import json

def debug_counting_difference():
    """调试计数差异"""
    
    print("🔍 调试计数差异问题:")
    print("=" * 60)
    
    # 检查DPO文件
    dpo_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    
    dpo_all = 0
    dpo_success = 0
    dpo_with_score = 0
    dpo_without_score = 0
    
    with open(dpo_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                dpo_all += 1
                
                success = data.get('success', False)
                has_score = data.get('final_score') is not None
                
                if success:
                    dpo_success += 1
                
                if has_score:
                    dpo_with_score += 1
                else:
                    dpo_without_score += 1
                    
            except json.JSONDecodeError:
                continue
    
    print(f"DPO文件详细统计:")
    print(f"  总记录数: {dpo_all}")
    print(f"  success=True: {dpo_success}")
    print(f"  有final_score: {dpo_with_score}")
    print(f"  无final_score: {dpo_without_score}")
    
    # 检查Tulu文件
    tulu_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    
    tulu_all = 0
    tulu_success = 0
    tulu_with_score = 0
    
    with open(tulu_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                tulu_all += 1
                
                success = data.get('success', False)
                has_score = data.get('final_score') is not None
                
                if success:
                    tulu_success += 1
                
                if has_score:
                    tulu_with_score += 1
                    
            except json.JSONDecodeError:
                continue
    
    print(f"\nTulu文件详细统计:")
    print(f"  总记录数: {tulu_all}")
    print(f"  success=True: {tulu_success}")
    print(f"  有final_score: {tulu_with_score}")

if __name__ == "__main__":
    debug_counting_difference()
