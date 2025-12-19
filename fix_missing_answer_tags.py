#!/usr/bin/env python3
"""
独立修复脚本：修复trajectory中缺失的answer标签
不需要调用工具，只需要基于现有内容补充完整的trajectory
"""
import json
import re
from typing import Dict, List, Optional
from pathlib import Path

def extract_pmids_from_text(text: str) -> List[str]:
    """从文本中提取PMID"""
    # 从snippet id中提取
    pmids = re.findall(r'<snippet\s+id="(\d+)"', text)
    # 从cite标签中提取
    pmids.extend(re.findall(r'<cite\s+id="(\d+)"', text))
    return list(set(pmids))

def extract_tool_output_summary(interleaved_text: str) -> str:
    """从interleaved_text中提取工具输出的摘要信息"""
    summaries = []
    
    # 提取所有tool_output块
    tool_outputs = re.findall(r'<tool_output>(.*?)</tool_output>', interleaved_text, re.DOTALL)
    
    for output in tool_outputs:
        # 提取snippet信息
        snippets = re.findall(r'<snippet\s+id="(\d+)">Title:\s*(.*?)\n', output, re.DOTALL)
        if snippets:
            for pmid, title in snippets[:3]:  # 只取前3个
                title_clean = title.strip().split('\n')[0]  # 只取第一行
                summaries.append(f"PMID {pmid}: {title_clean}")
    
    return "\n".join(summaries[:5])  # 最多5个

def generate_answer_from_tool_outputs(question: str, interleaved_text: str, tool_calls: List[Dict]) -> str:
    """基于工具输出生成答案"""
    
    # 提取所有PMID
    pmids = extract_pmids_from_text(interleaved_text)
    
    # 提取工具输出摘要
    tool_summary = extract_tool_output_summary(interleaved_text)
    
    # 检查是否有足够的工具输出
    if not tool_summary and not pmids:
        # 如果没有任何工具输出，生成一个简单的说明
        return f"Based on the available information, I was unable to find sufficient evidence to provide a comprehensive answer to: {question}. Further research may be needed."
    
    # 构建答案
    answer_parts = []
    
    # 如果有工具调用，说明有搜索结果
    if tool_calls:
        answer_parts.append(f"Based on the PubMed search results, here is what I found regarding: {question}")
        answer_parts.append("")
        
        if tool_summary:
            answer_parts.append("## Key Findings")
            answer_parts.append("")
            # 从工具输出中提取关键信息
            snippets = re.findall(r'<snippet\s+id="(\d+)">Title:\s*(.*?)\nAuthors:.*?Abstract:\s*(.*?)(?:</snippet>|$)', interleaved_text, re.DOTALL)
            
            for i, (pmid, title, abstract) in enumerate(snippets[:3], 1):
                title_clean = title.strip().split('\n')[0]
                abstract_clean = abstract.strip()[:300] + "..." if len(abstract.strip()) > 300 else abstract.strip()
                answer_parts.append(f"### {i}. {title_clean}")
                answer_parts.append(f"<cite id=\"{pmid}\">{abstract_clean}</cite>")
                answer_parts.append("")
        else:
            answer_parts.append("The search results indicate relevant information is available, but detailed content extraction was limited.")
            answer_parts.append("")
    else:
        # 没有工具调用，生成一个说明
        answer_parts.append(f"Regarding your question: {question}")
        answer_parts.append("")
        answer_parts.append("I was unable to retrieve sufficient information to provide a detailed answer. Additional research or tool calls may be needed to address this question comprehensively.")
    
    # 添加引用
    if pmids:
        answer_parts.append("## References")
        answer_parts.append("")
        for pmid in pmids[:5]:  # 最多5个引用
            answer_parts.append(f"<cite id=\"{pmid}\">PMID {pmid}</cite>")
    
    return "\n".join(answer_parts)

