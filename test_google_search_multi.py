#!/usr/bin/env python3
"""
测试多个查询的 Google 搜索
"""
import asyncio
import os
import sys

os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))

from dr_agent.tool_interface.mcp_tools import SerperSearchTool


async def test_query(tool, query, num_results=5):
    """测试单个查询"""
    print(f"\n{'='*60}")
    print(f"查询: {query}")
    print('='*60)
    
    result = await tool({"query": query, "num_results": num_results})
    
    if result.error:
        print(f"❌ 错误: {result.error}")
        return
    
    print(f"✓ 找到 {len(result.documents)} 个结果 (耗时 {result.runtime:.2f}秒)\n")
    
    for i, doc in enumerate(result.documents[:3], 1):
        print(f"{i}. {doc.title}")
        print(f"   {doc.url}")
        print(f"   {doc.snippet[:80]}...\n")


async def main():
    """测试多个查询"""
    print("初始化工具...")
    
    tool = SerperSearchTool(
        tool_parser="v20250824",
        number_documents_to_search=5,
        timeout=60,
        name="google_search"
    )
    
    print("✓ 工具准备完成\n")
    
    # 测试多个查询
    queries = [
        "深度学习最新进展",
        "什么是大语言模型",
        "Python 编程教程",
    ]
    
    for query in queries:
        await test_query(tool, query, num_results=5)
        await asyncio.sleep(0.5)  # 避免请求过快
    
    print("\n" + "="*60)
    print("✓ 所有测试完成")


if __name__ == "__main__":
    print("="*60)
    print("Google 搜索 - 多查询测试")
    print("="*60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

