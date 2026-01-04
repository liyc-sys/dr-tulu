import json

def find_failed_records():
    """找出失败的记录"""
    
    print("🔍 寻找失败的评估记录:")
    print("=" * 60)
    
    # 检查DPO文件
    dpo_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    
    print(f"\n📁 DPO文件中的失败记录:")
    
    with open(dpo_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if not data.get('success', True):
                    print(f"  {data.get('sample_id')}: {data.get('error', 'Unknown error')}")
                    print(f"  final_score: {data.get('final_score')}")
            except json.JSONDecodeError:
                continue

if __name__ == "__main__":
    find_failed_records()
