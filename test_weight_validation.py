import json
from evaluate_with_gpt4o import RubricsEvaluator

def test_weight_validation():
    """测试权重验证功能"""
    
    # 创建测试评估器
    evaluator = RubricsEvaluator("test-api-key")
    
    print("🧪 测试权重验证功能")
    print("="*60)
    
    # 测试1: 正确的权重
    print("\n测试1: 正确的权重 (应该通过)")
    valid_rubrics = [
        {"category": "tool_use", "title": "Test 1", "description": "Test", "weight": 0.2},
        {"category": "tool_use", "title": "Test 2", "description": "Test", "weight": 0.2},
        {"category": "content", "title": "Test 3", "description": "Test", "weight": 0.3},
        {"category": "content", "title": "Test 4", "description": "Test", "weight": 0.3}
    ]
    
    try:
        result = evaluator.validate_rubrics_weights(valid_rubrics)
        print(f"结果: {'✅ 通过' if result else '❌ 失败'}")
    except Exception as e:
        print(f"❌ 异常: {e}")
    
    # 测试2: 错误的权重 (总和不为1.0)
    print("\n测试2: 错误的权重 (应该失败)")
    invalid_rubrics = [
        {"category": "tool_use", "title": "Test 1", "description": "Test", "weight": 3},
        {"category": "tool_use", "title": "Test 2", "description": "Test", "weight": 3},
        {"category": "content", "title": "Test 3", "description": "Test", "weight": 2}
    ]
    
    try:
        result = evaluator.validate_rubrics_weights(invalid_rubrics)
        print(f"结果: {'❌ 应该失败但通过了' if result else '✅ 正确识别失败'}")
    except Exception as e:
        print(f"异常: {e}")
    
    # 测试3: 使用真实数据测试
    print("\n测试3: 真实数据测试")
    
    # 加载真实的rubrics
    with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r') as f:
        first_line = f.readline()
    
    data = json.loads(first_line)
    real_rubrics = data['all_rubrics']
    
    try:
        result = evaluator.validate_rubrics_weights(real_rubrics)
        print(f"结果: {'✅ 真实数据权重正确' if result else '❌ 真实数据权重有问题'}")
    except Exception as e:
        print(f"❌ 真实数据测试异常: {e}")
    
    # 测试4: 测试create_evaluation_prompt会抛出异常
    print("\n测试4: 测试create_evaluation_prompt异常处理")
    
    try:
        prompt = evaluator.create_evaluation_prompt(
            "Test question", 
            "Test answer", 
            invalid_rubrics
        )
        print("❌ 应该抛出异常但没有")
    except ValueError as e:
        print(f"✅ 正确抛出异常: {e}")
    except Exception as e:
        print(f"❌ 抛出了其他异常: {e}")

if __name__ == "__main__":
    test_weight_validation()
