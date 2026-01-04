import json

def check_evaluation_files():
    """检查评估结果文件的实际情况"""
    
    print("🔍 检查当前评估结果文件:")
    print("=" * 60)
    
    # 检查DPO文件
    dpo_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    print(f"\n📁 DPO文件: {dpo_file}")
    
    dpo_zero_scores = 0
    dpo_normal_scores = 0
    dpo_failed = 0
    
    with open(dpo_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                score = data.get('final_score')
                error = data.get('error', '')
                
                if score == 0.0:
                    if '没有final_answer' in error:
                        dpo_zero_scores += 1
                        print(f"  0分 (无final_answer): {data['sample_id']}")
                    elif 'rubrics' in error.lower():
                        dpo_failed += 1
                        print(f"  错误记录 (rubrics问题): {data['sample_id']}")
                    else:
                        dpo_zero_scores += 1
                        print(f"  0分 (其他): {data['sample_id']} - {error}")
                else:
                    dpo_normal_scores += 1
            except json.JSONDecodeError:
                continue
    
    print(f"\nDPO统计:")
    print(f"  正常得分: {dpo_normal_scores}")
    print(f"  0分 (无final_answer): {dpo_zero_scores}")
    print(f"  错误记录: {dpo_failed}")
    print(f"  总计: {dpo_normal_scores + dpo_zero_scores + dpo_failed}")
    
    # 检查Tulu文件
    tulu_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    print(f"\n📁 Tulu文件: {tulu_file}")
    
    tulu_zero_scores = 0
    tulu_normal_scores = 0
    tulu_failed = 0
    
    with open(tulu_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                score = data.get('final_score')
                error = data.get('error', '')
                
                if score == 0.0:
                    if '没有final_answer' in error:
                        tulu_zero_scores += 1
                        print(f"  0分 (无final_answer): {data['sample_id']}")
                    elif 'rubrics' in error.lower():
                        tulu_failed += 1
                        print(f"  错误记录 (rubrics问题): {data['sample_id']}")
                    else:
                        tulu_zero_scores += 1
                        print(f"  0分 (其他): {data['sample_id']} - {error}")
                else:
                    tulu_normal_scores += 1
            except json.JSONDecodeError:
                continue
    
    print(f"\nTulu统计:")
    print(f"  正常得分: {tulu_normal_scores}")
    print(f"  0分 (无final_answer): {tulu_zero_scores}")
    print(f"  错误记录: {tulu_failed}")
    print(f"  总计: {tulu_normal_scores + tulu_zero_scores + tulu_failed}")

if __name__ == "__main__":
    check_evaluation_files()
