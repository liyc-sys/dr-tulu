#!/usr/bin/env python3
"""
简单测试脚本：验证 PubMed 搜索工具是否正常工作
"""
import asyncio
import os
import sys

# 确保环境变量已设置
os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")

# 添加 agent 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))

from dr_agent.tool_interface.mcp_tools import PubMedSearchTool


async def test_pubmed_search():
    """测试 PubMed 搜索工具"""
    print("初始化 PubMed 搜索工具...")
    
    # 创建工具实例
    tool = PubMedSearchTool(
        tool_parser="v20250824",
        number_documents_to_search=5,
        timeout=60,
        name="pubmed_search"
    )
    
    print("✓ 工具创建成功\n")
    
    # 测试搜索
    test_query = "machine learning in healthcare"
    print(f"测试查询: {test_query}")
    print("-" * 60)
    
    # 直接调用（字典模式）
    result = await tool({"query": test_query, "limit": 5})
    
    print(f"\n搜索结果:")
    print(f"- 调用成功: {result.called}")
    print(f"- 是否有错误: {result.error if result.error else '无'}")
    print(f"- 运行时间: {result.runtime:.2f}秒")
    print(f"- 找到文档数: {len(result.documents)}")
    
    if result.documents:
        print(f"\n前 3 篇论文:")
        for i, doc in enumerate(result.documents[:3], 1):
            print(f"\n{i}. {doc.title}")
            print(f"   URL: {doc.url}")
            print(f"   评分(引用数): {doc.score}")
            # 显示摘要前200个字符
            snippet_preview = doc.snippet[:200] + "..." if len(doc.snippet) > 200 else doc.snippet
            print(f"   摘要: {snippet_preview}")
    
    print("\n" + "=" * 60)
    print("✓ 测试完成！")
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("PubMed 搜索工具测试")
    print("=" * 60)
    print("\n注意: 请确保 MCP 服务器正在运行:")
    print("  uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp\n")
    
    try:
        asyncio.run(test_pubmed_search())
    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

