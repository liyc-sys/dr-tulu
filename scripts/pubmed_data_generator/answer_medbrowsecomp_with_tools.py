"""
使用本地模型 + MCP 工具回答 MedBrowseComp 问题
读取 MedBrowseComp CSV，调用本地模型生成带工具调用的答案
"""
import asyncio
import json
import os
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import OUTPUT_DIR, MCP_HOST, MCP_PORT
from trajectory_generator import (
    MCPToolExecutor,
    ToolCallRecord,
)
import httpx
import re


# MedBrowseComp System Prompt
MEDBROWSECOMP_SYSTEM_PROMPT = """You are a medical research assistant. Answer questions about clinical trials, drug patents, approvals, and exclusivity information.

## Available Tools

1. **medbrowsecomp_search** - Unified medical search: NCT clinical trials, patents, approvals, exclusivity
   - Format: <call_tool name="medbrowsecomp_search">query</call_tool>
   - Example: <call_tool name="medbrowsecomp_search">NCT01639001</call_tool>

2. **get_trial_info** - Get ClinicalTrials.gov trial information by NCT number
   - Format: <call_tool name="get_trial_info">NCT_number</call_tool>
   - Example: <call_tool name="get_trial_info">NCT01639001</call_tool>

3. **get_drug_patents** - Get FDA Orange Book drug patents
   - Format: <call_tool name="get_drug_patents">drug_name</call_tool>
   - Example: <call_tool name="get_drug_patents">CRIZOTINIB</call_tool>

4. **get_drug_approvals** - Get FDA Orange Book drug approvals
   - Format: <call_tool name="get_drug_approvals">drug_name</call_tool>
   - Example: <call_tool name="get_drug_approvals">CRIZOTINIB</call_tool>

5. **get_drug_exclusivities** - Get FDA Orange Book drug exclusivity periods
   - Format: <call_tool name="get_drug_exclusivities">drug_name</call_tool>
   - Example: <call_tool name="get_drug_exclusivities">CRIZOTINIB</call_tool>

## Format Rules

1. Tool calls must be properly closed: <call_tool name="...">query</call_tool>
2. Only one tool call per response
3. Stop immediately after </call_tool> and wait for <tool_output>
4. Never write <tool_output> yourself

## Output Format

Your final answer must use this format:

<answer>
<think>Your reasoning process</think>
<result>Your final answer following the format specified in the question</result>
</answer>
"""


@dataclass
class MedBrowseCompResult:
    """MedBrowseComp 问题的回答结果"""
    question_id: str
    question: str
    task_name: str
    correct_answer: str
    model_answer: str
    model_reasoning: str
    interleaved_text: str
    tool_calls: List[ToolCallRecord]
    is_correct: bool
    generation_time: str

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "task_name": self.task_name,
            "correct_answer": self.correct_answer,
            "model_answer": self.model_answer,
            "model_reasoning": self.model_reasoning,
            "interleaved_text": self.interleaved_text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_correct": self.is_correct,
            "generation_time": self.generation_time
        }


