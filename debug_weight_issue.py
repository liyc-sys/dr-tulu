import json

print("🔍 检查所有147条数据的rubrics权重...")

large_weight_issues = []
total_weight_issues = []

with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
    for i, line in enumerate(f, 1):
        try:
            data = json.loads(line.strip())
            all_rubrics = data.get('all_rubrics', [])
            
            # 检查是否有权重大于1的rubrics
            large_weights = [r for r in all_rubrics if r['weight'] > 1]
            if large_weights:
                large_weight_issues.append({
                    'line': i,
                    'sample_id': data.get('sample_id'),
                    'large_weights': [(r['title'], r['weight']) for r in large_weights]
                })
            
            # 检查总权重
            total_weight = sum(r['weight'] for r in all_rubrics)
            if abs(total_weight - 1.0) > 0.01:  # 允许小误差
                total_weight_issues.append({
                    'line': i,
                    'sample_id': data.get('sample_id'),
                    'total_weight': total_weight
                })
                
        except json.JSONDecodeError:
            continue

if large_weight_issues:
    print(f"❌ 发现 {len(large_weight_issues)} 条数据有权重大于1的rubrics:")
    for issue in large_weight_issues[:5]:  # 只显示前5个
        print(f"  行{issue['line']} ({issue['sample_id']}):")
        for title, weight in issue['large_weights']:
            print(f"    - {title}: weight={weight}")
else:
    print("✅ 没有权重大于1的rubrics")

if total_weight_issues:
    print(f"\n❌ 发现 {len(total_weight_issues)} 条数据的总权重不等于1.0:")
    for issue in total_weight_issues[:5]:
        print(f"  行{issue['line']} ({issue['sample_id']}): total_weight={issue['total_weight']:.3f}")
else:
    print("✅ 所有数据的总权重都等于1.0")

print(f"\n📊 总结:")
print(f"   检查了147条数据")
print(f"   权重大于1的问题: {len(large_weight_issues)}条")
print(f"   总权重异常的问题: {len(total_weight_issues)}条")
