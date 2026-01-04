import json

input_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'

with open(input_file, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 2:  # 只看前2行
            data = json.loads(line.strip())
            print(f"第{i+1}行的字段:")
            for key in data.keys():
                print(f"  - {key}")
            
            # 检查是否有all_rubrics字段
            if 'all_rubrics' in data:
                print(f"  all_rubrics内容: {data['all_rubrics']}")
            
            # 检查question字段
            if 'question' in data:
                print(f"  question: {data['question'][:100]}...")  # 只显示前100个字符
            
            print()

