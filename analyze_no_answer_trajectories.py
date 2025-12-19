#!/usr/bin/env python3
"""分析没有answer标签的trajectory停留在什么位置"""
import json
import re

def analyze_no_answer(file_path):
    """分析没有answer标签的trajectory"""
    
    no_answer_cases = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
                
            try:
                data = json.loads(line)
                trajectory = data.get('trajectory', {})
                interleaved_text = trajectory.get('interleaved_text', '')
                
                has_open = '<answer>' in interleaved_text
                has_close = '</answer>' in interleaved_text
                
                if not has_open and not has_close:
                    # 分析最后的内容
                    total_tool_calls = trajectory.get('total_tool_calls', 0)
                    
                    # 检查最后是什么内容
                    last_500 = interleaved_text[-500:] if len(interleaved_text) > 500 else interleaved_text
                    
                    # 检查是否以tool_output结尾
                    ends_with_tool_output = interleaved_text.rstrip().endswith('</tool_output>')
                    
                    # 检查是否有未完成的reasoning
                    has_reasoning = '<think>' in last_500
                    has_unclosed_reasoning = last_500.count('<think>') > last_500.count('</think>')
                    
                    # 检查是否有call_tool
                    has_call_tool = '<call_tool' in last_500
                    has_unclosed_call_tool = last_500.count('<call_tool') > last_500.count('</call_tool>')
                    
                    # 提取最后几个部分
                    parts = []
                    if '<tool_output>' in interleaved_text:
                        tool_outputs = interleaved_text.split('<tool_output>')
                        for i, part in enumerate(tool_outputs[-3:], len(tool_outputs)-2):
                            if i > 0:  # 跳过第一个（没有tool_output前缀的部分）
                                parts.append(f"tool_output_{i}: {part[:200]}")
                    
                    no_answer_cases.append({
                        'line': line_num,
                        'question': data.get('question', '')[:80],
                        'total_tool_calls': total_tool_calls,
                        'ends_with_tool_output': ends_with_tool_output,
                        'has_reasoning': has_reasoning,
                        'has_unclosed_reasoning': has_unclosed_reasoning,
                        'has_call_tool': has_call_tool,
                        'has_unclosed_call_tool': has_unclosed_call_tool,
                        'last_500': last_500,
                        'interleaved_length': len(interleaved_text)
                    })
                    
            except Exception as e:
                print(f"Line {line_num}: Error: {e}")
    
    return no_answer_cases

def print_analysis(cases):
    """打印分析结果"""
    print("=" * 80)
    print(f"没有answer标签的trajectory分析 (共{len(cases)}条)")
    print("=" * 80)
    
    # 统计停止位置
    ends_with_tool_output = sum(1 for c in cases if c['ends_with_tool_output'])
    has_reasoning = sum(1 for c in cases if c['has_reasoning'])
    has_unclosed_reasoning = sum(1 for c in cases if c['has_unclosed_reasoning'])
    has_call_tool = sum(1 for c in cases if c['has_call_tool'])
    has_unclosed_call_tool = sum(1 for c in cases if c['has_unclosed_call_tool'])
    
    print(f"\n停止位置统计:")
    print(f"  以 </tool_output> 结尾: {ends_with_tool_output} ({ends_with_tool_output/len(cases)*100:.1f}%)")
    print(f"  最后部分包含 reasoning: {has_reasoning} ({has_reasoning/len(cases)*100:.1f}%)")
    print(f"  有未闭合的 reasoning: {has_unclosed_reasoning} ({has_unclosed_reasoning/len(cases)*100:.1f}%)")
    print(f"  最后部分包含 call_tool: {has_call_tool} ({has_call_tool/len(cases)*100:.1f}%)")
    print(f"  有未闭合的 call_tool: {has_unclosed_call_tool} ({has_unclosed_call_tool/len(cases)*100:.1f}%)")
    
    # 工具调用次数分布
    tool_call_dist = {}
    for case in cases:
        tc = case['total_tool_calls']
        tool_call_dist[tc] = tool_call_dist.get(tc, 0) + 1
    
    print(f"\n工具调用次数分布:")
    for tc in sorted(tool_call_dist.keys()):
        print(f"  {tc} 次: {tool_call_dist[tc]} 条")
    
    # 显示典型案例
    print("\n" + "=" * 80)
    print("典型案例 (前10个):")
    print("=" * 80)
    for i, case in enumerate(cases[:10], 1):
        print(f"\n[{i}] Line {case['line']}")
        print(f"问题: {case['question']}")
        print(f"工具调用次数: {case['total_tool_calls']}")
        print(f"停止位置: ", end="")
        if case['ends_with_tool_output']:
            print("以 </tool_output> 结尾")
        elif case['has_unclosed_call_tool']:
            print("有未闭合的 <call_tool>")
        elif case['has_unclosed_reasoning']:
            print("有未闭合的 <think>")
        else:
            print("其他")
        print(f"最后500字符:")
        print("-" * 80)
        print(case['last_500'])
        print("-" * 80)

if __name__ == '__main__':
    file_path = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_060613_no_rubrics_incremental.jsonl'
    cases = analyze_no_answer(file_path)
    print_analysis(cases)

