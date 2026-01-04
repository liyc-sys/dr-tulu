import re

def show_sample_answers(file_path, model_name, num_samples=3):
    """
    显示前几个答案样本，手动检查引用格式
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分割不同的问答条目
    entries = content.split('=' * 80)
    
    print(f"\n=== {model_name} 样本分析 ===")
    
    count = 0
    for entry in entries:
        if 'FINAL ANSWER:' not in entry:
            continue
            
        if count >= num_samples:
            break
            
        count += 1
        
        # 提取question和final_answer
        question_match = re.search(r'QUESTION:(.*?)FINAL ANSWER:', entry, re.DOTALL)
        final_answer_match = re.search(r'FINAL ANSWER:(.*?)(?=RUBRICS:|$)', entry, re.DOTALL)
        
        if question_match and final_answer_match:
            question = question_match.group(1).strip()[:200] + "..."
            final_answer = final_answer_match.group(1).strip()
            
            print(f"\n--- 条目 {count} ---")
            print(f"问题: {question}")
            print(f"答案:\n{final_answer[:500]}...")
            
            # 检查引用情况
            if '(' in final_answer and 'cite' in final_answer.lower():
                print("\n✓ 检测到引用格式")
            elif re.search(r'\d{4}', final_answer):
                print("✓ 检测到年份")
            else:
                print("✗ 未检测到明显引用")

# 检查两个文件
dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_final_answers.txt'
tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_final_answers.txt'

show_sample_answers(dporollout_file, "DPO Rollout", 2)
show_sample_answers(tulurollout_file, "Tulu Rollout", 2)
