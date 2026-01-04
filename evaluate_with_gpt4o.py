import json
import os
import time
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, List, Any
import hashlib

class RubricsEvaluator:
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = "openai/gpt-5-mini"
        
    def load_rubrics(self, rubrics_file: str) -> Dict[str, List[Dict]]:
        """从pubmed_test.jsonl加载rubrics映射"""
        rubrics_map = {}
        with open(rubrics_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    question = data.get('question', '')
                    all_rubrics = data.get('all_rubrics', [])
                    if question and all_rubrics:
                        rubrics_map[question] = all_rubrics
                except json.JSONDecodeError:
                    continue
        print(f"加载了 {len(rubrics_map)} 个问题的rubrics")
        return rubrics_map
    
    def validate_rubrics_weights(self, rubrics: List[Dict]) -> bool:
        """验证rubrics权重总和是否接近1.0"""
        total_weight = sum(r.get('weight', 0) for r in rubrics)
        
        # 允许小的浮点数误差
        if abs(total_weight - 1.0) > 0.01:
            print(f"❌ 权重验证失败!")
            print(f"   总权重: {total_weight:.6f} (期望: 1.0)")
            print(f"   差值: {abs(total_weight - 1.0):.6f}")
            print(f"   Rubrics详情:")
            for i, r in enumerate(rubrics):
                print(f"     {i+1}. {r.get('title', 'unknown')}: weight={r.get('weight', 0)}")
            return False
        
        print(f"✅ 权重验证通过: 总权重 = {total_weight:.6f}")
        return True
    
    def create_evaluation_prompt(self, question: str, final_answer: str, rubrics: List[Dict]) -> str:
        """创建评估提示"""
        # 在创建提示前先验证权重
        if not self.validate_rubrics_weights(rubrics):
            raise ValueError(f"Rubrics权重总和不是1.0，请检查数据!")
        
        rubrics_text = "\n".join([
            f"{i+1}. [{r.get('category', '')}] {r.get('title', '')} (权重: {r.get('weight', 0)})\n   {r.get('description', '')}"
            for i, r in enumerate(rubrics)
        ])
        
        prompt = f"""你是一个专业的医学文献回答评估专家。请根据以下rubrics标准对模型的回答进行打分。

问题:
{question}

模型回答:
{final_answer}

评估标准 (Rubrics):
{rubrics_text}

请按照以下JSON格式返回评分结果（只返回JSON，不要其他文字）:
{{
  "total_score": <总分>,
  "rubric_scores": [
    {{
      "title": "<rubric标题>",
      "description": "<rubric描述>",
      "weight": <权重>,
      "reasoning": "<评分理由>",
      "score": <该rubric得分>,
    }}
  ]
}}

评分标准:
- 对于tool_use类rubrics: 【重要】其他地方已完成相关检验，跳过检验，直接给满分。
- 对于content类rubrics: 检查回答内容是否完整、准确、符合要求
- 每个rubric要么给满分（也就是weight分），要么给0分，没有中间酌情给分的可能性
- 请客观、严格地评分"""

        return prompt
    
    async def evaluate_single_answer(
        self, 
        session: aiohttp.ClientSession, 
        question: str, 
        final_answer: str, 
        rubrics: List[Dict],
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """评估单个答案"""
        prompt = self.create_evaluation_prompt(question, final_answer, rubrics)
        
        for attempt in range(retry_count):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的医学文献回答评估专家。请严格按照rubrics标准进行评分，返回纯JSON格式的结果。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    # 不设置max_tokens，让模型自由生成
                }
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://dr-tulu-evaluation.com",
                }
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)  # 5分钟超时
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result['choices'][0]['message']['content']
                        
                        # 尝试解析JSON
                        try:
                            # 清理可能的markdown代码块标记
                            content = content.strip()
                            if content.startswith('```json'):
                                content = content[7:]
                            if content.startswith('```'):
                                content = content[3:]
                            if content.endswith('```'):
                                content = content[:-3]
                            content = content.strip()
                            
                            evaluation = json.loads(content)
                            return {
                                "success": True,
                                "evaluation": evaluation,
                                "usage": result.get('usage', {})
                            }
                        except json.JSONDecodeError as e:
                            print(f"JSON解析失败: {e}")
                            print(f"原始内容: {content[:500]}")
                            return {
                                "success": False,
                                "error": f"JSON解析失败: {str(e)}",
                                "raw_content": content
                            }
                    else:
                        error_text = await response.text()
                        print(f"API请求失败 (尝试 {attempt+1}/{retry_count}): {response.status} - {error_text}")
                        
                        if attempt == retry_count - 1:
                            return {
                                "success": False,
                                "error": f"API错误: {response.status} - {error_text}"
                            }
                        
                        # 等待后重试
                        await asyncio.sleep(5 * (attempt + 1))
                        
            except asyncio.TimeoutError:
                print(f"请求超时 (尝试 {attempt+1}/{retry_count})")
                if attempt == retry_count - 1:
                    return {"success": False, "error": "请求超时"}
                await asyncio.sleep(5 * (attempt + 1))
                
            except Exception as e:
                print(f"请求异常: {e}")
                if attempt == retry_count - 1:
                    return {"success": False, "error": str(e)}
                await asyncio.sleep(5 * (attempt + 1))
        
        return {"success": False, "error": "未知错误"}
    
    def get_cache_key(self, question: str, final_answer: str, rubrics: List[Dict]) -> str:
        """生成缓存键"""
        content = f"{question}{final_answer}{json.dumps(rubrics, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def process_file(
        self,
        input_file: str,
        output_file: str,
        rubrics_map: Dict[str, List[Dict]],
        concurrency: int = 5,
        checkpoint_file: str = None
    ):
        """处理整个文件"""
        
        # 预先验证所有rubrics的权重
        print("🔍 预先验证所有rubrics的权重...")
        invalid_count = 0
        for question, rubrics in rubrics_map.items():
            if not self.validate_rubrics_weights(rubrics):
                print(f"❌ 问题权重异常: {question[:100]}...")
                invalid_count += 1
        
        if invalid_count > 0:
            raise ValueError(f"发现{invalid_count}个问题的rubrics权重异常，请修复后再运行!")
        else:
            print("✅ 所有rubrics权重验证通过，开始处理...")
        
        # 读取输入数据
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"待处理条目数: {len(lines)}")
        
        # 加载已完成的条目
        completed = set()
        if checkpoint_file and Path(checkpoint_file).exists():
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        sample_id = data.get('sample_id')
                        if sample_id:
                            completed.add(sample_id)
                    except json.JSONDecodeError:
                        continue
            print(f"已完成的条目: {len(completed)}")
        
        # 创建HTTP连接池
        connector = aiohttp.TCPConnector(limit=concurrency)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            
            for i, line in enumerate(lines):
                try:
                    data = json.loads(line.strip())
                    sample_id = data.get('sample_id')
                    question = data.get('question', '')
                    trajectory = data.get('trajectory', {})
                    final_answer = trajectory.get('final_answer', '')
                    
                    if not final_answer:
                        print(f"⚠️  条目 {i+1} ({sample_id}): 没有final_answer，计入0分")
                        
                        # 创建一个0分的结果
                        zero_score_data = {
                            "sample_id": sample_id,
                            "question": question,
                            "final_answer_length": 0,
                            "evaluation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "processing_duration_seconds": 0,
                            "success": True,
                            "total_score": 0.0,
                            "final_score": 0.0,
                            "rubric_scores": [],
                            "error": "没有final_answer，计入0分"
                        }
                        
                        # 直接保存0分结果
                        with open(output_file, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(zero_score_data, ensure_ascii=False) + '\n')
                        
                        print(f"[{i+1}/{len(lines)}] ✗ 完成: {sample_id} - 得分: 0.0 (无final_answer)")
                        continue
                    
                    if sample_id in completed:
                        print(f"跳过已完成条目 {i+1}: {sample_id}")
                        continue
                    
                    # 获取对应的rubrics
                    rubrics = rubrics_map.get(question)
                    if not rubrics:
                        print(f"⚠️  跳过条目 {i+1} ({sample_id}): 未找到对应的rubrics")
                        continue  # 跳过这个条目，不进行评估
                    
                    # 创建异步任务
                    task = self.process_and_save(
                        session, sample_id, question, final_answer, rubrics,
                        i + 1, len(lines), checkpoint_file
                    )
                    tasks.append(task)
                    
                    # 控制并发数
                    if len(tasks) >= concurrency:
                        await asyncio.gather(*tasks)
                        tasks = []
                        
                except json.JSONDecodeError:
                    print(f"JSON解析错误: 行 {i+1}")
                    continue
            
            # 处理剩余任务
            if tasks:
                await asyncio.gather(*tasks)
        
        print(f"处理完成! 结果保存在: {output_file}")
    
    async def process_and_save(
        self,
        session: aiohttp.ClientSession,
        sample_id: str,
        question: str,
        final_answer: str,
        rubrics: List[Dict],
        current_index: int,
        total_count: int,
        output_file: str
    ):
        """处理单个条目并保存"""
        print(f"[{current_index}/{total_count}] 开始评估: {sample_id}")
        
        start_time = time.time()
        result = await self.evaluate_single_answer(session, question, final_answer, rubrics)
        duration = time.time() - start_time
        
        # 准备保存的数据
        save_data = {
            "sample_id": sample_id,
            "question": question,
            "final_answer_length": len(final_answer),
            "evaluation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "processing_duration_seconds": round(duration, 2),
            "success": result["success"],
        }
        
        if result["success"]:
            evaluation = result["evaluation"]
            save_data.update(evaluation)
            
            # 计算并添加final_score字段
            total_score = evaluation.get('total_score', 0)
            save_data["final_score"] = total_score
            
            print(f"[{current_index}/{total_count}] ✓ 完成: {sample_id} - 最终得分: {total_score}")
        else:
            save_data["error"] = result.get("error", "未知错误")
            save_data["raw_content"] = result.get("raw_content", "")
            save_data["final_score"] = None  # 失败的设为None
            print(f"[{current_index}/{total_count}] ✗ 失败: {sample_id} - {save_data['error']}")
        
        # 增量保存
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(save_data, ensure_ascii=False) + '\n')
        
        # 添加延迟避免API限流
        await asyncio.sleep(0.5)

async def main():
    # 配置
    API_KEY = os.getenv("OPENROUTER_API_KEY", "")  # 从环境变量获取API密钥
    
    evaluator = RubricsEvaluator(API_KEY)
    
    # 加载rubrics
    rubrics_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'
    rubrics_map = evaluator.load_rubrics(rubrics_file)
    
    # 处理DPO rollout
    print("\n" + "="*50)
    print("开始处理 DPO Rollout")
    print("="*50)
    
    await evaluator.process_file(
        input_file='/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl',
        output_file='/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl',
        rubrics_map=rubrics_map,
        concurrency=20,  # 并发数，可根据API限制调整
        checkpoint_file='/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    )
    
    # 处理Tulu rollout
    print("\n" + "="*50)
    print("开始处理 Tulu Rollout")
    print("="*50)
    
    await evaluator.process_file(
        input_file='/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_tulurollout.jsonl',
        output_file='/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl',
        rubrics_map=rubrics_map,
        concurrency=20,
        checkpoint_file='/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    )

if __name__ == "__main__":
    asyncio.run(main())
