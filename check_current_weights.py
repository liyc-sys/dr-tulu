import json

# 检查当前pubmed_test.jsonl的第一条数据
with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
    first_line = f.readline()

data = json.loads(first_line)
all_rubrics = data['all_rubrics']

print("🔍 当前pubmed_test.jsonl的第一条数据:")
print(f"Sample ID: {data['sample_id']}")

tool_rubrics = [r for r in all_rubrics if r['category'] == 'tool_use']
content_rubrics = [r for r in all_rubrics if r['category'] == 'content']

print(f"\nTool rubrics ({len(tool_rubrics)}个):")
for r in tool_rubrics:
    print(f"  - {r['title']}: weight={r['weight']}")

print(f"\nContent rubrics ({len(content_rubrics)}个):")
for r in content_rubrics[:3]:  # 只显示前3个
    print(f"  - {r['title']}: weight={r['weight']}")

total_weight = sum(r['weight'] for r in all_rubrics)
print(f"\n总权重: {total_weight}")

# 检查是否有权重大于1的情况
large_weights = [r for r in all_rubrics if r['weight'] > 1]
if large_weights:
    print(f"\n❌ 发现 {len(large_weights)} 个rubrics的权重大于1:")
    for r in large_weights:
        print(f"  - {r['title']}: weight={r['weight']}")
else:
    print("\n✅ 没有权重大于1的rubrics")
