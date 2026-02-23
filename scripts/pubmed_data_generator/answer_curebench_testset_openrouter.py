"""
使用 OpenRouter API + MCP 工具回答 CureBench Testset 问题
基于 answer_curebench_testset.py，将 LLM 调用改为 OpenRouter API

模型: seed1.8 (通过 --model-name 指定)
"""
import asyncio
import json
import glob
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import MCP_HOST, MCP_PORT, OPENROUTER_API_KEY
from trajectory_generator import (
    MCPToolExecutor,
    SYSTEM_PROMPT,
    ToolCallRecord,
)
import httpx
import re


# 针对选择题的 System Prompt（FDA 优先）- 与 answer_curebench_testset.py 一致
CUREBENCH_SYSTEM_PROMPT = """You are a medical expert assistant. Answer multiple-choice medical questions.

## Available Tools

1. **fda_drug_search** - Search FDA drug labels for medication information (PRIMARY TOOL - USE FIRST)
   - Format: <call_tool name="fda_drug_search" focus="aspect">drug_name</call_tool>
   - The focus parameter can be: adverse reactions, indications and usage, dosage and administration, warnings and precautions, contraindications, drug interactions, pregnancy, lactation, or any other relevant aspect
   - Example: <call_tool name="fda_drug_search" focus="adverse reactions">metformin</call_tool>

2. browse_webpage - Fetch and read webpage content (use if FDA tool is insufficient)
   - Format: <call_tool name="browse_webpage">URL</call_tool>
   - Example: <call_tool name="browse_webpage">https://dailymed.nlm.nih.gov/...</call_tool>

3. google_search - Search the web for medical information (use as last resort)
   - Format: <call_tool name="google_search">query</call_tool>
   - Example: <call_tool name="google_search">drug name side effects</call_tool>

## Tool Usage Priority

**IMPORTANT**: Always follow this priority order:
1. **First choice**: Use `fda_drug_search` for any drug-related questions
2. **Second choice**: Use `browse_webpage` if FDA search doesn't provide sufficient information
3. **Last resort**: Use `google_search` only when other tools cannot help

## Format Rules

1. Tool calls must be properly closed: <call_tool name="...">query</call_tool>
2. Only one tool call per response
3. Stop immediately after </call_tool> and wait for <tool_output>
4. Never write <tool_output> yourself

## Format Rules

### During Tool Calls
Each tool call MUST follow this exact format:

<think>
Goal: [What you're trying to find]
Plan: [Your step-by-step approach]
Next query: [Why you're making this specific tool call]
</think>
<call_tool name="tool_name" param="value">query</call_tool>

### Final Answer
When you have gathered enough information, provide your final answer:

<answer>
[Your reasoning process explaining how you arrived at the answer, including what evidence you found from the tools]

The answer is X.
</answer>

Where X is A, B, C, or D.
"""


@dataclass
class CureBenchResult:
    """CureBench 问题的回答结果"""
    question_id: str
    question: str
    question_type: str
    options: Dict[str, str]
    correct_answer: str  # testset 中为空字符串
    model_answer: str  # 模型选择的选项 (A/B/C/D)
    model_reasoning: str  # 模型的推理过程
    interleaved_text: str  # 完整的对话轨迹
    tool_calls: List[ToolCallRecord]
    is_correct: Optional[bool]  # testset 中为 None
    generation_time: str

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "question_type": self.question_type,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "model_answer": self.model_answer,
            "model_reasoning": self.model_reasoning,
            "interleaved_text": self.interleaved_text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_correct": self.is_correct,
            "generation_time": self.generation_time
        }


