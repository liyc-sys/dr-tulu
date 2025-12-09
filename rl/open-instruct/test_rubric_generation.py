#!/usr/bin/env python3
"""
测试adaptive rubric生成功能
这个脚本模拟训练过程中的rubric生成，但不需要运行完整的训练
"""
import os
import sys
import asyncio

# 设置环境变量（从train_dr_tulu.sh复制）
os.environ["http_proxy"] = "http://httpproxy.glm.ai:8888"
os.environ["https_proxy"] = "http://httpproxy.glm.ai:8888"
os.environ["no_proxy"] = "127.0.0.1,localhost,platform.glm.ai,::1"
os.environ["OPENAI_API_KEY"] = "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"
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
os.environ["RUBRIC_JUDGE_MODEL"] = "gpt-4.1-mini"
os.environ["RUBRIC_GENERATION_MODEL"] = "gpt-4.1-mini"

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from open_instruct.search_rewards.utils.rubric_utils import generate_instance_wise_adaptive_rubrics


async def test_rubric_generation_simple():
    """测试1: 简单的rubric生成"""
    print("=" * 60)
    print("测试1: 简单问题的Rubric生成")
    print("=" * 60)
    
    question = "What is the capital of France?"
    responses = [
        "The capital of France is Paris.",
        "Paris is the capital city of France, known for the Eiffel Tower.",
        "France's capital is Paris, a major European city.",
    ]
    
    print(f"\n问题: {question}")
    print(f"响应数量: {len(responses)}")
    
    try:
        result = await generate_instance_wise_adaptive_rubrics(
            question=question,
            response_list=responses,
            existing_rubrics=None,
            model_name=os.environ.get("RUBRIC_GENERATION_MODEL", "gpt-4.1-mini")
        )
        
        if result is None:
            print("❌ Rubric生成返回None")
            return False
        else:
            print("✅ Rubric生成成功!")
            print(f"结果: {result}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rubric_generation_with_existing():
    """测试2: 带有existing rubrics的生成"""
    print("\n" + "=" * 60)
    print("测试2: 带有Existing Rubrics的生成")
    print("=" * 60)
    
    question = "Explain quantum entanglement."
    responses = [
        "Quantum entanglement is when particles are connected.",
        "It's a quantum phenomenon where particles remain connected regardless of distance.",
    ]
    
    existing_rubrics = """
    - Accuracy: Response must be scientifically accurate
    - Clarity: Explanation should be clear and understandable
    """
    
    print(f"\n问题: {question}")
    print(f"Existing rubrics: {existing_rubrics}")
    
    try:
        result = await generate_instance_wise_adaptive_rubrics(
            question=question,
            response_list=responses,
            existing_rubrics=existing_rubrics,
            model_name=os.environ.get("RUBRIC_GENERATION_MODEL", "gpt-4.1-mini")
        )
        
        if result is None:
            print("❌ Rubric生成返回None")
            return False
        else:
            print("✅ Rubric生成成功!")
            print(f"结果: {result}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_litellm_direct():
    """测试3: 直接测试litellm连接"""
    print("\n" + "=" * 60)
    print("测试3: 直接测试LiteLLM连接")
    print("=" * 60)
    
    from open_instruct.search_rewards.utils.run_utils import run_litellm_async
    
    try:
        response = await run_litellm_async(
            model_name="gpt-4.1-mini",
            user_prompt="Say 'Hello' and nothing else.",
            max_tokens=10,
            timeout=30
        )
        
        if response == "":
            print("❌ LiteLLM返回空字符串（连接失败）")
            return False
        else:
            print(f"✅ LiteLLM连接成功! 响应: {response}")
            return True
            
    except Exception as e:
        print(f"❌ LiteLLM连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_proxy_connectivity():
    """测试4: 测试代理连接性"""
    print("\n" + "=" * 60)
    print("测试4: 测试代理和网络连接")
    print("=" * 60)
    
    import subprocess
    
    # 测试代理是否可用
    print("\n检查代理服务器...")
    proxy = "http://httpproxy.glm.ai:8888"
    try:
        result = subprocess.run(
            ["curl", "-x", proxy, "-I", "https://openrouter.ai", "-m", "10"],
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode == 0:
            print(f"✅ 代理可用，可以访问OpenRouter")
            print(f"响应头: {result.stdout[:200]}")
            return True
        else:
            print(f"❌ 代理连接失败")
            print(f"错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 无法测试代理: {e}")
        return False


async def main():
    print("\n" + "=" * 70)
    print("Adaptive Rubric生成测试套件")
    print("=" * 70)
    print(f"\n配置信息:")
    print(f"  代理: {os.environ.get('http_proxy')}")
    print(f"  API Base: {os.environ.get('OPENAI_API_BASE')}")
    print(f"  模型: {os.environ.get('RUBRIC_GENERATION_MODEL')}")
    print("=" * 70)
    
    results = {}
    
    # 按顺序执行测试
    print("\n开始测试...\n")
    
    results["proxy"] = await test_proxy_connectivity()
    results["litellm"] = await test_litellm_direct()
    results["simple_rubric"] = await test_rubric_generation_simple()
    results["rubric_with_existing"] = await test_rubric_generation_with_existing()
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name:30s}: {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    print(f"\n通过率: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过! adaptive rubric功能正常。")
    elif results.get("proxy") and results.get("litellm"):
        print("\n⚠️  基础连接正常，但rubric生成失败。")
        print("可能原因:")
        print("  - Prompt太长导致超时")
        print("  - JSON解析失败")
        print("  - 模型响应格式不符合预期")
    else:
        print("\n❌ 连接测试失败!")
        print("\n诊断建议:")
        if not results.get("proxy"):
            print("  1. 检查代理服务器是否可用")
            print("     命令: curl -x http://httpproxy.glm.ai:8888 https://openrouter.ai")
        if not results.get("litellm"):
            print("  2. 验证OpenRouter API key")
            print("  3. 检查OPENAI_API_BASE设置")
            print("  4. 尝试不使用代理（注释掉proxy设置）")
        
        print("\n可以尝试的修复:")
        print("  - 在train_dr_tulu.sh中注释掉proxy设置，直接连接")
        print("  - 更换API key")
        print("  - 使用其他模型（如gpt-4o-mini）")


if __name__ == "__main__":
    asyncio.run(main())

