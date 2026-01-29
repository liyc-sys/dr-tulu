"""
测试 FDA Drug Label Search 工具的并发性能
验证异步实现是否能正确处理多个并发请求
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "scripts" / "pubmed_data_generator"))

from fastmcp import Client


async def call_fda_tool(
    client: Client,
    drug_name: str,
    focus: str,
    request_id: int,
) -> Tuple[int, str, float, bool, str]:
    """
    调用 FDA 工具并记录时间

    Returns:
        (request_id, drug_name, elapsed_time, success, result_preview)
    """
    start_time = time.time()
    try:
        result = await client.call_tool(
            "fda_drug_label_search",
            {
                "keyword": drug_name,
                "focus": focus,
                "limit": 1,
                "use_llm_extraction": False,  # 不使用 LLM 提取，加快测试速度
            }
        )

        elapsed = time.time() - start_time

        if hasattr(result, "content") and result.content:
            if hasattr(result.content[0], "text"):
                raw_result = json.loads(result.content[0].text)
                if raw_result.get("error"):
                    return (request_id, drug_name, elapsed, False, str(raw_result["error"]))
                preview = f"strategy={raw_result.get('search_strategy', 'N/A')}"
                return (request_id, drug_name, elapsed, True, preview)

        return (request_id, drug_name, elapsed, False, "No content")

    except Exception as e:
        elapsed = time.time() - start_time
        return (request_id, drug_name, elapsed, False, str(e))


async def test_concurrent_fda_calls():
    """测试并发 FDA 工具调用"""
    print("=" * 70)
    print("FDA Drug Label Search 并发测试")
    print("=" * 70)
    print()

    # 读取 MCP 配置
    mcp_host = os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1")
    mcp_port = os.environ.get("MCP_TRANSPORT_PORT", "8003")
    mcp_url = f"http://{mcp_host}:{mcp_port}/mcp"

    print(f"MCP URL: {mcp_url}")
    print()

    # 测试药物列表
    test_drugs = [
        ("aspirin", "adverse reactions"),
        ("metformin", "indications and usage"),
        ("ibuprofen", "warnings"),
        ("acetaminophen", "dosage"),
        ("lisinopril", "contraindications"),
        ("atorvastatin", "drug interactions"),
        ("omeprazole", "adverse reactions"),
        ("amlodipine", "warnings"),
    ]

    # 并发数量测试
    concurrency_levels = [1, 2, 4, 8]

    for concurrency in concurrency_levels:
        print("-" * 70)
        print(f"测试并发数: {concurrency}")
        print("-" * 70)

        # 取前 concurrency 个药物进行测试
        drugs_to_test = test_drugs[:concurrency]

        client = Client(mcp_url, timeout=180)

        start_time = time.time()

        async with client:
            # 创建并发任务
            tasks = [
                call_fda_tool(client, drug, focus, i)
                for i, (drug, focus) in enumerate(drugs_to_test)
            ]

            # 并发执行
            results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.time() - start_time

        # 统计结果
        success_count = 0
        fail_count = 0
        total_individual_time = 0

        print(f"\n{'ID':<4} {'药物':<15} {'耗时(s)':<10} {'状态':<8} {'结果'}")
        print("-" * 70)

        for result in results:
            if isinstance(result, Exception):
                print(f"{'?':<4} {'?':<15} {'?':<10} {'异常':<8} {str(result)[:40]}")
                fail_count += 1
            else:
                req_id, drug, elapsed, success, preview = result
                status = "成功" if success else "失败"
                print(f"{req_id:<4} {drug:<15} {elapsed:<10.2f} {status:<8} {preview[:40]}")
                total_individual_time += elapsed
                if success:
                    success_count += 1
                else:
                    fail_count += 1

        print("-" * 70)
        print(f"总耗时: {total_time:.2f}s")
        print(f"各请求耗时之和: {total_individual_time:.2f}s")
        print(f"并发效率: {total_individual_time / total_time:.2f}x (理想值: {concurrency}x)")
        print(f"成功: {success_count}, 失败: {fail_count}")
        print()

    print("=" * 70)
    print("测试完成")
    print("=" * 70)
    print()
    print("说明:")
    print("- 并发效率接近并发数说明异步实现正确")
    print("- 如果并发效率接近 1x，说明请求是串行执行的")
    print("- 实际效率可能因网络延迟等因素略低于理想值")


async def test_sequential_vs_concurrent():
    """对比顺序执行和并发执行的性能"""
    print("=" * 70)
    print("顺序执行 vs 并发执行 对比测试")
    print("=" * 70)
    print()

    mcp_host = os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1")
    mcp_port = os.environ.get("MCP_TRANSPORT_PORT", "8003")
    mcp_url = f"http://{mcp_host}:{mcp_port}/mcp"

    test_drugs = [
        ("aspirin", "adverse reactions"),
        ("metformin", "indications"),
        ("ibuprofen", "warnings"),
        ("acetaminophen", "dosage"),
    ]

    # 顺序执行
    print("1. 顺序执行 (4个请求)")
    print("-" * 40)

    client = Client(mcp_url, timeout=180)
    sequential_start = time.time()

    async with client:
        for i, (drug, focus) in enumerate(test_drugs):
            result = await call_fda_tool(client, drug, focus, i)
            print(f"   请求 {i}: {drug} - {result[2]:.2f}s")

    sequential_time = time.time() - sequential_start
    print(f"   顺序执行总耗时: {sequential_time:.2f}s")
    print()

    # 并发执行
    print("2. 并发执行 (4个请求)")
    print("-" * 40)

    client = Client(mcp_url, timeout=180)
    concurrent_start = time.time()

    async with client:
        tasks = [
            call_fda_tool(client, drug, focus, i)
            for i, (drug, focus) in enumerate(test_drugs)
        ]
        results = await asyncio.gather(*tasks)

        for result in results:
            print(f"   请求 {result[0]}: {result[1]} - {result[2]:.2f}s")

    concurrent_time = time.time() - concurrent_start
    print(f"   并发执行总耗时: {concurrent_time:.2f}s")
    print()

    # 对比
    print("=" * 70)
    print("对比结果:")
    print(f"  顺序执行: {sequential_time:.2f}s")
    print(f"  并发执行: {concurrent_time:.2f}s")
    print(f"  加速比: {sequential_time / concurrent_time:.2f}x")
    print()

    if concurrent_time < sequential_time * 0.6:
        print("结论: 异步实现正确工作，并发执行明显更快")
    elif concurrent_time < sequential_time * 0.9:
        print("结论: 异步有一定效果，但可能存在瓶颈")
    else:
        print("结论: 异步未生效，请检查实现")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("FDA Tool 并发性能测试")
    print("=" * 70 + "\n")

    # 检查环境变量
    print("环境变量检查:")
    env_vars = {
        "MCP_TRANSPORT_HOST": os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1"),
        "MCP_TRANSPORT_PORT": os.environ.get("MCP_TRANSPORT_PORT", "8003"),
    }

    for key, value in env_vars.items():
        print(f"  {key}: {value}")
    print()

    # 运行测试
    try:
        await test_sequential_vs_concurrent()
        print("\n")
        await test_concurrent_fda_calls()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
