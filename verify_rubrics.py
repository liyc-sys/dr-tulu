import json

# 快速验证新权重设计
with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
    first_line = f.readline()

data = json.loads(first_line)
all_rubrics = data['all_rubrics']

print("🔍 验证新的权重设计:")
print(f"总rubrics数量: {len(all_rubrics)}")

tool_rubrics = [r for r in all_rubrics if r['category'] == 'tool_use']
content_rubrics = [r for r in all_rubrics if r['category'] == 'content']

print(f"\nTool rubrics ({len(tool_rubrics)}个，每个0.2):")
for r in tool_rubrics:
    print(f"  - {r['title']} (weight: {r['weight']})")

print(f"\nContent rubrics ({len(content_rubrics)}个，总weight=0.6):")
for r in content_rubrics:
    print(f"  - {r['title']} (weight: {r['weight']})")

total_weight = sum(r['weight'] for r in all_rubrics)
print(f"\n总权重: {total_weight:.3f}")

tool_weight = sum(r['weight'] for r in tool_rubrics)
content_weight = sum(r['weight'] for r in content_rubrics)

print(f"\n详细验证:")
print(f"Tool总权重: {tool_weight:.1f} (应该是0.4)")
print(f"Content总权重: {content_weight:.1f} (应该是0.6)")
print(f"总权重: {total_weight:.1f} (应该是1.0)")

if (abs(tool_weight - 0.4) < 0.01 and 
    abs(content_weight - 0.6) < 0.01 and 
    abs(total_weight - 1.0) < 0.01):
    print("✅ 权重设计正确!")
else:
    print("❌ 权重设计有问题!")
