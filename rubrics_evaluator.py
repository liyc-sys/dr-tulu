#!/usr/bin/env python3
"""
Rubrics评估工具
调用OpenRouter的GPT-4o评估rubrics设计是否合理
支持并发、增量保存、失败重试、断点续跑
"""
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import aiohttp
from datetime import datetime


class RubricsEvaluator:
    def __init__(self, api_key: str, input_file: str, output_file: str, 
                 max_concurrent: int = 5, max_retries: int = 3):
        self.api_key = api_key
        self.input_file = input_file
        self.output_file = output_file
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # 创建输出目录
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)

    def load_progress(self) -> Dict[str, dict]:
        """加载已保存的评估结果"""
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_progress(self, results: Dict[str, dict]):
        """保存评估结果"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    def load_data(self) -> List[dict]:
        """加载待评估的数据"""
        data = []
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return data

    def create_evaluation_prompt(self, question: str, content_rubrics: dict) -> str:
        """创建评估提示"""
        rubrics_text = json.dumps(content_rubrics, ensure_ascii=False, indent=2)
        
        prompt = f"""You are a professional expert in evaluating large language models' PubMed-related medical capabilities. Please assess whether the following scoring rubrics designed for LLMs are reasonable.

Question: {question}

Scoring Rubrics:
{rubrics_text}

Evaluation Criteria:
1. Whether the scoring rubrics are clear, specific, and actionable
2. Whether the scoring dimensions comprehensively cover key aspects of the question
3. Whether the scoring levels are reasonably defined
4. Whether the rubrics can effectively differentiate between different quality levels of responses

Please provide your analysis in the following format:

ANALYSIS:
[Your detailed analysis of the rubrics here - discuss each evaluation criterion and provide reasoning]

CONCLUSION: reasonable OR unreasonable

