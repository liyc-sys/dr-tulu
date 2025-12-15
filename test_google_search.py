#!/usr/bin/env python3
"""
测试 Google 搜索工具
"""
import asyncio
import os
import sys

# 设置环境变量
os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))

from dr_agent.tool_interface.mcp_tools import SerperSearchTool


async def test_google_search():
    """测试 Google 搜索"""
    print("创建 Google 搜索工具...")
    
    tool = SerperSearchTool(
        tool_parser="v20250824",
        number_documents_to_search=10,
        timeout=60,
        name="google_search"
    )
    
    print("✓ 工具创建成功\n")
    
    # 测试查询
    query = "人工智能最新进展"
    print(f"搜索: {query}")
    print("-" * 60)
    
    # 执行搜索
    result = await tool({"query": query, "num_results": 10})
    
    # 显示结果
    print(f"\n搜索结果:")
    print(f"  调用成功: {result.called}")
    print(f"  错误信息: {result.error if result.error else '无'}")
    print(f"  耗时: {result.runtime:.2f}秒")
    print(f"  文档数: {len(result.documents)}")
    
    if result.documents:
        print(f"\n前 5 个搜索结果:\n")
        for i, doc in enumerate(result.documents[:5], 1):
            print(f"{i}. {doc.title}")
            print(f"   URL: {doc.url}")
            print(f"   摘要: {doc.snippet[:150]}..." if len(doc.snippet) > 150 else f"   摘要: {doc.snippet}")
            print()
    
    print("=" * 60)
    print("✓ 测试完成")
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("Google 搜索工具测试")
    print("=" * 60)
    print("\n请确保 MCP 服务器正在运行:")
    print("  cd agent")
    print("  uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp\n")
    
    try:
        asyncio.run(test_google_search())
    except KeyboardInterrupt:
        print("\n\n测试中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

