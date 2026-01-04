#!/usr/bin/env python3
"""
分析interleaved_text中最重要的工具调用步骤
调用OpenRouter GPT-4o判断哪2-3步工具调用最重要
支持断点续跑、并发开20、增量保存
"""

import json
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import asyncio
import aiohttp
from aiohttp import ClientSession
from datetime import datetime


class ToolImportanceAnalyzer:
    def __init__(self, api_key: str, input_file: str, output_file: str, max_concurrent: int = 20):
        self.api_key = api_key
        self.input_file = input_file
        self.output_file = output_file
        self.max_concurrent = max_concurrent
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
    def extract_tool_calls(self, interleaved_text: str) -> List[Dict[str, Any]]:
        """提取所有工具调用步骤"""
        tool_calls = []
        pattern = r'<call_tool name="([^"]+)"(?: limit="(\d+)")?>(.*?)</call_tool>'
        
        for match in re.finditer(pattern, interleaved_text, re.DOTALL):
            tool_name = match.group(1)
            limit = match.group(2) if match.group(2) else "default"
            query = match.group(3).strip()
            
            # 获取工具调用在原文中的位置（用于后续定位）
            start_pos = match.start()
            
            tool_calls.append({
                'step_number': len(tool_calls) + 1,
                'tool_name': tool_name,
                'limit': limit,
                'query': query,
                'start_pos': start_pos,
                'full_match': match.group(0)
            })
            
        return tool_calls
    
    def create_analysis_prompt(self, question: str, tool_calls: List[Dict[str, Any]]) -> str:
        """创建GPT-4o分析的prompt"""
        tool_calls_desc = []
        for call in tool_calls:
            tool_calls_desc.append(
                f"步骤 {call['step_number']}: {call['tool_name']}\n"
                f"查询内容: {call['query'][:200]}{'...' if len(call['query']) > 200 else ''}"
            )
        
        prompt = f"""你是一个专业的科研工具调用分析专家。请分析以下科研问题解决过程中，哪2-3个工具调用步骤最为重要。

科研问题: {question}

工具调用序列:
{chr(10).join(tool_calls_desc)}

请选择最重要的2-3个步骤，并按照以下格式返回：

重要性分析：
步骤 X: [具体步骤编号] - [选择理由，包括该步骤对解决问题的重要性、关键信息的获取等]
步骤 Y: [具体步骤编号] - [选择理由]
步骤 Z: [具体步骤编号] - [选择理由]（如果选择第3步）

最重要的步骤总结: [步骤编号列表，用逗号分隔，如: 1,3,5]

注意：
1. 优先选择那些获取关键信息、改变搜索方向或获得突破性结果的步骤
2. 考虑步骤之间的依赖关系和逻辑递进
3. 选择对回答问题最核心、最不可或缺的步骤
4. 必须在"最重要的步骤总结"中只包含数字，用逗号分隔，不要有其他内容"""
        
        return prompt
    
    async def call_gpt4o(self, session: ClientSession, prompt: str) -> str:
        """调用OpenRouter GPT-4o API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dr-tulu-analysis.com",
        }
        
        payload = {
            "model": "openai/gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的科研工具调用分析专家，擅长评估和判断各个研究步骤的重要性。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.0,
            # 不限制max_tokens
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        print(f"API错误 (状态码 {response.status}): {error_text}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)  # 指数退避
                        else:
                            raise Exception(f"API调用失败: {response.status} - {error_text}")
            except asyncio.TimeoutError:
                print(f"请求超时，重试 {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise Exception("请求超时，已达最大重试次数")
            except Exception as e:
                print(f"请求异常: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    
    def parse_important_steps(self, response: str) -> List[int]:
        """解析GPT-4o返回的重要步骤编号"""
        # 多种模式匹配步骤编号
        patterns = [
            r'最重要的步骤总结[：:]\s*([0-9,]+)',
            r'重要步骤[：:]\s*([0-9,]+)',
            r'Summary[：:]\s*([0-9,]+)',
            r'步骤[：:]\s*([0-9,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                steps_str = match.group(1)
                try:
                    steps = [int(s.strip()) for s in steps_str.split(',') if s.strip().isdigit()]
                    if steps:
                        return steps
                except ValueError:
                    continue
        
        # 如果上面的模式都匹配不到，尝试直接提取所有数字
        numbers = re.findall(r'\b([1-9]\d*|0)\b', response)
        if numbers:
            # 取最后几个数字（通常是总结部分）
            unique_numbers = list(set(int(n) for n in numbers))
            if len(unique_numbers) <= 5:  # 如果数字不多，可能是步骤编号
                return unique_numbers
        
        return []
    
    def load_processed_records(self) -> set:
        """加载已处理的记录ID（支持断点续跑）"""
        processed = set()
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            if 'sample_id' in record:
                                processed.add(record['sample_id'])
                print(f"发现已处理记录: {len(processed)}条")
            except Exception as e:
                print(f"加载已处理记录时出错: {e}")
        return processed
    
    async def process_single_record(self, session: ClientSession, record: Dict[str, Any]) -> Dict[str, Any]:
        """处理单条记录"""
        sample_id = record.get('sample_id', '')
        question = record.get('question', '')
        trajectory = record.get('trajectory', {})
        interleaved_text = trajectory.get('interleaved_text', '')
        
        if not interleaved_text:
            return {
                'sample_id': sample_id,
                'status': 'error',
                'error': '没有interleaved_text'
            }
        
        # 提取工具调用
        tool_calls = self.extract_tool_calls(interleaved_text)
        
        if not tool_calls:
            return {
                'sample_id': sample_id,
                'status': 'error',
                'error': '没有找到工具调用'
            }
        
        # 创建分析prompt
        prompt = self.create_analysis_prompt(question, tool_calls)
        
        try:
            # 调用GPT-4o
            response = await self.call_gpt4o(session, prompt)
            
            # 解析重要步骤
            important_steps = self.parse_important_steps(response)
            
            # 验证步骤编号的有效性
            valid_steps = [s for s in important_steps if 1 <= s <= len(tool_calls)]
            
            return {
                'sample_id': sample_id,
                'question': question,
                'total_steps': len(tool_calls),
                'important_steps': valid_steps,
                'analysis_response': response,
                'tool_calls_summary': [
                    {
                        'step': call['step_number'],
                        'tool': call['tool_name'],
                        'query': call['query'][:100]
                    }
                    for call in tool_calls
                ],
                'status': 'success',
                'processed_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'sample_id': sample_id,
                'status': 'error',
                'error': str(e),
                'total_steps': len(tool_calls),
                'processed_time': datetime.now().isoformat()
            }
    
    async def process_batch(self, session: ClientSession, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理一批记录"""
        tasks = [self.process_single_record(session, record) for record in batch]
        return await asyncio.gather(*tasks)
    
    async def run_analysis(self):
        """运行分析"""
        # 读取输入文件
        print(f"读取输入文件: {self.input_file}")
        records = []
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        print(f"总记录数: {len(records)}")
        
        # 加载已处理记录（支持断点续跑）
        processed_ids = self.load_processed_records()
        remaining_records = [r for r in records if r.get('sample_id') not in processed_ids]
        
        print(f"待处理记录数: {len(remaining_records)}")
        
        if not remaining_records:
            print("所有记录已处理完成！")
            return
        
        # 创建输出目录
        output_dir = os.path.dirname(self.output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 分批处理（每批20个并发）
        batch_size = self.max_concurrent
        total_batches = (len(remaining_records) + batch_size - 1) // batch_size
        
        print(f"开始处理，每批{batch_size}个并发，共{total_batches}批")
        
        async with ClientSession() as session:
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min((batch_num + 1) * batch_size, len(remaining_records))
                batch = remaining_records[start_idx:end_idx]
                
                print(f"\n处理第{batch_num + 1}/{total_batches}批 (记录{start_idx + 1}-{end_idx})")
                
                try:
                    results = await self.process_batch(session, batch)
                    
                    # 增量保存结果
                    with open(self.output_file, 'a', encoding='utf-8') as f:
                        for result in results:
                            f.write(json.dumps(result, ensure_ascii=False) + '\n')
                    
                    print(f"第{batch_num + 1}批处理完成，成功{sum(1 for r in results if r['status'] == 'success')}个，"
                          f"失败{sum(1 for r in results if r['status'] == 'error')}个")
                    
                    # 避免API限流
                    if batch_num < total_batches - 1:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"处理第{batch_num + 1}批时出错: {e}")
                    continue
        
        print(f"\n分析完成！结果保存到: {self.output_file}")
    
    def generate_summary_report(self):
        """生成汇总报告"""
        if not os.path.exists(self.output_file):
            print("结果文件不存在，请先运行分析")
            return
        
        results = []
        with open(self.output_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        print(f"\n=== 分析结果汇总 ===")
        print(f"总处理记录数: {len(results)}")
        
        successful = [r for r in results if r['status'] == 'success']
        failed = [r for r in results if r['status'] == 'error']
        
        print(f"成功: {len(successful)}")
        print(f"失败: {len(failed)}")
        
        if successful:
            # 统计步骤分布
            step_counts = {}
            for result in successful:
                for step in result.get('important_steps', []):
                    step_counts[step] = step_counts.get(step, 0) + 1
            
            print(f"\n重要步骤分布:")
            for step in sorted(step_counts.keys()):
                print(f"  步骤{step}: {step_counts[step]}次")
        
        if failed:
            print(f"\n失败原因:")
            error_counts = {}
            for result in failed:
                error = result.get('error', 'unknown')[:50]
                error_counts[error] = error_counts.get(error, 0) + 1
            
            for error, count in error_counts.items():
                print(f"  {error}: {count}次")


def main():
    # 从环境变量获取API密钥
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("错误: 请设置OPENROUTER_API_KEY环境变量")
        return
    
    # 配置参数
    input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/4次数据收集_纯净.jsonl"
    output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tool_importance_analysis_results.jsonl"
    
    print("=== 工具调用重要性分析 ===")
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print(f"并发数: 20")
    
    # 创建分析器并运行
    analyzer = ToolImportanceAnalyzer(
        api_key=api_key,
        input_file=input_file,
        output_file=output_file,
        max_concurrent=20
    )
    
    # 运行分析
    asyncio.run(analyzer.run_analysis())
    
    # 生成汇总报告
    analyzer.generate_summary_report()


if __name__ == "__main__":
    main()