Please strictly follow this format and ensure your conclusion is either "reasonable" or unreasonable"."""
        return prompt

    def parse_response(self, response: str) -> Optional[bool]:
        """解析API响应，返回True(合理)或False(不合理)，无法解析返回None"""
        response_lower = response.strip().lower()
        
        # 首先尝试从CONCLUSION格式中提取
        conclusion_match = re.search(r'conclusion:\s*(reasonable|unreasonable)', response_lower)
        if conclusion_match:
            conclusion = conclusion_match.group(1)
            return conclusion == "reasonable"
        
        # 如果没有找到CONCLUSION格式，尝试其他格式匹配
        # 检查是否包含明确的结论标记
        conclusion_patterns = [
            r'(conclusion|final judgment|verdict|decision):\s*(reasonable|unreasonable)',
            r'(reasonable|unreasonable)\s*$',  # 以结论结尾
            r'is\s*(reasonable|unreasonable)',  # "is reasonable/unreasonable"
        ]
        
        for pattern in conclusion_patterns:
            match = re.search(pattern, response_lower)
            if match:
                conclusion = match.group(2) if match.lastindex >= 2 else match.group(1)
                return conclusion == "reasonable"
        
        # 最后尝试在整个文本中查找关键词（作为备用方案）
        reasonable_patterns = [r'\breasonable\b', r'\bwell-designed\b', r'\bgood rubrics\b', r'\beffective rubrics\b']
        unreasonable_patterns = [r'\bunreasonable\b', r'\bpoorly designed\b', r'\bbad rubrics\b', r'\bineffective rubrics\b']
        
        reasonable_count = sum(1 for pattern in reasonable_patterns if re.search(pattern, response_lower))
        unreasonable_count = sum(1 for pattern in unreasonable_patterns if re.search(pattern, response_lower))
        
        if reasonable_count > unreasonable_count:
            return True
        elif unreasonable_count > reasonable_count:
            return False
        
        # 如果都找不到，返回None表示无法解析
        return None

    async def call_openrouter(self, prompt: str, session: aiohttp.ClientSession, 
                            retry_count: int = 0) -> Optional[str]:
        """调用OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "google/gemini-3-pro-preview",
            "messages": [
                {"role": "system", "content": "You are a professional educational assessment expert specializing in evaluating the quality of scoring rubrics."},
                {"role": "user", "content": prompt}
            ],
        }
        
        try:
            async with session.post(self.api_url, headers=headers, json=data, 
                                  timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    print(f"API错误: {response.status} - {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"请求超时，重试 {retry_count + 1}/{self.max_retries}")
            return None
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return None

    async def evaluate_single_item(self, item: dict, session: aiohttp.ClientSession) -> Tuple[str, Optional[dict]]:
        """评估单个项目"""
        sample_id = item["sample_id"]
        question = item["question"]
        content_rubrics = item.get("content_rubrics", {})

        
        if not content_rubrics:
            return sample_id, {
                "error": "没有content_rubrics字段",
                "evaluated": False
            }
            # raise Error
            
        
        prompt = self.create_evaluation_prompt(question, content_rubrics)
        
        # 带重试的API调用
        for retry in range(self.max_retries):
            response_text = await self.call_openrouter(prompt, session, retry)
            
            if response_text:
                judgment = self.parse_response(response_text)
                
                if judgment is not None:
                    return sample_id, {
                        "question": question,
                        "content_rubrics": content_rubrics,
                        "response": response_text,
                        "is_reasonable": judgment,
                        "evaluated": True,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    print(f"{sample_id}: 无法解析API响应: {response_text}")
            else:
                if retry < self.max_retries - 1:
                    await asyncio.sleep(2 ** retry)  # 指数退避
        
        # 所有重试都失败
        return sample_id, {
            "error": "API调用失败或无法解析响应",
            "evaluated": False,
            "timestamp": datetime.now().isoformat()
        }

    async def evaluate_batch(self, items: List[dict]) -> Dict[str, dict]:
        """批量评估"""
        results = {}
        
        # 加载已保存的进度
        existing_results = self.load_progress()
        results.update(existing_results)
        
        # 过滤掉已评估的项目
        pending_items = [item for item in items if item["sample_id"] not in existing_results]
        print(f"总项目数: {len(items)}, 已评估: {len(existing_results)}, 待评估: {len(pending_items)}")
        
        if not pending_items:
            print("所有项目已评估完成")
            return results
        
        # 创建HTTP会话
        connector = aiohttp.TCPConnector(limit=self.max_concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            # 使用信号量控制并发数
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def evaluate_with_semaphore(item):
                async with semaphore:
                    return await self.evaluate_single_item(item, session)
            
            # 批量评估
            tasks = [evaluate_with_semaphore(item) for item in pending_items]
            
            completed = 0
            for coro in asyncio.as_completed(tasks):
                sample_id, result = await coro
                results[sample_id] = result
                completed += 1
                
                # 每10个或完成时保存一次
                if completed % 10 == 0 or completed == len(pending_items):
                    self.save_progress(results)
                    print(f"进度: {completed}/{len(pending_items)}")
        
        return results

    def run(self):
        """运行评估"""
        print("开始加载评估数据...")
        data = self.load_data()
        print(f"加载了 {len(data)} 条数据")
        
        print("开始评估...")
        results = asyncio.run(self.evaluate_batch(data))
        
        # 最终保存
        self.save_progress(results)
        
        # 统计结果
        evaluated = [r for r in results.values() if r.get("evaluated", False)]
        reasonable = sum(1 for r in evaluated if r.get("is_reasonable", False))
        unreasonable = len(evaluated) - reasonable
        
        print(f"\n评估完成!")
        print(f"总项目数: {len(results)}")
        print(f"成功评估: {len(evaluated)}")
        print(f"合理: {reasonable}")
        print(f"不合理: {unreasonable}")
        print(f"评估失败: {len(results) - len(evaluated)}")
        print(f"结果已保存到: {self.output_file}")


def main():
    # 配置参数
    API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    INPUT_FILE = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl"
    OUTPUT_FILE = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_evaluation_results.json"
    MAX_CONCURRENT = 30  # 并发数
    MAX_RETRIES = 3     # 重试次数
    
    if not API_KEY:
        print("错误: 请设置环境变量 OPENROUTER_API_KEY")
        print("示例: export OPENROUTER_API_KEY='your-api-key'")
        return
    
    evaluator = RubricsEvaluator(
        api_key=API_KEY,
        input_file=INPUT_FILE,
        output_file=OUTPUT_FILE,
        max_concurrent=MAX_CONCURRENT,
        max_retries=MAX_RETRIES
    )
    
    evaluator.run()


if __name__ == "__main__":
    main()