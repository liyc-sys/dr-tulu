#!/usr/bin/env python3
"""
根据question过滤tool_importance_analysis_results.jsonl
只保留question存在于matched_data_1.jsonl中的记录
一次性代码
"""

import json
import os
from typing import Set, Dict, Any


def load_questions_from_matched_data(file_path: str) -> Set[str]:
    """从matched_data_1.jsonl中加载所有question"""
    questions = set()
    
    print(f"读取matched_data文件: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    record = json.loads(line)
                    question = record.get('question', '').strip()
                    if question:
                        questions.add(question)
                except Exception as e:
                    print(f"解析第{line_num}行时出错: {e}")
    
    print(f"从matched_data中加载了{len(questions)}个不重复的question")
    return questions


def filter_analysis_results(input_file: str, output_file: str, valid_questions: Set[str]):
    """过滤analysis results，只保留question在valid_questions中的记录"""
    print(f"\n读取analysis results文件: {input_file}")
    
    kept_records = []
    discarded_records = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    record = json.loads(line)
                    question = record.get('question', '').strip()
                    
                    if question in valid_questions:
                        kept_records.append(record)
                    else:
                        discarded_records.append({
                            'sample_id': record.get('sample_id', ''),
                            'question': question,
                            'reason': 'question not in matched_data_1.jsonl'
                        })
                except Exception as e:
                    print(f"解析第{line_num}行时出错: {e}")
    
    print(f"原始记录数: {len(kept_records) + len(discarded_records)}")
    print(f"保留记录数: {len(kept_records)}")
    print(f"丢弃记录数: {len(discarded_records)}")
    
    # 保存过滤后的结果
    print(f"\n保存过滤后的结果到: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        for record in kept_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    # 保存被丢弃的记录列表
    discarded_file = output_file.replace('.jsonl', '_discarded.jsonl')
    print(f"保存被丢弃的记录到: {discarded_file}")
    with open(discarded_file, 'w', encoding='utf-8') as f:
        for record in discarded_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    return kept_records, discarded_records


def main():
    # 文件路径
    matched_data_file = "/Users/liyc/Desktop/dr-tulu/交付数据/matched_data_1.jsonl"
    analysis_results_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tool_importance_analysis_results.jsonl"
    output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tool_importance_analysis_results_filtered.jsonl"
    
    print("=== 工具调用重要性分析结果过滤 ===")
    
    # 检查文件是否存在
    if not os.path.exists(matched_data_file):
        print(f"错误: 文件不存在 - {matched_data_file}")
        return
    
    if not os.path.exists(analysis_results_file):
        print(f"错误: 文件不存在 - {analysis_results_file}")
        return
    
    # 1. 加载matched_data中的所有question
    valid_questions = load_questions_from_matched_data(matched_data_file)
    
    if not valid_questions:
        print("错误: 没有从matched_data中加载到任何question")
        return
    
    # 2. 过滤analysis results
    kept_records, discarded_records = filter_analysis_results(
        analysis_results_file,
        output_file,
        valid_questions
    )
    
    # 3. 显示统计信息
    print("\n=== 过滤完成 ===")
    print(f"保留率: {len(kept_records)/(len(kept_records)+len(discarded_records))*100:.1f}%")
    
    if discarded_records:
        print(f"\n前5个被丢弃的记录示例:")
        for i, record in enumerate(discarded_records[:5], 1):
            print(f"  {i}. {record['sample_id']}: {record['question'][:80]}...")
    
    print(f"\n过滤后的文件已保存到: {output_file}")


if __name__ == "__main__":
    main()