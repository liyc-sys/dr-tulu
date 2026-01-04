import json
from collections import defaultdict

def verify_all_rubrics():
    """验证所有147条数据的rubrics设计"""
    
    print("🔍 验证所有数据的rubrics权重设计...")
    print("="*60)
    
    issues = []
    rubric_distribution = defaultdict(int)
    content_weight_distribution = defaultdict(int)
    
    with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
        for i, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                all_rubrics = data.get('all_rubrics', [])
                
                # 分类统计
                tool_rubrics = [r for r in all_rubrics if r['category'] == 'tool_use']
                content_rubrics = [r for r in all_rubrics if r['category'] == 'content']
                
                # 统计rubric数量分布
                rubric_distribution[len(all_rubrics)] += 1
                content_weight_distribution[len(content_rubrics)] += 1
                
                # 验证tool rubrics
                if len(tool_rubrics) != 2:
                    issues.append(f"行{i}: tool rubrics数量错误，应该是2个，实际是{len(tool_rubrics)}个")
                
                # 验证tool rubrics权重
                for r in tool_rubrics:
                    if abs(r['weight'] - 0.2) > 0.001:  # 允许小数精度误差
                        issues.append(f"行{i}: tool rubric '{r['title']}'权重错误，应该是0.2，实际是{r['weight']}")
                
                # 验证content rubrics总权重
                content_total_weight = sum(r['weight'] for r in content_rubrics)
                if abs(content_total_weight - 0.6) > 0.001:
                    issues.append(f"行{i}: content rubrics总权重错误，应该是0.6，实际是{content_total_weight:.3f}")
                
                # 验证每个content rubric的权重是否相等（允许浮点数误差）
                if content_rubrics:
                    weights = [r['weight'] for r in content_rubrics]
                    # 检查权重是否基本相等（允许1e-10的误差）
                    first_weight = weights[0]
                    weights_equal = all(abs(w - first_weight) < 1e-10 for w in weights)
                    if not weights_equal:
                        issues.append(f"行{i}: content rubrics权重不相等，{weights}")
                
                # 验证总权重
                total_weight = sum(r['weight'] for r in all_rubrics)
                if abs(total_weight - 1.0) > 0.001:
                    issues.append(f"行{i}: 总权重错误，应该是1.0，实际是{total_weight:.3f}")
                
            except json.JSONDecodeError:
                issues.append(f"行{i}: JSON解析错误")
            except Exception as e:
                issues.append(f"行{i}: 处理错误 - {e}")
    
    # 显示统计结果
    print(f"📊 Rubrics数量分布:")
    for count, freq in sorted(rubric_distribution.items()):
        print(f"   {count}个rubrics: {freq}个问题")
    
    print(f"\n📊 Content rubrics数量分布:")
    for count, freq in sorted(content_weight_distribution.items()):
        expected_weight = round(0.6 / count, 3)
        print(f"   {count}个content rubrics: {freq}个问题 (每个weight={expected_weight})")
    
    print(f"\n" + "="*60)
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for issue in issues[:20]:  # 只显示前20个问题
            print(f"   {issue}")
        if len(issues) > 20:
            print(f"   ... 还有 {len(issues)-20} 个问题")
    else:
        print("✅ 所有147条数据的rubrics设计都正确!")
        print("   - Tool rubrics: 每个问题都是2个，每个weight=0.2")
        print("   - Content rubrics: 总weight=0.6，根据数量平均分配")
        print("   - 总权重: 每个问题都是1.0")

if __name__ == "__main__":
    verify_all_rubrics()
