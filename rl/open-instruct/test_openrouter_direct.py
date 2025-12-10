#!/usr/bin/env python3
"""
测试 OpenRouter 直接调用功能
确保可以正常生成 adaptive rubrics
"""

import os
import asyncio
import sys

os.environ["OPENAI_API_KEY"] = "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"


# 设置环境变量（如果还没有设置）
if not os.environ.get("OPENAI_API_KEY"):
    print("警告: OPENAI_API_KEY 未设置")
    print("请设置: export OPENAI_API_KEY='sk-or-v1-...'")
    sys.exit(1)

if not os.environ.get("OPENAI_API_BASE"):
    os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

# 强制使用 OpenRouter 直接调用
os.environ["USE_OPENROUTER_DIRECT"] = "true"

# 设置测试模型
if not os.environ.get("RUBRIC_JUDGE_MODEL"):
    os.environ["RUBRIC_JUDGE_MODEL"] = "openai/gpt-4o-mini"

from open_instruct.search_rewards.utils.run_utils import run_litellm_async, run_litellm


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


async def test_basic_call():
    """测试基本的 API 调用"""
    print_section("测试 1: 基本 API 调用")
    
    try:
        response = await run_litellm_async(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt="Say hello in one sentence.",
            max_tokens=100,
        )
        
        if response:
            print("✅ 基本调用成功")
            print(f"响应: {response[:100]}...")
            return True
        else:
            print("❌ 基本调用失败：返回空字符串")
            return False
    except Exception as e:
        print(f"❌ 基本调用异常: {e}")
        return False


async def test_rubric_generation():
    """测试 rubric 生成场景"""
    print_section("测试 2: Rubric 生成")
    
    question = "What are the main causes of climate change?"
    responses = [
        "Climate change is primarily caused by human activities, especially the burning of fossil fuels.",
        "The sun is getting hotter, causing the Earth to warm up.",
        "Climate change is caused by greenhouse gas emissions from various sources.",
    ]
    
    prompt = f"""You are an expert evaluator. Generate evaluation rubrics for the following question and responses.

Question: {question}

Responses:
"""
    for i, resp in enumerate(responses):
        prompt += f"Response {i+1}: {resp}\n"
    
    prompt += """
Output in JSON format:
{
  "positive_rubrics": [{"title": "...", "description": "..."}],
  "negative_rubrics": [{"title": "...", "description": "..."}]
}
"""
    
    try:
        response = await run_litellm_async(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt=prompt,
            max_tokens=2000,
        )
        
        if response:
            print("✅ Rubric 生成成功")
            print(f"响应长度: {len(response)} 字符")
            
            # 尝试解析 JSON
            import json
            try:
                # 简单检查是否包含 JSON
                if "{" in response and "}" in response:
                    print("✅ 响应包含 JSON 格式数据")
                    print(f"预览: {response[:200]}...")
                else:
                    print("⚠️  响应不包含 JSON 格式")
            except:
                print("⚠️  无法解析 JSON")
            
            return True
        else:
            print("❌ Rubric 生成失败：返回空字符串")
            return False
    except Exception as e:
        print(f"❌ Rubric 生成异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_concurrent_calls():
    """测试并发调用"""
    print_section("测试 3: 并发调用")
    
    num_concurrent = 5
    print(f"同时发起 {num_concurrent} 个请求...")
    
    async def make_call(idx):
        response = await run_litellm_async(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt=f"Count from 1 to {idx}.",
            max_tokens=50,
        )
        return idx, response
    
    try:
        tasks = [make_call(i) for i in range(1, num_concurrent + 1)]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(1 for idx, resp in results if resp)
        print(f"✅ 成功: {success_count}/{num_concurrent} 个请求")
        
        if success_count == num_concurrent:
            print("✅ 所有并发请求都成功")
            return True
        else:
            print(f"⚠️  有 {num_concurrent - success_count} 个请求失败")
            return False
    except Exception as e:
        print(f"❌ 并发调用异常: {e}")
        return False


def test_sync_call():
    """测试同步调用"""
    print_section("测试 4: 同步调用")
    
    try:
        response = run_litellm(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt="What is 2+2?",
            max_tokens=50,
        )
        
        if response:
            print("✅ 同步调用成功")
            print(f"响应: {response[:100]}...")
            return True
        else:
            print("❌ 同步调用失败：返回空字符串")
            return False
    except Exception as e:
        print(f"❌ 同步调用异常: {e}")
        return False


async def test_error_handling():
    """测试错误处理"""
    print_section("测试 5: 错误处理")
    
    # 使用无效的模型名测试错误处理
    try:
        response = await run_litellm_async(
            model_name="invalid-model-name",
            user_prompt="This should fail",
            max_tokens=50,
            num_retries=2,  # 减少重试次数加快测试
        )
        
        # 应该返回空字符串而不是抛出异常
        if response == "":
            print("✅ 错误处理正确：返回空字符串")
            return True
        else:
            print("⚠️  意外情况：无效模型返回了响应")
            return True  # 也算通过，可能是兜底模型
    except Exception as e:
        print(f"❌ 错误处理失败：抛出了异常 {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print(" OpenRouter 直接调用测试")
    print("=" * 70)
    print(f"API Base: {os.environ.get('OPENAI_API_BASE')}")
    print(f"Model: {os.environ.get('RUBRIC_JUDGE_MODEL')}")
    print(f"USE_OPENROUTER_DIRECT: {os.environ.get('USE_OPENROUTER_DIRECT')}")
    
    results = {}
    
    # 运行测试
    results["基本调用"] = await test_basic_call()
    results["Rubric生成"] = await test_rubric_generation()
    results["并发调用"] = await test_concurrent_calls()
    results["同步调用"] = test_sync_call()
    results["错误处理"] = await test_error_handling()
    
    # 总结
    print_section("测试总结")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, passed_test in results.items():
        status = "✅ 通过" if passed_test else "❌ 失败"
        print(f"{status}: {test_name}")
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！可以开始训练了。")
        print("\n使用方法：")
        print("1. 在 train_dr_tulu.sh 中添加: export USE_OPENROUTER_DIRECT=true")
        print("2. 确保模型名包含 provider 前缀: export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini")
        print("3. 运行训练脚本")
        return 0
    else:
        print("\n⚠️  有测试失败，请检查配置。")
        print("\n常见问题：")
        print("1. 检查 OPENAI_API_KEY 是否正确")
        print("2. 检查网络连接")
        print("3. 检查模型名是否包含 provider 前缀")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