def fix_trajectory(data: Dict) -> Optional[Dict]:
    """修复单个trajectory的answer标签问题"""
    
    trajectory = data.get('trajectory', {})
    interleaved_text = trajectory.get('interleaved_text', '')
    final_answer = trajectory.get('final_answer', '')
    tool_calls = trajectory.get('tool_calls', [])
    question = trajectory.get('question', data.get('question', ''))
    
    has_open = '<answer>' in interleaved_text
    has_close = '</answer>' in interleaved_text
    
    modified = False
    
    # 情况1: 只有<answer>没有</answer>
    if has_open and not has_close:
        # 提取已有的答案内容
        answer_start_idx = interleaved_text.find('<answer>')
        answer_content = interleaved_text[answer_start_idx + 8:]  # 8 = len('<answer>')
        
        # 如果final_answer为空，使用提取的内容
        if not final_answer:
            final_answer = answer_content.strip()
        
        # 补充结束标签
        interleaved_text = interleaved_text + '</answer>'
        modified = True
        print(f"  ✓ 补充缺失的 </answer> 标签")
    
    # 情况2: 完全没有标签
    elif not has_open and not has_close:
        # 生成答案
        if not final_answer:
            final_answer = generate_answer_from_tool_outputs(question, interleaved_text, tool_calls)
        
        # 检查interleaved_text是否以</tool_output>结尾
        if interleaved_text.rstrip().endswith('</tool_output>'):
            # 在</tool_output>后添加answer
            interleaved_text = interleaved_text + '\n<answer>' + final_answer + '</answer>'
        elif interleaved_text.strip():
            # 如果interleaved_text不为空，直接添加
            interleaved_text = interleaved_text + '\n<answer>' + final_answer + '</answer>'
        else:
            # 如果interleaved_text为空，创建基本的轨迹
            interleaved_text = '<answer>' + final_answer + '</answer>'
        
        modified = True
        print(f"  ✓ 添加缺失的 <answer>...</answer> 标签")
    
    # 更新trajectory
    if modified:
        trajectory['interleaved_text'] = interleaved_text
        trajectory['final_answer'] = final_answer
        
        # 更新pmids_cited（从interleaved_text中提取）
        pmids_cited = extract_pmids_from_text(interleaved_text)
        trajectory['pmids_cited'] = list(set(pmids_cited))
        
        # 更新data中的trajectory
        data['trajectory'] = trajectory
        
        return data
    
    return None

def fix_jsonl_file(input_file: str, output_file: str):
    """修复JSONL文件中的所有trajectory"""
    
    fixed_count = 0
    total_count = 0
    issues = {
        'only_open_tag': 0,
        'no_tags': 0,
        'fixed': 0
    }
    
    print(f"正在处理文件: {input_file}")
    print("=" * 80)
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for line_num, line in enumerate(f_in, 1):
            if not line.strip():
                continue
            
            try:
                data = json.loads(line)
                total_count += 1
                
                trajectory = data.get('trajectory', {})
                interleaved_text = trajectory.get('interleaved_text', '')
                
                has_open = '<answer>' in interleaved_text
                has_close = '</answer>' in interleaved_text
                
                # 检查是否需要修复
                needs_fix = False
                if has_open and not has_close:
                    issues['only_open_tag'] += 1
                    needs_fix = True
                elif not has_open and not has_close:
                    issues['no_tags'] += 1
                    needs_fix = True
                
                if needs_fix:
                    print(f"\n[Line {line_num}] 发现问题:")
                    if has_open and not has_close:
                        print(f"  类型: 只有<answer>没有</answer>")
                    else:
                        print(f"  类型: 完全没有标签")
                    print(f"  问题: {data.get('question', '')[:80]}")
                    
                    fixed_data = fix_trajectory(data)
                    if fixed_data:
                        issues['fixed'] += 1
                        fixed_count += 1
                        data = fixed_data
                
                # 写入修复后的数据
                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                
            except json.JSONDecodeError as e:
                print(f"Line {line_num}: JSON decode error: {e}")
                # 仍然写入原行
                f_out.write(line)
            except Exception as e:
                print(f"Line {line_num}: Error: {e}")
                import traceback
                traceback.print_exc()
                # 仍然写入原行
                f_out.write(line)
    
    print("\n" + "=" * 80)
    print("修复完成!")
    print("=" * 80)
    print(f"总计: {total_count} 条trajectory")
    print(f"需要修复: {issues['only_open_tag'] + issues['no_tags']} 条")
    print(f"  - 只有<answer>没有</answer>: {issues['only_open_tag']} 条")
    print(f"  - 完全没有标签: {issues['no_tags']} 条")
    print(f"成功修复: {issues['fixed']} 条")
    print(f"\n输出文件: {output_file}")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python fix_missing_answer_tags.py <input_file> [output_file]")
        print("\n示例:")
        print("  python fix_missing_answer_tags.py input.jsonl output.jsonl")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.jsonl', '_fixed.jsonl')
    
    if not Path(input_file).exists():
        print(f"错误: 文件不存在: {input_file}")
        sys.exit(1)
    
    fix_jsonl_file(input_file, output_file)

