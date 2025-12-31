#!/usr/bin/env python3
"""
从已有问题生成轨迹并使用OpenRouter的gpt-4o-mini进行评分
"""
import asyncio
import json
import os
import sys
import re
import requests
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


class LocalModelTrajectoryGenerator:
    """使用本地模型生成轨迹"""
    
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
            response = await self._call_local_llm(messages)
            
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
                    tools_used.add(tool_name)
                    total_tool_calls += 1
                    
                    print(f"  执行工具: {tool_name}({query})")
                    
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
                
                tool_output_text = "\n".join(all_tool_outputs)
                interleaved_parts.append(tool_output_text)
                
                messages.append({"role": "assistant", "content": clean_content})
                
                if total_tool_calls >= 5:
                    reminder = f"{tool_output_text}\n\n⚠️ You have reached the maximum limit of 5 tool calls. You MUST provide your final answer now using the <answer> tag."
                    messages.append({"role": "user", "content": reminder})
                    print(f"  ⚠️ 已达到工具调用上限 (5次)，提醒模型给出答案")
                else:
                    messages.append({"role": "user", "content": tool_output_text})
                
            else:
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
        
        interleaved_text = "\n".join(interleaved_parts)
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


class TrajectoryEvaluator:
    """使用OpenRouter评估轨迹质量"""
    
    def __init__(
        self,
        model_name: str = "openai/gpt-4o-mini",
        api_key: Optional[str] = None
    ):
        self.model_name = model_name
        self.api_base = "https://openrouter.ai/api/v1"
        
        # 获取API密钥
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY 未设置，请提供api_key参数或设置环境变量")
    
    async def evaluate_trajectory(
        self,
        question: str,
        trajectory: Trajectory,
        rubrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        评估轨迹质量
        
        Args:
            question: 用户问题
            trajectory: 生成的轨迹
            rubrics: 评分标准（如果有）
            
        Returns:
            评估结果，包含分数和理由
        """
        
        # 构建评分提示词
        if rubrics:
            prompt = self._build_rubric_based_prompt(question, trajectory, rubrics)
        else:
            prompt = self._build_general_quality_prompt(question, trajectory)
        
        try:
            response = self._call_openrouter(prompt)
            
            # 解析响应
            return self._parse_evaluation_response(response)
            
        except Exception as e:
            print(f"  ⚠ 评分失败: {e}")
            return {
                "error": str(e),
                "score": 0.0,
                "reasoning": "评分过程出错"
            }
    
    def _call_openrouter(self, prompt: str) -> str:
        """调用OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        }
        
        # 添加超时设置：连接超时10秒，读取超时60秒
        response = requests.post(self.api_base, headers=headers, json=data, timeout=(10, 60))
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    
    def _build_general_quality_prompt(self, question: str, trajectory: Trajectory) -> str:
        """构建通用的质量评分提示词"""
        prompt = f"""### Task Description
Please act as an impartial judge and evaluate the quality of the response provided by an AI assistant to the user query displayed below.

Notes:
1. Your evaluation should consider factors such as the helpfulness, relevance, accuracy, depth, creativity, and level of detail of the response.
2. Begin your evaluation by providing a short explanation.
3. Be as objective as possible. After providing your explanation, please rate the response on a scale of 1 to 10.

[Query]
{question}

[Response]
{trajectory.final_answer if trajectory.final_answer else trajectory.interleaved_text}

[Additional Information]
- Tools used: {', '.join(trajectory.tools_used)}
- Number of tool calls: {trajectory.total_tool_calls}
- PMIDs cited: {', '.join(trajectory.pmids_cited) if trajectory.pmids_cited else 'None'}

[Your judgement]
Respond in JSON format: {{"REASONING": "[...]", "SCORE": "<your-score>"}}
"""
        return prompt
    
    def _build_rubric_based_prompt(
        self,
        question: str,
        trajectory: Trajectory,
        rubrics: Dict[str, Any]
    ) -> str:
        """基于rubrics构建评分提示词"""
        tool_rubrics = rubrics.get("tool_rubrics", [])
        content_rubrics = rubrics.get("content_rubrics", [])
        
        rubric_text = "### Evaluation Criteria\n\n"
        
        if tool_rubrics:
            rubric_text += "Tool Use Rubrics:\n"
            for i, rubric in enumerate(tool_rubrics, 1):
                rubric_text += f"{i}. {rubric.get('title', '')}: {rubric.get('description', '')}\n"
        
        if content_rubrics:
            rubric_text += "\nContent Rubrics:\n"
            for i, rubric in enumerate(content_rubrics, 1):
                rubric_text += f"{i}. {rubric.get('title', '')}: {rubric.get('description', '')}\n"
        
        prompt = f"""### Task Description
Please act as an impartial judge and evaluate the quality of the response provided by an AI assistant to the user query displayed below.

Notes:
- Evaluate the response against each criterion independently.
- Begin your evaluation by providing a short explanation for each criterion.
- The maximum score is awarded as follows: 0.1 points for each of the three "Tool Use Rubrics" items, and 0.7 points for each of the "Content Rubrics" items. If you believe a particular rubric is adequately represented, award full marks to that item; otherwise, award it 0 points. Finally, output a decimal between 0 and 1 as the total score.
- Be as objective as possible. After providing your explanation, output the overall score.

{rubric_text}

[Query]
{question}

[Response]
{trajectory.final_answer if trajectory.final_answer else trajectory.interleaved_text}

[Additional Information]
- Tools used: {', '.join(trajectory.tools_used)}
- Number of tool calls: {trajectory.total_tool_calls}
- PMIDs cited: {', '.join(trajectory.pmids_cited) if trajectory.pmids_cited else 'None'}

[Your judgement]
Respond in JSON format: {{"REASONING": "[...]", "SCORE": "<your-score>"}}
"""
        return prompt
    
    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """解析评估响应"""
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{[^{}]*"REASONING"[^{}]*"SCORE"[^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "score": float(result.get("SCORE", 0)),
                    "reasoning": result.get("REASONING", ""),
                    "raw_response": response
                }
            
            # 如果没有找到JSON，尝试直接提取分数
            score_match = re.search(r'SCORE["\s:]+(\d+\.?\d*)', response, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
                return {
                    "score": score,
                    "reasoning": response,
                    "raw_response": response
                }
            
            # 最后尝试提取任何数字
            number_matches = re.findall(r'\d+\.?\d*', response)
            if number_matches:
                return {
                    "score": float(number_matches[0]),
                    "reasoning": response,
                    "raw_response": response
                }
            
            return {
                "score": 0.0,
                "reasoning": "无法解析评分响应",
                "raw_response": response
            }
            
        except Exception as e:
            return {
                "score": 0.0,
                "error": f"解析错误: {e}",
                "raw_response": response
            }


@dataclass
class EvaluatedTrajectorySample:
    """经过评估的轨迹样本"""
    sample_id: str
    question: str
    topic: str
    question_type: str
    trajectory: Dict[str, Any]
    evaluation: Dict[str, Any]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "topic": self.topic,
            "question_type": self.question_type,
            "trajectory": self.trajectory,
            "evaluation": self.evaluation,
            "metadata": self.metadata
        }


class TrajectoryGeneratorWithEval:
    """生成轨迹并进行评估"""
    
    def __init__(
        self,
        questions_file: str,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        output_dir: str = OUTPUT_DIR,
        incremental_save: bool = True,
        instance_id: str = None,
        enable_evaluation: bool = True,
        eval_model: str = "openai/gpt-4o-mini"
    ):
        self.questions_file = questions_file
        self.model_name = model_name
        self.instance_id = instance_id
        self.enable_evaluation = enable_evaluation
        
        api_model_name = model_name.split("_port")[0] if "_port" in model_name else model_name
        
        self.trajectory_generator = LocalModelTrajectoryGenerator(
            local_model_url=local_model_url,
            model_name=api_model_name
        )
        
        self.evaluator = None
        if enable_evaluation:
            try:
                self.evaluator = TrajectoryEvaluator(model_name=eval_model)
            except Exception as e:
                print(f"⚠️ 无法初始化评估器: {e}")
                print("   将继续生成轨迹但不进行评分")
                self.enable_evaluation = False
        
        self.samples: List[EvaluatedTrajectorySample] = []
        self.output_dir = output_dir
        self.incremental_save = incremental_save
        
        if self.incremental_save:
            os.makedirs(self.output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_suffix = api_model_name.replace("/", "_").replace(":", "_")
            
            if instance_id:
                file_suffix = f"{model_suffix}_{instance_id}"
            else:
                file_suffix = model_suffix
            
            self.incremental_file = os.path.join(
                self.output_dir,
                f"pubmed_trajectory_evaluated_{timestamp}_{file_suffix}_incremental.jsonl"
            )
            self.timestamp = timestamp
            self.model_suffix = file_suffix
    
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
    
    async def generate_and_evaluate(
        self,
        question_data: Dict,
        sample_index: int
    ) -> Optional[EvaluatedTrajectorySample]:
        """为单个问题生成轨迹并评估"""
        question = question_data.get("question", "")
        rubrics = question_data.get("rubrics")  # 如果数据中包含rubrics
        
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
        
        # 评估轨迹
        evaluation = {"enabled": False}
        if self.enable_evaluation:
            print("  正在评估轨迹质量...")
            try:
                evaluation = await self.evaluator.evaluate_trajectory(
                    question=question,
                    trajectory=trajectory,
                    rubrics=rubrics
                )
                evaluation["enabled"] = True
                print(f"  ✓ 评估完成: 得分 {evaluation.get('score', 0)}")
            except Exception as e:
                print(f"  ⚠ 评估失败: {e}")
                evaluation = {
                    "enabled": True,
                    "error": str(e),
                    "score": 0.0,
                    "reasoning": "评估过程出错"
                }
        
        # 构建sample_id
        if self.instance_id:
            sample_id = f"{self.instance_id}_eval_{sample_index:05d}"
        else:
            base_name = self.model_name.replace("/", "_").replace(":", "_").replace("-", "_")
            sample_id = f"{base_name}_eval_{sample_index:05d}"
        
        return EvaluatedTrajectorySample(
            sample_id=sample_id,
            question=question,
            topic=question_data.get("topic", ""),
            question_type=question_data.get("question_type", ""),
            trajectory=trajectory.to_dict(),
            evaluation=evaluation,
            metadata={
                "expected_search_terms": question_data.get("expected_search_terms", []),
                "tools_used": trajectory.tools_used,
                "total_tool_calls": trajectory.total_tool_calls,
                "generation_time": datetime.now().isoformat(),
                "model": self.model_name,
                "api_model": self.trajectory_generator.model_name,
                "instance_id": self.instance_id,
                "source_file": self.questions_file,
                "rubrics_provided": rubrics is not None
            }
        )
    
    async def generate_and_evaluate_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[EvaluatedTrajectorySample]:
        """带重试机制的轨迹生成和评估"""
        async with semaphore:
            for attempt in range(max_retries):
                try:
                    sample = await self.generate_and_evaluate(q_data, sample_index)
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
    
    async def generate_dataset(self, concurrency: int = 5, limit: int = None) -> List[EvaluatedTrajectorySample]:
        """生成完整数据集"""
        print("\n" + "=" * 60)
        print("从已有问题生成轨迹并进行评估")
        print("=" * 60)
        print(f"本地模型: {self.trajectory_generator.model_name}")
        print(f"API地址: {self.trajectory_generator.local_model_url}")
        print(f"并发数: {concurrency}")
        print(f"评估: {'启用' if self.enable_evaluation else '禁用'}")
        
        # 加载问题
        questions = self.load_questions()
        
        if not questions:
            print("✗ 没有加载到任何问题")
            return []
        
        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")
        
        print("\n" + "=" * 60)
        print("生成轨迹并评估（并发模式）")
        print("=" * 60)
        
        semaphore = asyncio.Semaphore(concurrency)
        
        tasks = []
        for i, q_data in enumerate(questions, 1):
            task = self.generate_and_evaluate_with_retry(q_data, i, semaphore)
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
                self.append_sample_to_file(sample)
            
            success_rate = (len(samples) / completed * 100) if completed > 0 else 0
            avg_score = 0.0
            if samples and self.enable_evaluation:
                scores = [s.evaluation.get("score", 0) for s in samples if s.evaluation.get("enabled")]
                avg_score = sum(scores) / len(scores) if scores else 0.0
            
            print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%) | "
                  f"成功: {len(samples)} | 失败: {completed - len(samples)} | "
                  f"成功率: {success_rate:.1f}%")
            if avg_score > 0:
                print(f"   平均得分: {avg_score:.2f}")
        
        self.samples = samples
        print(f"\n✓ 完成！共生成 {len(samples)} 个样本")
        if self.incremental_save:
            print(f"💾 所有样本已增量保存到: {self.incremental_file}")
        return samples
    
    def append_sample_to_file(self, sample: EvaluatedTrajectorySample):
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
            f"trajectory_evaluated_stats_{self.timestamp}_{self.model_suffix}.json"
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
        scores = []
        
        for sample in self.samples:
            topics[sample.topic] = topics.get(sample.topic, 0) + 1
            question_types[sample.question_type] = question_types.get(sample.question_type, 0) + 1
            tool_calls_counts.append(sample.metadata.get("total_tool_calls", 0))
            
            if sample.evaluation.get("enabled"):
                scores.append(sample.evaluation.get("score", 0))
        
        stats = {
            "total_samples": len(self.samples),
            "topics": topics,
            "question_types": question_types,
            "avg_tool_calls": sum(tool_calls_counts) / len(tool_calls_counts) if tool_calls_counts else 0,
            "generation_time": datetime.now().isoformat(),
            "model": self.trajectory_generator.model_name,
            "source_file": self.questions_file,
            "evaluation_enabled": self.enable_evaluation
        }
        
        if scores and self.enable_evaluation:
            stats["avg_score"] = sum(scores) / len(scores)
            stats["min_score"] = min(scores)
            stats["max_score"] = max(scores)
        
        return stats


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="从已有问题生成轨迹并进行评估")
    parser.add_argument("--questions-file", type=str, required=True, help="问题JSONL文件路径")
    parser.add_argument("--local-model-url", type=str, default="http://localhost:8000/v1",
                        help="本地模型API地址（OpenAI兼容格式）")
    parser.add_argument("--model-name", type=str, default="Qwen3-8B", help="模型名称")
    parser.add_argument("--instance-id", type=str, default=None, help="实例标识（如port8000）")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制生成的问题数量")
    parser.add_argument("--no-incremental", action="store_true", help="禁用增量保存")
    parser.add_argument("--no-evaluation", action="store_true", help="禁用评估")
    parser.add_argument("--eval-model", type=str, default="openai/gpt-5-mini",
                        help="评估使用的模型")
    
    args = parser.parse_args()
    
    print(f"本地模型: {args.model_name}")
    print(f"API地址: {args.local_model_url}")
    print(f"问题文件: {args.questions_file}")
    print(f"并发数: {args.concurrency}")
    print(f"评估: {'禁用' if args.no_evaluation else '启用'}")
    if args.no_evaluation:
        print(f"  评估模型: {args.eval_model}")
    
    generator = TrajectoryGeneratorWithEval(
        questions_file=args.questions_file,
        local_model_url=args.local_model_url,
        model_name=args.model_name,
        output_dir=args.output,
        incremental_save=not args.no_incremental,
        instance_id=args.instance_id,
        enable_evaluation=not args.no_evaluation,
        eval_model=args.eval_model
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
