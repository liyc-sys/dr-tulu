#!/usr/bin/env python3
"""
简单测试脚本：测试LiteLLM与OpenRouter的连接
用于诊断adaptive rubric生成失败的问题
"""
import os
import asyncio
import litellm

# 从train_dr_tulu.sh中复制的环境变量设置
# os.environ["http_proxy"] = "http://httpproxy.glm.ai:8888"
# os.environ["https_proxy"] = "http://httpproxy.glm.ai:8888"
# os.environ["no_proxy"] = "127.0.0.1,localhost,platform.glm.ai,::1"

os.environ["OPENROUTER_API_KEY"] = "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"
# os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

# 测试模型
# test_model = os.environ.get("RUBRIC_JUDGE_MODEL", "openrouter/openai/gpt-4.1-mini")
# test_model = "openrouter/openai/gpt-4o-mini"
test_model = "openrouter/openai/gpt-5-mini"
# 注意前面没有openrouter是不行的
# test_model = "openai/gpt-4.1-mini"


print("=" * 60)
print("LiteLLM 连接测试")
print("=" * 60)
print(f"代理设置: {os.environ.get('http_proxy')}")
# print(f"API Base: {os.environ.get('OPENAI_API_BASE')}")
print(f"测试模型: {test_model}")
print("=" * 60)


async def test_basic_connection():
    """测试1: 基本连接测试"""
    print("\n[测试1] 基本连接测试...")
    try:
        response = await litellm.acompletion(
            model=test_model,
            messages=[{"role": "user", "content": "Hello, respond with just 'OK'"}],
            max_tokens=3000,
            timeout=30,
            num_retries=2
        )
        print(f"✅ 成功! 响应: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        print(f"错误类型: {type(e)}")
        return False


async def test_without_proxy():
    """测试2: 不使用代理的连接测试"""
    print("\n[测试2] 测试不使用代理...")
    
    # 临时移除代理
    old_http_proxy = os.environ.pop("http_proxy", None)
    old_https_proxy = os.environ.pop("https_proxy", None)
    
    try:
        response = await litellm.acompletion(
            model=test_model,
            messages=[{"role": "user", "content": "Hello, respond with just 'OK'"}],
            max_tokens=3000,
            timeout=30,
            num_retries=2
        )
        print(f"✅ 不使用代理成功! 响应: {response.choices[0].message.content}")
        result = True
    except Exception as e:
        print(f"❌ 不使用代理也失败: {e}")
        result = False
    finally:
        # 恢复代理设置
        if old_http_proxy:
            os.environ["http_proxy"] = old_http_proxy
        if old_https_proxy:
            os.environ["https_proxy"] = old_https_proxy
    
    return result


async def test_with_debug():
    """测试3: 开启调试模式"""
    print("\n[测试3] 开启LiteLLM调试模式...")
    litellm.set_verbose = True
    
    try:
        response = await litellm.acompletion(
            model=test_model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=3000,
            timeout=30,
            num_retries=1
        )
        print(f"✅ 调试模式成功!")
        return True
    except Exception as e:
        print(f"❌ 调试模式失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rubric_generation():
    """测试4: 模拟真实的adaptive rubric生成"""
    print("\n[测试4] 模拟adaptive rubric生成...")
    
    test_prompt = """You are an expert evaluator. Generate a simple rubric.

Question: What is 2+2?

Responses:
Response 1: The answer is 4.
Response 2: 2+2 equals 4.

Output JSON format:
{"question": "What is 2+2?", "positive_rubrics": [], "negative_rubrics": []}
"""
    
    try:
        response = await litellm.acompletion(
            model=test_model,
            messages=[{"role": "user", "content": test_prompt}],
            max_tokens=800,
            timeout=60,
            num_retries=5,
            temperature=0
        )
        print(f"✅ Rubric生成测试成功!")
        print(f"响应长度: {len(response.choices[0].message.content)} 字符")
        print(f"响应片段: {response.choices[0].message.content[:200]}...")
        return True
    except Exception as e:
        print(f"❌ Rubric生成测试失败: {e}")
        return False


async def main():
    print("\n开始测试...")
    
    results = {}
    results["basic"] = await test_basic_connection()
    
    # 如果基本测试失败，尝试不使用代理
    if not results["basic"]:
        results["no_proxy"] = await test_without_proxy()
    
    # 开启调试模式
    results["debug"] = await test_with_debug()
    
    # 测试实际的rubric生成
    results["rubric"] = await test_rubric_generation()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")
    
    if not any(results.values()):
        print("\n⚠️  所有测试都失败了!")
        print("\n可能的原因:")
        print("1. 代理服务器 httpproxy.glm.ai:8888 无法访问")
        print("2. OpenRouter API key 无效或过期")
        print("3. OpenRouter API 服务不可用")
        print("4. 网络防火墙阻止了连接")
        print("\n建议:")
        print("- 检查代理是否可用: curl -x http://httpproxy.glm.ai:8888 https://openrouter.ai")
        print("- 验证API key是否有效")
        print("- 尝试直接连接(不使用代理)")
    elif results.get("basic"):
        print("\n✅ 连接正常! 训练脚本中的LiteLLM应该可以工作。")
        print("如果训练时仍然失败，可能是:")
        print("- 并发请求过多导致超时")
        print("- API rate limiting")
        print("- 请求的token数量过大")


if __name__ == "__main__":
    asyncio.run(main())

