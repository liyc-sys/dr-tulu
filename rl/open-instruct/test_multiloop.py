#!/usr/bin/env python3
"""
测试多事件循环场景下的 OpenRouter 调用
模拟分布式训练环境中的情况
"""

import os
import asyncio
import concurrent.futures

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "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"
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
os.environ["USE_OPENROUTER_DIRECT"] = "true"
os.environ["RUBRIC_JUDGE_MODEL"] = "openai/gpt-4o-mini"

from open_instruct.search_rewards.utils.run_utils import run_litellm_async


async def test_call_in_loop(loop_id):
    """在单独的事件循环中测试调用"""
    try:
        print(f"[Loop {loop_id}] Starting test...")
        response = await run_litellm_async(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt=f"Say 'Hello from loop {loop_id}' in one sentence.",
            max_tokens=50,
        )
        
        if response:
            print(f"[Loop {loop_id}] ✅ Success: {response[:50]}...")
            return True
        else:
            print(f"[Loop {loop_id}] ❌ Failed: empty response")
            return False
    except Exception as e:
        print(f"[Loop {loop_id}] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_in_new_loop(loop_id):
    """在新的事件循环中运行测试"""
    # 创建新的事件循环（模拟 Ray actor 的情况）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(test_call_in_loop(loop_id))
        return result
    finally:
        loop.close()


def main():
    print("=" * 70)
    print(" 多事件循环测试（模拟分布式训练）")
    print("=" * 70)
    print("这个测试模拟了 Ray 分布式训练中的多进程/多事件循环场景\n")
    
    # 使用 ProcessPoolExecutor 模拟多进程环境
    # 注意：在实际的 Ray 环境中，每个 actor 都有自己的进程和事件循环
    num_loops = 3
    
    print(f"启动 {num_loops} 个独立的事件循环（进程）...\n")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_loops) as executor:
        # 提交任务到不同的线程，每个线程创建自己的事件循环
        futures = [executor.submit(run_in_new_loop, i) for i in range(num_loops)]
        
        # 等待所有任务完成
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    print("\n" + "=" * 70)
    print(" 测试结果")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r)
    print(f"成功: {success_count}/{num_loops}")
    
    if success_count == num_loops:
        print("\n✅ 所有测试通过！多事件循环问题已解决。")
        return 0
    else:
        print(f"\n❌ 有 {num_loops - success_count} 个测试失败。")
        return 1


if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code)

