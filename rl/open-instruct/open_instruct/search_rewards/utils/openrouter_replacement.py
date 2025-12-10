"""
Direct OpenRouter API replacement for litellm.
Simpler and more reliable for OpenRouter-specific usage.
"""

import os
import asyncio
import weakref
import httpx
from typing import Optional, List, Dict
import logging

LOGGER = logging.getLogger(__name__)

# Per-event-loop semaphore to avoid event loop binding issues in distributed environments
_OPENROUTER_SEMAPHORES = weakref.WeakKeyDictionary()

def _get_semaphore():
    """
    Return a per-event-loop semaphore for concurrent API calls.
    This avoids 'bound to a different event loop' errors in distributed training (Ray).
    
    Limit can be configured with env var `OPENROUTER_MAX_CONCURRENT_CALLS` (default 10).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create a new semaphore
        max_concurrent = int(os.environ.get("OPENROUTER_MAX_CONCURRENT_CALLS", "10"))
        return asyncio.Semaphore(max_concurrent)
    
    sem = _OPENROUTER_SEMAPHORES.get(loop)
    if sem is None:
        max_concurrent = int(os.environ.get("OPENROUTER_MAX_CONCURRENT_CALLS", "10"))
        sem = asyncio.Semaphore(max_concurrent)
        _OPENROUTER_SEMAPHORES[loop] = sem
    return sem


async def call_openrouter_async(
    model_name: str,
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    timeout: float = 600.0,
    num_retries: int = 5,
    **kwargs,
) -> str:
    """
    直接调用 OpenRouter API，替代 litellm。
    
    Args:
        model_name: 模型名称（如 "openai/gpt-4o-mini"）
        user_prompt: 用户提示词
        system_prompt: 系统提示词（可选）
        messages: 完整的消息列表（可选，如果提供则忽略 user_prompt 和 system_prompt）
        temperature: 温度参数
        max_tokens: 最大token数
        top_p: top_p 参数
        frequency_penalty: 频率惩罚
        presence_penalty: 存在惩罚
        timeout: 超时时间（秒）
        num_retries: 重试次数
        **kwargs: 其他参数
        
    Returns:
        模型生成的文本内容
    """
    
    # 从环境变量获取配置
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    # 准备消息
    if messages is not None:
        msgs = messages
    else:
        msgs = []
        if system_prompt is not None:
            msgs.append({"role": "system", "content": system_prompt})
        if user_prompt is not None:
            msgs.append({"role": "user", "content": user_prompt})
    
    # 准备请求数据
    request_data = {
        "model": model_name,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    
    # OpenRouter 特定的头部
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost:3000"),
        "X-Title": os.environ.get("OPENROUTER_TITLE", "DR-Tulu Training"),
    }
    
    # 使用信号量控制并发
    semaphore = _get_semaphore()
    
    async with semaphore:
        # 重试逻辑
        last_error = None
        for attempt in range(num_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{api_base}/chat/completions",
                        json=request_data,
                        headers=headers,
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # 提取内容
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        return content
                    else:
                        LOGGER.warning(f"Unexpected response format: {result}")
                        return ""
                        
            except Exception as e:
                last_error = e
                LOGGER.warning(f"OpenRouter API call failed (attempt {attempt + 1}/{num_retries}): {e}")
                if attempt < num_retries - 1:
                    # 指数退避
                    await asyncio.sleep(2 ** attempt)
                continue
        
        # 所有重试都失败了
        LOGGER.error(f"All {num_retries} attempts failed. Last error: {last_error}")
        return ""


def call_openrouter(
    model_name: str,
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    timeout: float = 600.0,
    num_retries: int = 5,
    **kwargs,
) -> str:
    """
    同步版本的 OpenRouter 调用。
    使用同步 HTTP 客户端，避免事件循环问题。
    """
    # 从环境变量获取配置
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    # 准备消息
    if messages is not None:
        msgs = messages
    else:
        msgs = []
        if system_prompt is not None:
            msgs.append({"role": "system", "content": system_prompt})
        if user_prompt is not None:
            msgs.append({"role": "user", "content": user_prompt})
    
    # 准备请求数据
    request_data = {
        "model": model_name,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    
    # OpenRouter 特定的头部
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost:3000"),
        "X-Title": os.environ.get("OPENROUTER_TITLE", "DR-Tulu Training"),
    }
    
    # 重试逻辑（同步版本）
    last_error = None
    for attempt in range(num_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{api_base}/chat/completions",
                    json=request_data,
                    headers=headers,
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 提取内容
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    return content
                else:
                    LOGGER.warning(f"Unexpected response format: {result}")
                    return ""
                    
        except Exception as e:
            last_error = e
            LOGGER.warning(f"OpenRouter API call failed (attempt {attempt + 1}/{num_retries}): {e}")
            if attempt < num_retries - 1:
                # 指数退避
                import time
                time.sleep(2 ** attempt)
            continue
    
    # 所有重试都失败了
    LOGGER.error(f"All {num_retries} attempts failed. Last error: {last_error}")
    return ""


if __name__ == "__main__":
    # 简单测试
    import asyncio
    
    async def test():
        print("Testing OpenRouter API replacement...")
        
        # 设置必要的环境变量
        if not os.environ.get("OPENAI_API_KEY"):
            print("Please set OPENAI_API_KEY environment variable")
            return
        
        response = await call_openrouter_async(
            model_name="openai/gpt-4o-mini",
            user_prompt="Say hello in one sentence.",
            max_tokens=100,
        )
        
        print(f"Response: {response}")
    
    asyncio.run(test())

