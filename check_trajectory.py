import json

input_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl'

with open(input_file, 'r', encoding='utf-8') as f:
    line = f.readline()
    data = json.loads(line.strip())
    
    print("trajectory字段的类型:", type(data.get('trajectory')))
    
    if isinstance(data.get('trajectory'), dict):
        print("trajectory字典的键:")
        for key in data['trajectory'].keys():
            print(f"  - {key}")
            # 检查是否有final_answer相关的字段
            if 'final' in key.lower() or 'answer' in key.lower():
                print(f"    找到可能的答案字段: {key}")

