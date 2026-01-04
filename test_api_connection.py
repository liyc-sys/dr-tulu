#!/usr/bin/env python3
"""
快速测试OpenRouter API连接
"""

import asyncio
import aiohttp
import os
import json

async def test_api_connection():
    # API配置
    api_key = os.getenv("OPENROUTER_API_KEY", "sk-or-v1-your-key-here")
    base_url = "https://openrouter.ai/api/v1"
    model = "openai/gpt-4o"
    
    if api_key == "sk-or-v1-your-key-here":
        print("❌ 请设置OPENROUTER_API_KEY环境变量")
        return
    
    print("🧪 测试OpenRouter API连接...")
    print(f"📡 API端点: {base_url}")
    print(f"🤖 模型: {model}")
    
    # 测试请求
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个帮助性的助手。"},
            {"role": "user", "content": "请简单回答：1+1等于几？"}
        ],
        "temperature": 0.3,
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://dr-tulu-evaluation.com",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    usage = result.get('usage', {})
                    
                    print("✅ API连接成功!")
                    print(f"📝 回答: {content}")
                    print(f"📊 Token使用: 输入={usage.get('prompt_tokens', 'N/A')}, 输出={usage.get('completion_tokens', 'N/A')}, 总计={usage.get('total_tokens', 'N/A')}")
                    print("🎉 API配置正确，可以开始评估")
                else:
                    error_text = await response.text()
                    print(f"❌ API错误: {response.status}")
                    print(f"📄 错误详情: {error_text}")
                    
                    if response.status == 401:
                        print("💡 提示: API密钥无效，请检查OPENROUTER_API_KEY")
                    elif response.status == 429:
                        print("💡 提示: API限流，请稍后重试")
                    elif response.status == 500:
                        print("💡 提示: OpenRouter服务异常，请稍后重试")
                        
    except asyncio.TimeoutError:
        print("❌ 请求超时")
        print("💡 提示: 检查网络连接")
    except Exception as e:
        print(f"❌ 连接错误: {e}")
        print("💡 提示: 检查网络连接和API配置")

if __name__ == "__main__":
    asyncio.run(test_api_connection())