class MedBrowseCompAnswerer:
    """使用本地模型 + MCP 工具回答 MedBrowseComp 问题"""

    # 工具映射：逻辑名 -> MCP 工具名
    TOOL_MAPPING = {
        "medbrowsecomp_search": "medbrowsecomp_search",
        "get_trial_info": "get_trial_info",
        "get_drug_patents": "get_drug_patents",
        "get_drug_approvals": "get_drug_approvals",
        "get_drug_exclusivities": "get_drug_exclusivities",
        "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
        "google_search": "serper_google_webpage_search",
    }

    def __init__(
        self,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        max_turns: int = 10
    ):
        self.local_model_url = local_model_url
        self.model_name = model_name
        self.max_turns = max_turns
        self.tool_executor = MCPToolExecutor(host=MCP_HOST, port=MCP_PORT)

    def _remove_hallucinated_tool_output(self, content: str) -> str:
        """移除模型可能生成的假 tool_output 内容"""
        pattern = r'(</call_tool>)\s*<tool_output>.*?(?:</tool_output>|$)'
        cleaned = re.sub(pattern, r'\1', content, flags=re.DOTALL)

        if '<tool_output>' in cleaned:
            idx = cleaned.find('<tool_output>')
            cleaned = cleaned[:idx].rstrip()

        return cleaned

    def _clean_model_output(self, content: str, first_tool_call: tuple) -> str:
        """清理模型输出，只保留到第一个有效的 call_tool 为止"""
        tool_name, params_str, query = first_tool_call

        if params_str:
            call_tool_tag = f'<call_tool name="{tool_name}" {params_str}>{query}</call_tool>'
        else:
            call_tool_tag = f'<call_tool name="{tool_name}">{query}</call_tool>'

        first_call_idx = content.find('<call_tool')
        if first_call_idx == -1:
            return content

        prefix = content[:first_call_idx]

        close_tag_idx = content.find('</call_tool>', first_call_idx)
        if close_tag_idx != -1:
            clean_content = content[:close_tag_idx + len('</call_tool>')]
        else:
            clean_content = prefix + call_tool_tag

        clean_content = self._remove_hallucinated_tool_output(clean_content)

        return clean_content

    async def _execute_tool_with_mapping(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        query: str
    ) -> tuple[Dict[str, Any], str]:
        """执行工具调用，使用自定义映射"""
        # 获取 MCP 工具名
        mcp_tool_name = self.TOOL_MAPPING.get(tool_name, tool_name)

        # 构建参数
        mcp_params = {"query": query, **parameters}

        # 调用 MCP 工具
        from fastmcp import Client
        client = Client(f"http://{MCP_HOST}:{MCP_PORT}/mcp", timeout=120)

        try:
            async with client:
                result = await client.call_tool(mcp_tool_name, mcp_params)

                if hasattr(result, "content") and result.content:
                    if hasattr(result.content[0], "text"):
                        raw_result = json.loads(result.content[0].text)
                    else:
                        raw_result = {"data": str(result.content[0])}
                else:
                    raw_result = {"error": "No content in response"}

                # 格式化输出
                formatted_output = self._format_tool_output(tool_name, raw_result)
                return raw_result, formatted_output

        except Exception as e:
            error_result = {"error": str(e)}
            return error_result, f"<tool_output>Error: {str(e)}</tool_output>"

    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        """格式化工具输出"""
        err = raw_result.get("error")
        if err is not None and err != "":
            return f"<tool_output>Error: {err}</tool_output>"

        # 基本格式化，返回 JSON 或主要内容
        data = raw_result.get("data")
        if data:
            # 如果数据是列表或字典，格式化为可读形式
            if isinstance(data, (list, dict)):
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                return f"<tool_output>\n{formatted}\n</tool_output>"
            else:
                return f"<tool_output>{data}</tool_output>"

        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False, indent=2)}</tool_output>"

    async def answer_question(self, question_data: Dict) -> MedBrowseCompResult:
        """为单个 MedBrowseComp 问题生成答案"""

        question_id = str(question_data.get("row_id", ""))
        question = question_data.get("prompt", "")
        task_name = question_data.get("task_name", "")
        correct_answer = question_data.get("gold", "")

        messages = [
            {"role": "system", "content": MEDBROWSECOMP_SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]

        tool_calls = []
        total_tool_calls = 0
        interleaved_parts = []
        model_answer = ""
        model_reasoning = ""

        for turn in range(self.max_turns):
            # 调用本地 LLM
            response = await self._call_local_llm(messages)

            if not response:
                print(f"  ⚠ LLM 无响应，停止生成")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                print(f"  ⚠ 响应内容为空，停止生成")
                break

            # 检查工具调用
            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )

            # 如果没有闭合标签的匹配，尝试匹配未闭合的
            if not tool_call_matches:
                unclosed_matches = re.findall(
                    r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>(.*?)(?=<call_tool|<answer|$)',
                    content, re.DOTALL
                )
                if unclosed_matches:
                    first_match = unclosed_matches[0]
                    tool_name = first_match[0]
                    params_str = first_match[1]
                    query = first_match[2].strip().split('\n')[0].strip()
                    tool_call_matches = [(tool_name, params_str, query)]
                    print(f"  ⚠ 检测到未闭合的 <call_tool>，自动修复")

            if tool_call_matches:
                # 清理内容
                clean_content = self._clean_model_output(content, tool_call_matches[0])
                interleaved_parts.append(clean_content)

                # 只执行第一个工具调用
                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches[:1]:
                    # 解析参数
                    parameters = {}
                    if params_str:
                        param_matches = re.findall(r'(\w+)="([^"]*)"', params_str)
                        for k, v in param_matches:
                            try:
                                parameters[k] = int(v)
                            except:
                                parameters[k] = v

                    query = query.strip()
                    total_tool_calls += 1

                    print(f"  执行工具: {tool_name}({query})")

                    # 执行工具
                    raw_result, formatted_output = await self._execute_tool_with_mapping(
                        tool_name, parameters, query
                    )

                    tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        parameters=parameters,
                        query=query,
                        result=self._truncate_result(raw_result),
                        timestamp=datetime.now().isoformat()
                    ))

                    all_tool_outputs.append(formatted_output)

                # 添加工具输出
                tool_output_text = "\n".join(all_tool_outputs)
                interleaved_parts.append(tool_output_text)

                messages.append({"role": "assistant", "content": clean_content})
                messages.append({"role": "user", "content": tool_output_text})

            else:
                # 检查是否有 <answer>
                if "<answer>" in content:
                    interleaved_parts.append(content)

                    # 提取 <result>
                    result_match = re.search(r'<result>(.*?)</result>', content, re.DOTALL | re.IGNORECASE)
                    if result_match:
                        model_answer = result_match.group(1).strip()

                    # 提取推理过程
                    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
                    if think_match:
                        model_reasoning = think_match.group(1).strip()
                    else:
                        # 如果没有 think，就用整个 answer 内容
                        answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                        if answer_match:
                            model_reasoning = answer_match.group(1).strip()

                    print(f"  ✓ 模型答案: {model_answer}")
                    break
                else:
                    interleaved_parts.append(content)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please provide your final answer using the <answer> tag with <result> inside."})

        # 如果没有提取到答案，尝试从最后的内容中提取
        if not model_answer and interleaved_parts:
            last_content = interleaved_parts[-1]
            model_answer = last_content.strip()
            print(f"  ⚠ 使用最后内容作为答案: {model_answer[:100]}...")

        # 组合完整的 interleaved 文本
        interleaved_text = "\n".join(interleaved_parts)

        # 判断是否正确（简单的字符串匹配）
        is_correct = self._check_answer_correctness(model_answer, correct_answer)

        return MedBrowseCompResult(
            question_id=question_id,
            question=question,
            task_name=task_name,
            correct_answer=correct_answer,
            model_answer=model_answer,
            model_reasoning=model_reasoning,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            is_correct=is_correct,
            generation_time=datetime.now().isoformat()
        )

    def _check_answer_correctness(self, model_answer: str, correct_answer: str) -> bool:
        """检查答案是否正确"""
        if not model_answer or not correct_answer:
            return False

        # 标准化处理
        model_ans_norm = model_answer.strip().upper()
        correct_ans_norm = correct_answer.strip().upper()

        # 精确匹配
        if model_ans_norm == correct_ans_norm:
            return True

        # 包含匹配
        if correct_ans_norm in model_ans_norm or model_ans_norm in correct_ans_norm:
            return True

        return False

    async def _call_local_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用本地模型 API（OpenAI兼容格式）"""
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "stop": ["</call_tool>\n", "</call_tool><", "<tool_output>"],
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{self.local_model_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    content=json.dumps(request_data, ensure_ascii=False).encode('utf-8'),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"本地LLM调用失败: {e}")
                return None

    def _truncate_result(self, result: Any, max_length: int = 3000) -> Any:
        """截断过长的结果"""
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                return {"truncated": True, "preview": result_str[:max_length]}
        return result


class MedBrowseCompRunner:
    """运行 MedBrowseComp 评测"""

    def __init__(
        self,
        data_file: str,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        output_dir: str = OUTPUT_DIR,
        instance_id: str = None
    ):
        self.data_file = data_file
        self.model_name = model_name
        self.instance_id = instance_id

        # 提取基础模型名
        api_model_name = model_name.split("_port")[0] if "_port" in model_name else model_name

        self.answerer = MedBrowseCompAnswerer(
            local_model_url=local_model_url,
            model_name=api_model_name
        )

        self.results: List[MedBrowseCompResult] = []
        self.output_dir = output_dir

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_suffix = api_model_name.replace("/", "_").replace(":", "_")

        if instance_id:
            file_suffix = f"{model_suffix}_{instance_id}"
        else:
            file_suffix = model_suffix

        self.output_file = os.path.join(
            self.output_dir,
            f"medbrowsecomp_results_{timestamp}_{file_suffix}.jsonl"
        )
        self.stats_file = os.path.join(
            self.output_dir,
            f"medbrowsecomp_stats_{timestamp}_{file_suffix}.json"
        )
        self.timestamp = timestamp

    def load_questions(self) -> List[Dict]:
        """从 CSV 加载问题"""
        print(f"从文件加载问题: {self.data_file}")
        questions = []

        with open(self.data_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                questions.append({
                    "row_id": i,
                    "gold": row.get("gold", ""),
                    "prompt": row.get("prompt", ""),
                    "task_name": row.get("task_name", "")
                })

        print(f"✓ 加载了 {len(questions)} 个问题")
        return questions

    async def run_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[MedBrowseCompResult]:
        """带重试机制的问答"""
        async with semaphore:
            for attempt in range(max_retries):
                try:
                    result = await self.answerer.answer_question(q_data)
                    return result
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"  ⚠️ [{sample_index}] 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                        print(f"  ⏳ 等待 {wait_time}s 后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"  ✗ [{sample_index}] 所有重试失败: {e}")
            return None

    async def run_evaluation(self, concurrency: int = 5, limit: int = None):
        """运行评测"""
        print("\n" + "=" * 60)
        print("MedBrowseComp 评测 - 使用本地模型 + MCP 工具")
        print("=" * 60)
        print(f"本地模型: {self.answerer.model_name}")
        print(f"API地址: {self.answerer.local_model_url}")
        print(f"并发数: {concurrency}")

        # 加载问题
        questions = self.load_questions()

        if not questions:
            print("✗ 没有加载到任何问题")
            return

        # 如果设置了limit，只处理前N个问题
        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")

        # 并发生成答案
        print("\n" + "=" * 60)
        print("开始回答问题（并发模式）")
        print("=" * 60)

        semaphore = asyncio.Semaphore(concurrency)

        tasks = []
        for i, q_data in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] Task: {q_data.get('task_name', '')} | Question: {q_data.get('prompt', '')[:80]}...")
            task = self.run_with_retry(q_data, i, semaphore)
            tasks.append(task)

        # 执行并显示进度
        completed = 0
        correct = 0
        total = len(tasks)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1

            if result:
                self.results.append(result)
                if result.is_correct:
                    correct += 1

                # 增量保存
                self.append_result_to_file(result)

                print(f"  {'✓' if result.is_correct else '✗'} 模型答案: {result.model_answer[:100]} | 正确答案: {result.correct_answer[:100]}")

            # 显示进度
            accuracy = (correct / len(self.results) * 100) if self.results else 0
            print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%) | "
                  f"正确: {correct}/{len(self.results)} | "
                  f"准确率: {accuracy:.1f}%")

        # 保存统计
        self.save_stats()

        print(f"\n{'='*60}")
        print(f"评测完成！")
        print(f"总问题数: {len(self.results)}")
        print(f"正确数: {correct}")
        print(f"准确率: {accuracy:.2f}%")
        print(f"结果保存到: {self.output_file}")
        print(f"统计保存到: {self.stats_file}")
        print(f"{'='*60}")

    def append_result_to_file(self, result: MedBrowseCompResult):
        """增量保存：追加单条结果到文件"""
        try:
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"  ⚠️ 增量保存失败: {e}")

    def save_stats(self):
        """保存统计信息"""
        if not self.results:
            print("⚠️ 没有结果可保存")
            return

        correct_count = sum(1 for r in self.results if r.is_correct)
        accuracy = correct_count / len(self.results) * 100

        # 按任务类型统计
        by_task = {}
        for r in self.results:
            task = r.task_name
            if task not in by_task:
                by_task[task] = {"total": 0, "correct": 0}
            by_task[task]["total"] += 1
            if r.is_correct:
                by_task[task]["correct"] += 1

        for task in by_task:
            by_task[task]["accuracy"] = by_task[task]["correct"] / by_task[task]["total"] * 100

        # 工具使用统计
        total_tool_calls = sum(len(r.tool_calls) for r in self.results)
        avg_tool_calls = total_tool_calls / len(self.results) if self.results else 0

        stats = {
            "total_questions": len(self.results),
            "correct": correct_count,
            "accuracy": accuracy,
            "by_task_type": by_task,
            "tool_usage": {
                "total_tool_calls": total_tool_calls,
                "avg_tool_calls_per_question": avg_tool_calls
            },
            "model": self.answerer.model_name,
            "instance_id": self.instance_id,
            "data_file": self.data_file,
            "generation_time": datetime.now().isoformat()
        }

        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        print(f"✓ 统计已保存")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="使用本地模型 + MCP 工具回答 MedBrowseComp 问题")

    # 使用相对路径
    _script_path = Path(__file__).resolve()
    _root = (_script_path.parent / ".." / "..").resolve()
    _default_data = str(_root / "训练和benchmark数据0120" / "MedBrowseComp_605_part2.csv")
    _default_output = str(_root / "pubmed_training_data")

    parser.add_argument("--data-file", type=str, default=_default_data,
                        help="MedBrowseComp CSV 文件路径（默认：项目根/训练和benchmark数据0120/MedBrowseComp_605_part2.csv）")
    parser.add_argument("--local-model-url", type=str, default="http://localhost:8000/v1",
                        help="本地模型API地址（OpenAI兼容格式）")
    parser.add_argument("--model-name", type=str, default="Qwen3-8B", help="模型名称")
    parser.add_argument("--instance-id", type=str, default=None, help="实例标识（如port8000）")
    parser.add_argument("--output", type=str, default=_default_output, help="输出目录（默认：项目根/pubmed_training_data）")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的问题数量（用于测试）")

    args = parser.parse_args()

    print(f"本地模型: {args.model_name}")
    print(f"API地址: {args.local_model_url}")
    print(f"数据文件: {args.data_file}")
    print(f"并发数: {args.concurrency}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")

    runner = MedBrowseCompRunner(
        data_file=args.data_file,
        local_model_url=args.local_model_url,
        model_name=args.model_name,
        output_dir=args.output,
        instance_id=args.instance_id
    )

    try:
        await runner.run_evaluation(concurrency=args.concurrency, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，保存已完成的结果...")
        if runner.results:
            runner.save_stats()
        print("✓ 已保存部分结果")
    except Exception as e:
        print(f"\n\n✗ 评测过程出错: {e}")
        import traceback
        traceback.print_exc()
        if runner.results:
            print("\n保存已完成的结果...")
            runner.save_stats()

    print("\n" + "=" * 60)
    print("评测完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
