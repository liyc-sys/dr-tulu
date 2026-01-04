import asyncio
from evaluate_with_gpt4o import RubricsEvaluator

async def test_full_validation():
    """测试完整的验证流程"""
    
    API_KEY = "test"  # 测试用，不会真实调用API
    
    print("🧪 测试完整的权重验证流程")
    print("="*60)
    
    evaluator = RubricsEvaluator(API_KEY)
    
    # 加载rubrics
    print("📋 加载rubrics...")
    rubrics_map = evaluator.load_rubrics('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl')
    
    print(f"📊 统计:")
    print(f"   总问题数: {len(rubrics_map)}")
    
    # 验证所有rubrics的权重
    print(f"\n🔍 验证所有rubrics的权重...")
    
    validation_results = {
        "valid": 0,
        "invalid": 0,
        "total": len(rubrics_map)
    }
    
    for question, rubrics in rubrics_map.items():
        if evaluator.validate_rubrics_weights(rubrics):
            validation_results["valid"] += 1
        else:
            validation_results["invalid"] += 1
            print(f"❌ 权重异常问题: {question[:80]}...")
    
    print(f"\n📋 验证结果:")
    print(f"   总数: {validation_results['total']}")
    print(f"   有效: {validation_results['valid']}")
    print(f"   无效: {validation_results['invalid']}")
    print(f"   通过率: {validation_results['valid']/validation_results['total']*100:.1f}%")
    
    if validation_results["invalid"] == 0:
        print(f"\n✅ 所有rubrics权重验证通过，可以安全运行评估!")
    else:
        print(f"\n❌ 发现{validation_results['invalid']}个权重异常问题，需要修复后再运行评估!")
        raise ValueError(f"Rubrics权重验证失败，无法继续评估!")

if __name__ == "__main__":
    try:
        asyncio.run(test_full_validation())
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
