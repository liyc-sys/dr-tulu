import json

# 读取第一行数据
with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
    first_line = f.readline()

data = json.loads(first_line)
trajectory = data['trajectory']
final_answer = trajectory['final_answer']

print("=== 原始pubmed_test.jsonl第一条数据的final_answer ===")
print(final_answer[:1000])
print("\n...[截断]...")
print("\n=== 查找cite标签 ===")

import re
cite_matches = re.findall(r'<cite[^>]*>.*?</cite>', final_answer, re.DOTALL)
print(f"共找到 {len(cite_matches)} 个引用")

print("\n前3个引用的完整内容:")
for i, cite in enumerate(cite_matches[:3]):
    # 提取cite内容
    cite_content = re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', cite, flags=re.DOTALL)
    print(f"\n引用 {i+1}:")
    print(cite_content[:300])
