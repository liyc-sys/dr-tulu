#!/usr/bin/env python3
"""
测试 Google 搜索工具 - 使用工具调用格式（模拟训练场景）
"""
import asyncio
import os
import sys

os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))

from dr_agent.tool_interface.mcp_tools import SerperSearchTool


async def test_with_tool_call_format():
    """测试使用工具调用格式"""
    print("创建工具实例...")
    
    tool = SerperSearchTool(
        tool_parser="v20250824",  # 使用训练中的 parser
        number_documents_to_search=5,
        timeout=60,
        name="google_search"
    )
    
    print("✓ 工具创建成功\n")
    
    # 模拟模型生成的工具调用格式
    tool_call_text = '<tool_call name="google_search" num_results="5">机器学习在医疗中的应用</tool_call>'
    
    print(f"工具调用文本:")
    print(f"  {tool_call_text}\n")
    print("-" * 60)
    
    # 使用字符串格式调用（模拟真实场景）
    result = await tool(tool_call_text)
    
    # 显示结果
    print(f"\n搜索结果:")
    print(f"  成功: {result.called}")
    print(f"  错误: {result.error if result.error else '无'}")
    print(f"  耗时: {result.runtime:.2f}秒")
    print(f"  结果数: {len(result.documents)}")
    print(f"  查询: {result.query}")
    
    if result.documents:
        print(f"\n搜索结果详情:\n")
        for i, doc in enumerate(result.documents, 1):
            print(f"{i}. 【{doc.title}】")
            print(f"   🔗 {doc.url}")
            snippet = doc.snippet[:100] + "..." if len(doc.snippet) > 100 else doc.snippet
            print(f"   📝 {snippet}")
            print()
    
    # 显示格式化输出（这是返回给模型的内容）
    print("=" * 60)
    print("格式化输出（返回给模型）:\n")
    formatted = tool._format_output(result)
    print(formatted[:500] + "..." if len(formatted) > 500 else formatted)
    
    print("\n" + "=" * 60)
    print("✓ 测试完成")


if __name__ == "__main__":
    print("=" * 60)
    print("Google 搜索 - 工具调用格式测试")
    print("=" * 60)
    print("\n确保 MCP 服务器运行:")
    print("  cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp\n")
    
    try:
        asyncio.run(test_with_tool_call_format())
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

