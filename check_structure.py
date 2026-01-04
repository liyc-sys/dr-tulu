import json

input_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl'

with open(input_file, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 3:  # 只看前3行
            data = json.loads(line.strip())
            print(f"第{i+1}行的字段:")
            for key in data.keys():
                print(f"  - {key}")
            print()

