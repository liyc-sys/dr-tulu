"""
使用本地Qwen3-8B模型从已有问题生成轨迹
从JSONL文件读取questions，调用本地模型生成轨迹，不生成rubrics
"""
import asyncio
import json
import os
import sys
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
    SYSTEM_PROMPT,
    ToolCallRecord,
    Trajectory
)
import httpx
import re


class LocalModelTrajectoryGenerator:
    """使用本地Qwen3-8B模型生成轨迹"""
    
    def __init__(
        self,
        local_model_url: str = "http://localhost:8000/v1",  # 本地模型API地址
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
    
    async def generate_trajectory(self, question: str) -> Trajectory:
        """为给定问题生成完整的 interleaved 轨迹"""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
        
        tool_calls = []
        tools_used = set()
        total_tool_calls = 0
        interleaved_parts = []
        final_answer = ""
        
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
                    tools_used.add(tool_name)
                    total_tool_calls += 1
                    
                    print(f"  执行工具: {tool_name}({query})")
                    
                    # 执行工具
                    raw_result, formatted_output = await self.tool_executor.execute_tool(
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
                
                # 检查是否达到工具调用限制
                if total_tool_calls >= 5:
                    reminder = f"{tool_output_text}\n\n⚠️ You have reached the maximum limit of 5 tool calls. You MUST provide your final answer now using the <answer> tag."
                    messages.append({"role": "user", "content": reminder})
                    print(f"  ⚠️ 已达到工具调用上限 (5次)，提醒模型给出答案")
                else:
                    messages.append({"role": "user", "content": tool_output_text})
                
            else:
                # 检查是否有 <answer>
                if "<answer>" in content:
                    interleaved_parts.append(content)
                    answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                    if answer_match:
                        final_answer = answer_match.group(1).strip()
                    else:
                        final_answer = content.split("<answer>")[-1].strip()
                    print(f"  ✓ 获取到最终答案")
                    break
                else:
                    interleaved_parts.append(content)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please continue with tool calls or provide your final answer."})
        
        # 组合完整的 interleaved 文本
        interleaved_text = "\n".join(interleaved_parts)
        
        # 提取所有引用的 PMIDs
        pmids_cited = list(set(re.findall(r'<cite\s+id="(\d+)"', interleaved_text)))
        
        return Trajectory(
            question=question,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            final_answer=final_answer,
            total_tool_calls=total_tool_calls,
            tools_used=list(tools_used),
            pmids_cited=pmids_cited
        )
    
    async def _call_local_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用本地模型 API（OpenAI兼容格式）"""
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
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


@dataclass
class TrajectoryDataSample:
    """轨迹数据样本（无rubrics）"""
    sample_id: str
    question: str
    topic: str
    question_type: str
    trajectory: Dict[str, Any]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "topic": self.topic,
            "question_type": self.question_type,
            "trajectory": self.trajectory,
            "metadata": self.metadata
        }


class QuestionBasedTrajectoryGenerator:
    """从已有问题生成轨迹"""
    
    def __init__(
        self,
        questions_file: str,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        output_dir: str = OUTPUT_DIR,
        incremental_save: bool = True
    ):
        self.questions_file = questions_file
        self.trajectory_generator = LocalModelTrajectoryGenerator(
            local_model_url=local_model_url,
            model_name=model_name
        )
        self.samples: List[TrajectoryDataSample] = []
        self.output_dir = output_dir
        self.incremental_save = incremental_save
        
        # 创建输出目录和增量保存文件
        if self.incremental_save:
            os.makedirs(self.output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_suffix = model_name.replace("/", "_").replace(":", "_")
            self.incremental_file = os.path.join(
                self.output_dir,
                f"pubmed_trajectory_{timestamp}_{model_suffix}_incremental.jsonl"
            )
            self.timestamp = timestamp
            self.model_suffix = model_suffix
    
    def load_questions(self) -> List[Dict]:
        """从JSONL文件加载问题"""
        print(f"从文件加载问题: {self.questions_file}")
        questions = []
        
        with open(self.questions_file, 'r', encoding='utf-8') as f:
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
    
    async def generate_trajectory_for_question(
        self,
        question_data: Dict,
        sample_index: int
    ) -> Optional[TrajectoryDataSample]:
        """为单个问题生成轨迹"""
        question = question_data.get("question", "")
        
        print(f"\n[{sample_index}] 问题: {question}")
        
        # 生成轨迹
        print("  正在生成工具调用轨迹...")
        try:
            trajectory = await self.trajectory_generator.generate_trajectory(question)
            print(f"  ✓ 轨迹生成完成: {trajectory.total_tool_calls} 次工具调用")
        except Exception as e:
            print(f"  ✗ 轨迹生成失败: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        return TrajectoryDataSample(
            sample_id=f"qwen3_traj_{sample_index:05d}",
            question=question,
            topic=question_data.get("topic", ""),
            question_type=question_data.get("question_type", ""),
            trajectory=trajectory.to_dict(),
            metadata={
                "expected_search_terms": question_data.get("expected_search_terms", []),
                "tools_used": trajectory.tools_used,
                "total_tool_calls": trajectory.total_tool_calls,
                "generation_time": datetime.now().isoformat(),
                "model": self.trajectory_generator.model_name,
                "source_file": self.questions_file
            }
        )
    
    async def generate_trajectory_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[TrajectoryDataSample]:
        """带重试机制的轨迹生成"""
        async with semaphore:
            for attempt in range(max_retries):
                try:
                    sample = await self.generate_trajectory_for_question(q_data, sample_index)
                    if sample:
                        return sample
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"  ⚠️ [{sample_index}] 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                        print(f"  ⏳ 等待 {wait_time}s 后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"  ✗ [{sample_index}] 所有重试失败: {e}")
            return None
    
    async def generate_dataset(self, concurrency: int = 5, limit: int = None) -> List[TrajectoryDataSample]:
        """生成完整数据集
        
        Args:
            concurrency: 并发数
            limit: 限制生成的问题数量（用于测试），None表示生成全部
        """
        print("\n" + "=" * 60)
        print("从已有问题生成轨迹")
        print("=" * 60)
        print(f"本地模型: {self.trajectory_generator.model_name}")
        print(f"API地址: {self.trajectory_generator.local_model_url}")
        print(f"并发数: {concurrency}")
        
        # 加载问题
        questions = self.load_questions()
        
        if not questions:
            print("✗ 没有加载到任何问题")
            return []
        
        # 如果设置了limit，只处理前N个问题
        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")
        
        # 并发生成轨迹
        print("\n" + "=" * 60)
        print("生成轨迹（并发模式）")
        print("=" * 60)
        
        semaphore = asyncio.Semaphore(concurrency)
        
        tasks = []
        for i, q_data in enumerate(questions, 1):
            task = self.generate_trajectory_with_retry(q_data, i, semaphore)
            tasks.append(task)
        
        # 执行并显示进度
        samples = []
        completed = 0
        total = len(tasks)
        
        if self.incremental_save:
            print(f"💾 增量保存已启用: {self.incremental_file}")
        
        for coro in asyncio.as_completed(tasks):
            sample = await coro
            completed += 1
            if sample:
                samples.append(sample)
                # 增量保存
                self.append_sample_to_file(sample)
            
            # 显示进度
            success_rate = (len(samples) / completed * 100) if completed > 0 else 0
            print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%) | "
                  f"成功: {len(samples)} | 失败: {completed - len(samples)} | "
                  f"成功率: {success_rate:.1f}%")
        
        self.samples = samples
        print(f"\n✓ 完成！共生成 {len(samples)} 个样本")
        if self.incremental_save:
            print(f"💾 所有样本已增量保存到: {self.incremental_file}")
        return samples
    
    def append_sample_to_file(self, sample: TrajectoryDataSample):
        """增量保存：追加单条样本到文件"""
        if not self.incremental_save:
            return
        
        try:
            with open(self.incremental_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(sample.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"  ⚠️ 增量保存失败: {e}")
    
    def save_dataset(self):
        """保存数据集统计"""
        if not self.samples:
            print("⚠️ 没有样本可保存")
            return
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 保存统计
        stats = self._generate_stats()
        stats_path = os.path.join(
            self.output_dir,
            f"trajectory_stats_{self.timestamp}_{self.model_suffix}.json"
        )
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存统计: {stats_path}")
        
        return self.incremental_file
    
    def _generate_stats(self) -> Dict:
        """生成统计信息"""
        if not self.samples:
            return {}
        
        topics = {}
        question_types = {}
        tool_calls_counts = []
        
        for sample in self.samples:
            topics[sample.topic] = topics.get(sample.topic, 0) + 1
            question_types[sample.question_type] = question_types.get(sample.question_type, 0) + 1
            tool_calls_counts.append(sample.metadata.get("total_tool_calls", 0))
        
        return {
            "total_samples": len(self.samples),
            "topics": topics,
            "question_types": question_types,
            "avg_tool_calls": sum(tool_calls_counts) / len(tool_calls_counts) if tool_calls_counts else 0,
            "generation_time": datetime.now().isoformat(),
            "model": self.trajectory_generator.model_name,
            "source_file": self.questions_file
        }


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="从已有问题生成轨迹（使用本地Qwen3-8B）")
    parser.add_argument("--questions-file", type=str, required=True, help="问题JSONL文件路径")
    parser.add_argument("--local-model-url", type=str, default="http://localhost:8000/v1", 
                        help="本地模型API地址（OpenAI兼容格式）")
    parser.add_argument("--model-name", type=str, default="Qwen3-8B", help="模型名称")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制生成的问题数量（用于测试）")
    parser.add_argument("--no-incremental", action="store_true", help="禁用增量保存")
    
    args = parser.parse_args()
    
    print(f"本地模型: {args.model_name}")
    print(f"API地址: {args.local_model_url}")
    print(f"问题文件: {args.questions_file}")
    print(f"并发数: {args.concurrency}")
    print(f"增量保存: {'禁用' if args.no_incremental else '启用'}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")
    
    generator = QuestionBasedTrajectoryGenerator(
        questions_file=args.questions_file,
        local_model_url=args.local_model_url,
        model_name=args.model_name,
        output_dir=args.output,
        incremental_save=not args.no_incremental
    )
    
    try:
        await generator.generate_dataset(concurrency=args.concurrency, limit=args.limit)
        generator.save_dataset()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，保存已完成的样本...")
        if generator.samples:
            generator.save_dataset()
        print("✓ 已保存部分结果")
    except Exception as e:
        print(f"\n\n✗ 生成过程出错: {e}")
        import traceback
        traceback.print_exc()
        if generator.samples:
            print("\n保存已完成的样本...")
            generator.save_dataset()
    
    print("\n" + "=" * 60)
    print("数据生成完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

