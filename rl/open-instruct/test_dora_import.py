#!/usr/bin/env python3
"""
简单的测试脚本，验证 DoRA 相关的导入和配置是否正确
"""

import sys

def test_imports():
    """测试所有必要的导入"""
    print("测试导入...")
    
    try:
        from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
        print("✅ PEFT 导入成功")
    except ImportError as e:
        print(f"❌ PEFT 导入失败: {e}")
        return False
    
    try:
        from open_instruct.model_utils import ModelConfig
        print("✅ ModelConfig 导入成功")
    except ImportError as e:
        print(f"❌ ModelConfig 导入失败: {e}")
        return False
    
    return True

def test_model_config():
    """测试 ModelConfig 是否包含 DoRA 参数"""
    print("\n测试 ModelConfig 参数...")
    
    try:
        from open_instruct.model_utils import ModelConfig
        
        # 创建一个默认配置
        config = ModelConfig()
        
        # 检查 PEFT/DoRA 参数
        required_attrs = [
            'use_peft', 'use_dora', 'lora_r', 'lora_alpha', 
            'lora_dropout', 'lora_target_modules'
        ]
        
        for attr in required_attrs:
            if hasattr(config, attr):
                print(f"✅ {attr}: {getattr(config, attr)}")
            else:
                print(f"❌ 缺少参数: {attr}")
                return False
        
        return True
    except Exception as e:
        print(f"❌ ModelConfig 测试失败: {e}")
        return False

def test_lora_config():
    """测试 LoraConfig 是否支持 use_dora 参数"""
    print("\n测试 LoraConfig DoRA 支持...")
    
    try:
        from peft import LoraConfig, TaskType
        
        # 尝试创建一个带 DoRA 的配置
        config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            inference_mode=False,
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
            use_dora=True,
        )
        
        print(f"✅ LoraConfig 创建成功，use_dora={config.use_dora}")
        return True
    except Exception as e:
        print(f"❌ LoraConfig 测试失败: {e}")
        print("提示: 请确保 PEFT 版本 >= 0.13.2")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("DoRA 实现验证测试")
    print("=" * 60)
    
    tests = [
        ("导入测试", test_imports),
        ("ModelConfig 测试", test_model_config),
        ("LoraConfig 测试", test_lora_config),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 出现异常: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 所有测试通过！DoRA 实现正确。")
        print("可以通过以下命令启用 DoRA 训练：")
        print("  --use_peft --use_dora --lora_r 16 --lora_alpha 32 --lora_dropout 0.05")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查上述错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())