class CureBenchAnswerer:
    """使用 OpenRouter API + MCP 工具回答 CureBench 问题"""

    TOOL_MAPPING = {
        "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
        "google_search": "serper_google_webpage_search",
        "fda_drug_search": "fda_drug_label_search",
    }

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "seed1.8",
        max_turns: int = 15,
        temperature: float = 0.1,
    ):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model_name = model_name
        self.max_turns = max_turns
        self.temperature = temperature
        self.base_url = "https://openrouter.ai/api/v1"
        self.tool_executor = MCPToolExecutor(host=MCP_HOST, port=MCP_PORT)

    def _remove_hallucinated_tool_output(self, content: str) -> str:
        pattern = r'(</call_tool>)\s*<tool_output>.*?(?:</tool_output>|$)'
        cleaned = re.sub(pattern, r'\1', content, flags=re.DOTALL)

        if '<tool_output>' in cleaned:
            idx = cleaned.find('<tool_output>')
            cleaned = cleaned[:idx].rstrip()

        return cleaned

    def _clean_model_output(self, content: str, first_tool_call: tuple) -> str:
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
        mcp_tool_name = self.TOOL_MAPPING.get(tool_name, tool_name)

        if tool_name == "fda_drug_search":
            mcp_params = {
                "keyword": query,
                "focus": parameters.get("focus", "general information"),
                "limit": parameters.get("limit", 3),
                "use_llm_extraction": True
            }
        else:
            if tool_name == "pubmed_search":
                mcp_params = {
                    "query": query,
                    "limit": parameters.get("limit", 10),
                    "offset": parameters.get("offset", 0)
                }
            elif tool_name == "browse_webpage":
                mcp_params = {
                    "url": query,
                    "use_ai2_config": True,
                }
            elif tool_name == "google_search":
                mcp_params = {
                    "query": query,
                    "num_results": parameters.get("num_results", 10)
                }
            else:
                mcp_params = {"query": query, **parameters}

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

                formatted_output = self._format_tool_output(tool_name, raw_result)
                return raw_result, formatted_output

        except Exception as e:
            error_result = {"error": str(e)}
            return error_result, f"<tool_output>Error: {str(e)}</tool_output>"

    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        err = raw_result.get("error")
        if err is not None and err != "":
            return f"<tool_output>Error: {err}</tool_output>"

        if tool_name == "pubmed_search":
            snippets = []
            data = raw_result.get("data", [])
            for paper in data[:10]:
                pmid = paper.get("paperId", "unknown")
                title = paper.get("title", "No title")
                abstract = paper.get("abstract", "No abstract")
                year = paper.get("year", "N/A")
                venue = paper.get("venue", "N/A")

                snippet = f"""<snippet id="{pmid}">Title: {title}
Year: {year} | Journal: {venue}
Abstract: {abstract}</snippet>"""
                snippets.append(snippet)

            total = raw_result.get("total", len(data))
            header = f"Found {total} results. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"

        elif tool_name == "browse_webpage":
            md = raw_result.get("markdown") or ""
            if md:
                content = md[:8000]
            else:
                content = json.dumps(raw_result, ensure_ascii=False)[:2000]
            return f"<tool_output><webpage>{content}</webpage></tool_output>"

        elif tool_name == "google_search":
            results = raw_result.get("organic", raw_result.get("data", []))
            snippets = []
            for i, r in enumerate(results[:5]):
                title = r.get("title", "")
                snippet_text = r.get("snippet", r.get("description", ""))
                link = r.get("link", r.get("url", ""))
                snippets.append(f'<snippet id="G{i+1}">Title: {title}\n{snippet_text}\nURL: {link}</snippet>')
            return f"<tool_output>\n" + "\n".join(snippets) + "\n</tool_output>"

        elif tool_name == "fda_drug_search":
            keyword = raw_result.get("keyword", "")
            focus = raw_result.get("focus", "")
            strategy = raw_result.get("search_strategy", "")
            extracted_info = raw_result.get("extracted_info", [])

            if extracted_info:
                info_text = "\n".join([f"- {info}" for info in extracted_info])
                return f"""<tool_output>
FDA Drug Label Search Results for '{keyword}' (Focus: {focus})
Search Strategy: {strategy}

Extracted Information:
{info_text}
</tool_output>"""
            else:
                return f"<tool_output>No FDA information found for '{keyword}' (Focus: {focus})</tool_output>"

        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False)[:2000]}</tool_output>"

    def _format_question_with_options(self, question: str, options: Dict[str, str]) -> str:
        formatted = f"{question}\n\n"
        for key in sorted(options.keys()):
            formatted += f"{key}) {options[key]}\n"
        return formatted.strip()

    async def answer_question(self, question_data: Dict) -> CureBenchResult:
        question_id = question_data.get("id", "")
        question = question_data.get("question", "")
        question_type = question_data.get("question_type", "")
        options = question_data.get("options", {})
        correct_answer = question_data.get("correct_answer", "")  # testset 中为空

        formatted_question = self._format_question_with_options(question, options)

        messages = [
            {"role": "system", "content": CUREBENCH_SYSTEM_PROMPT},
            {"role": "user", "content": formatted_question}
        ]

        tool_calls = []
        total_tool_calls = 0
        interleaved_parts = []
        model_answer = ""
        model_reasoning = ""

        for turn in range(self.max_turns):
            response = await self._call_openrouter_llm(messages)

            if not response:
                print(f"  ⚠ LLM 无响应，停止生成")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                print(f"  ⚠ 响应内容为空，停止生成")
                break

            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )

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
                clean_content = self._clean_model_output(content, tool_call_matches[0])
                interleaved_parts.append(clean_content)

                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches[:1]:
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

                tool_output_text = "\n".join(all_tool_outputs)
                interleaved_parts.append(tool_output_text)

                messages.append({"role": "assistant", "content": clean_content})
                messages.append({"role": "user", "content": tool_output_text})

            else:
                if "<answer>" in content:
                    interleaved_parts.append(content)

                    choice_match = re.search(r'<choice>([A-D])</choice>', content, re.IGNORECASE)
                    if choice_match:
                        model_answer = choice_match.group(1).upper()

                    think_match = re.search(r'<answer>.*?<think>(.*?)</think>', content, re.DOTALL)
                    if think_match:
                        model_reasoning = think_match.group(1).strip()
                    else:
                        answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                        if answer_match:
                            model_reasoning = answer_match.group(1).strip()

                    print(f"  ✓ 模型答案: {model_answer}")
                    break
                else:
                    interleaved_parts.append(content)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please provide your final answer using the <answer> tag with <choice> inside."})

        if not model_answer and interleaved_parts:
            last_content = interleaved_parts[-1]
            letter_match = re.search(r'\b([A-D])\b', last_content)
            if letter_match:
                model_answer = letter_match.group(1)
                print(f"  ⚠ 从内容中提取答案: {model_answer}")

        interleaved_text = "\n".join(interleaved_parts)

        # testset 没有 correct_answer，is_correct 设为 None
        if correct_answer:
            is_correct = (model_answer == correct_answer)
        else:
            is_correct = None

        return CureBenchResult(
            question_id=question_id,
            question=question,
            question_type=question_type,
            options=options,
            correct_answer=correct_answer,
            model_answer=model_answer,
            model_reasoning=model_reasoning,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            is_correct=is_correct,
            generation_time=datetime.now().isoformat()
        )

    async def _call_openrouter_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用 OpenRouter API"""
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "stop": ["</call_tool>\n", "</call_tool><", "<tool_output>"],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-org/dr-tulu",
            "X-Title": "DR-Tulu CureBench Eval"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    content=json.dumps(request_data, ensure_ascii=False).encode('utf-8'),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"OpenRouter API 调用失败: {e}")
                return None

    def _truncate_result(self, result: Any, max_length: int = 3000) -> Any:
        if isinstance(result, dict):
            if "data" in result:
                truncated_data = []
                for paper in result.get("data", [])[:5]:
                    if isinstance(paper, dict):
                        truncated_data.append({
                            "paperId": paper.get("paperId"),
                            "title": paper.get("title"),
                            "abstract": paper.get("abstract", ""),
                            "year": paper.get("year"),
                            "venue": paper.get("venue"),
                        })
                return {"total": result.get("total"), "data": truncated_data}

            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                return {"truncated": True, "preview": result_str[:max_length]}
        return result


class CureBenchRunner:
    """运行 CureBench 评测（支持 testset，OpenRouter 版）"""

    def __init__(
        self,
        data_file: str,
        api_key: str = None,
        model_name: str = "seed1.8",
        output_dir: str = None,
        instance_id: str = None,
        prompt_version: str = "original"
    ):
        self.data_file = data_file
        self.model_name = model_name
        self.instance_id = instance_id
        self.prompt_version = prompt_version

        self.answerer = CureBenchAnswerer(
            api_key=api_key,
            model_name=model_name
        )

        self.results: List[CureBenchResult] = []

        # 默认输出目录
        if output_dir is None:
            _script_path = Path(__file__).resolve()
            _root = (_script_path.parent / ".." / "..").resolve()
            output_dir = str(_root / "curebench_testset_results")
        self.output_dir = output_dir

        os.makedirs(self.output_dir, exist_ok=True)
        model_suffix = model_name.replace("/", "_").replace(":", "_")

        if instance_id:
            file_suffix = f"{model_suffix}_{instance_id}_{prompt_version}"
        else:
            file_suffix = f"{model_suffix}_{prompt_version}"

        # 断点续跑：查找已有的结果文件
        self.output_file, self.stats_file = self._find_or_create_output_files(file_suffix)
        self.completed_ids = self._load_completed_ids()
        if self.completed_ids:
            print(f"🔄 断点续跑：发现已完成 {len(self.completed_ids)} 个问题，将跳过这些问题")

    def _find_or_create_output_files(self, file_suffix: str) -> tuple:
        """查找已有的结果文件，如果没有则创建新文件"""
        pattern = os.path.join(self.output_dir, f"curebench_testset_results_*_{file_suffix}.jsonl")
        existing_files = sorted(glob.glob(pattern))

        if existing_files:
            output_file = existing_files[-1]
            basename = os.path.basename(output_file)
            import re as _re
            ts_match = _re.search(r'curebench_testset_results_(\d{8}_\d{6})_', basename)
            if ts_match:
                timestamp = ts_match.group(1)
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stats_file = os.path.join(
                self.output_dir,
                f"curebench_testset_stats_{timestamp}_{file_suffix}.json"
            )
            print(f"📂 找到已有结果文件: {os.path.basename(output_file)}")
            return output_file, stats_file
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(
                self.output_dir,
                f"curebench_testset_results_{timestamp}_{file_suffix}.jsonl"
            )
            stats_file = os.path.join(
                self.output_dir,
                f"curebench_testset_stats_{timestamp}_{file_suffix}.json"
            )
            print(f"📂 创建新结果文件: {os.path.basename(output_file)}")
            return output_file, stats_file

    def _load_completed_ids(self) -> set:
        """从已有的结果文件中加载已完成的 question_id"""
        completed = set()
        if not os.path.exists(self.output_file):
            return completed

        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            qid = data.get("question_id", "")
                            if qid:
                                completed.add(qid)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"  ⚠️ 读取已有结果文件失败: {e}")

        return completed

    def load_questions(self) -> List[Dict]:
        print(f"从文件加载问题: {self.data_file}")
        questions = []

        with open(self.data_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        q = json.loads(line)
                        questions.append(q)
                    except json.JSONDecodeError as e:
                        print(f"  ⚠ JSON解析错误: {e}")

        print(f"✓ 加载了 {len(questions)} 个问题")
        return questions

    async def run_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[CureBenchResult]:
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
        print("\n" + "=" * 60)
        print(f"CureBench Testset 评测 - OpenRouter - Prompt版本: {self.prompt_version}")
        print("=" * 60)
        print(f"模型: {self.answerer.model_name}")
        print(f"API: OpenRouter")
        print(f"并发数: {concurrency}")

        questions = self.load_questions()

        if not questions:
            print("✗ 没有加载到任何问题")
            return

        has_correct_answer = "correct_answer" in questions[0]
        if not has_correct_answer:
            print("📋 检测到 Testset 模式（无 correct_answer）")

        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")

        # 断点续跑
        if self.completed_ids:
            original_count = len(questions)
            questions = [q for q in questions if q.get("id", "") not in self.completed_ids]
            skipped = original_count - len(questions)
            print(f"🔄 跳过已完成的 {skipped} 个问题，剩余 {len(questions)} 个待处理")
            if not questions:
                print("✓ 所有问题已完成，无需继续")
                return

        print("\n" + "=" * 60)
        print("开始回答问题（并发模式）")
        print("=" * 60)

        semaphore = asyncio.Semaphore(concurrency)

        tasks = []
        for i, q_data in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] {q_data.get('id', '')}: {q_data.get('question', '')[:80]}...")
            task = self.run_with_retry(q_data, i, semaphore)
            tasks.append(task)

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

                self.append_result_to_file(result)

                if has_correct_answer:
                    print(f"  {'✓' if result.is_correct else '✗'} 模型答案: {result.model_answer} | 正确答案: {result.correct_answer}")
                else:
                    print(f"  📝 模型答案: {result.model_answer}")

            if has_correct_answer:
                accuracy = (correct / len(self.results) * 100) if self.results else 0
                print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%) | "
                      f"正确: {correct}/{len(self.results)} | "
                      f"准确率: {accuracy:.1f}%")
            else:
                print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%)")

        self.save_stats(has_correct_answer)

        print(f"\n{'='*60}")
        print(f"评测完成！")
        print(f"总问题数: {len(self.results)}")
        if has_correct_answer:
            accuracy = (correct / len(self.results) * 100) if self.results else 0
            print(f"正确数: {correct}")
            print(f"准确率: {accuracy:.2f}%")
        print(f"结果保存到: {self.output_file}")
        print(f"统计保存到: {self.stats_file}")
        print(f"{'='*60}")

    def append_result_to_file(self, result: CureBenchResult):
        try:
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"  ⚠️ 增量保存失败: {e}")

    def save_stats(self, has_correct_answer: bool = True):
        if not self.results:
            print("⚠️ 没有结果可保存")
            return

        by_type = {}
        for r in self.results:
            qtype = r.question_type
            if qtype not in by_type:
                by_type[qtype] = {"total": 0, "correct": 0, "answers": []}
            by_type[qtype]["total"] += 1
            by_type[qtype]["answers"].append(r.model_answer)
            if has_correct_answer and r.is_correct:
                by_type[qtype]["correct"] += 1

        if has_correct_answer:
            for qtype in by_type:
                by_type[qtype]["accuracy"] = by_type[qtype]["correct"] / by_type[qtype]["total"] * 100
                del by_type[qtype]["answers"]

        total_tool_calls = sum(len(r.tool_calls) for r in self.results)
        avg_tool_calls = total_tool_calls / len(self.results) if self.results else 0

        stats = {
            "total_questions": len(self.results),
            "prompt_version": self.prompt_version,
            "by_question_type": by_type,
            "tool_usage": {
                "total_tool_calls": total_tool_calls,
                "avg_tool_calls_per_question": avg_tool_calls
            },
            "model": self.answerer.model_name,
            "api": "openrouter",
            "instance_id": self.instance_id,
            "data_file": self.data_file,
            "generation_time": datetime.now().isoformat()
        }

        if has_correct_answer:
            correct_count = sum(1 for r in self.results if r.is_correct)
            stats["correct"] = correct_count
            stats["accuracy"] = correct_count / len(self.results) * 100

        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        print(f"✓ 统计已保存")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="使用 OpenRouter API + MCP 工具回答 CureBench Testset 问题")
    _root = (Path(__file__).resolve().parent / ".." / "..").resolve()
    _default_data = str(_root / "训练和benchmark数据0120" / "curebench_testset_phase1.jsonl")
    _default_output = str(_root / "curebench_testset_results")
    parser.add_argument("--data-file", type=str, default=_default_data,
                        help="CureBench 数据文件路径")
    parser.add_argument("--model-name", type=str, default="seed1.8", help="OpenRouter 模型名称")
    parser.add_argument("--api-key", type=str, default=None,
                        help="OpenRouter API Key（默认从环境变量 OPENROUTER_API_KEY 读取）")
    parser.add_argument("--instance-id", type=str, default=None, help="实例标识")
    parser.add_argument("--output", type=str, default=_default_output, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的问题数量")
    parser.add_argument("--prompt-version", type=str, default="original", help="Prompt版本标识")

    args = parser.parse_args()

    print(f"模型: {args.model_name}")
    print(f"API: OpenRouter")
    print(f"数据文件: {args.data_file}")
    print(f"Prompt版本: {args.prompt_version}")
    print(f"并发数: {args.concurrency}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")

    runner = CureBenchRunner(
        data_file=args.data_file,
        api_key=args.api_key,
        model_name=args.model_name,
        output_dir=args.output,
        instance_id=args.instance_id,
        prompt_version=args.prompt_version
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
