import json
from pathlib import Path

def cleanup_wrong_zero_scores(input_file: str, output_file: str):
    """
    清理错误生成的0分记录
    删除那些因为"未找到对应的rubrics"而被错误计入0分的记录
    """
    
    if not Path(input_file).exists():
        print(f"❌ 文件不存在: {input_file}")
        return
    
    print(f"🔍 清理文件: {input_file}")
    
    valid_records = []
    removed_count = 0
    total_count = 0
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                total_count += 1
                
                # 检查是否是错误的0分记录
                error_msg = data.get('error', '')
                if ('未找到对应的rubrics' in error_msg or 
                    '无rubrics' in error_msg or
                    (data.get('final_score') == 0.0 and 'rubrics' in error_msg.lower())):
                    print(f"🗑️  删除错误记录: {data.get('sample_id')} - {error_msg}")
                    removed_count += 1
                else:
                    valid_records.append(data)
                    
            except json.JSONDecodeError:
                continue
    
    # 保存清理后的数据
    with open(output_file, 'w', encoding='utf-8') as f:
        for record in valid_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    print(f"\n📊 清理结果:")
    print(f"   原始记录数: {total_count}")
    print(f"   删除记录数: {removed_count}")
    print(f"   保留记录数: {len(valid_records)}")
    print(f"📁 清理后文件: {output_file}")

def main():
    # 清理DPO结果
    print("=" * 60)
    print("清理 DPO 评估结果")
    print("=" * 60)
    
    dpo_input = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    dpo_output = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results_cleaned.jsonl'
    
    cleanup_wrong_zero_scores(dpo_input, dpo_output)
    
    # 清理Tulu结果
    print("\n" + "=" * 60)
    print("清理 Tulu 评估结果")
    print("=" * 60)
    
    tulu_input = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    tulu_output = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results_cleaned.jsonl'
    
    cleanup_wrong_zero_scores(tulu_input, tulu_output)
    
    print("\n" + "=" * 60)
    print("✅ 清理完成!")
    print("💡 下一步:")
    print("   1. 检查清理后的文件是否正确")
    print("   2. 如果满意，可以用清理后的文件替换原文件:")
    print(f"      mv {dpo_output} {dpo_input}")
    print(f"      mv {tulu_output} {tulu_input}")
    print("=" * 60)

if __name__ == "__main__":
    main()
