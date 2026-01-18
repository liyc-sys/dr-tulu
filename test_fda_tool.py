#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 FDA Drug Label Search 工具
"""
import asyncio
import os


async def test_fda_tool():
    """测试 FDA 工具（直接调用 API，不通过 MCP server）"""
    from agent.dr_agent.mcp_backend.apis.fda_apis import search_fda_drug_label
    
    print("=" * 60)
    print("测试 1: 搜索 aspirin 的副作用 (使用 LLM 提取)")
    print("=" * 60)
    
    result = search_fda_drug_label(
        keyword="aspirin",
        focus="adverse reactions",
        limit=2,
        use_llm_extraction=True
    )
    
    print(f"\n关键词: {result['keyword']}")
    print(f"关注点: {result['focus']}")
    print(f"搜索策略: {result['search_strategy']}")
    print(f"错误: {result.get('error', 'None')}")
    print(f"\n提取的信息 ({len(result['extracted_info'])} 条):")
    for i, info in enumerate(result['extracted_info'], 1):
        print(f"\n--- 结果 {i} ---")
        print(info[:500] if len(info) > 500 else info)
        if len(info) > 500:
            print("... (截断)")
    
    print("\n" + "=" * 60)
    print("测试 2: 搜索 metformin 的用途 (不使用 LLM 提取)")
    print("=" * 60)
    
    result2 = search_fda_drug_label(
        keyword="metformin",
        focus="indications and usage",
        limit=1,
        use_llm_extraction=False
    )
    
    print(f"\n关键词: {result2['keyword']}")
    print(f"关注点: {result2['focus']}")
    print(f"搜索策略: {result2['search_strategy']}")
    print(f"错误: {result2.get('error', 'None')}")
    print(f"\n原始数据 ({len(result2['data'])} 条):")
    if result2['data']:
        print(str(result2['data'][0])[:500] + "... (截断)")


async def test_fda_tool_via_mcp():
    """测试通过 MCP Tool Interface 调用 FDA 工具"""
    from dr_agent.tool_interface.mcp_tools import FDADrugLabelSearchTool
    from dr_agent.tool_interface.tool_parsers import ToolCallInfo
    
    print("\n" + "=" * 60)
    print("测试 3: 通过 MCP Tool Interface 调用")
    print("=" * 60)
    
    # 创建工具实例
    fda_tool = FDADrugLabelSearchTool(
        number_documents_to_search=2,
        timeout=180,
        use_llm_extraction=True
    )
    
    # 模拟工具调用
    tool_call_info = ToolCallInfo(
        content="ibuprofen",  # 药物名称
        parameters={"focus": "warnings and precautions"},  # 关注点
        start_pos=0,
        end_pos=9
    )
    
    # 注意：这需要 MCP server 运行
    # 如果 server 没运行，这会失败
    try:
        result = await fda_tool(tool_call_info)
        print(f"\n工具名称: {result.tool_name}")
        print(f"调用成功: {result.called}")
        print(f"错误: {result.error or 'None'}")
        print(f"\n文档数量: {len(result.documents)}")
        for i, doc in enumerate(result.documents, 1):
            print(f"\n--- 文档 {i} ---")
            print(f"标题: {doc.title}")
            print(f"URL: {doc.url}")
            print(f"摘要: {doc.snippet[:200]}..." if len(doc.snippet) > 200 else f"摘要: {doc.snippet}")
    except Exception as e:
        print(f"\n⚠️  MCP server 未运行或连接失败: {e}")
        print("请先启动 MCP server:")
        print("cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")


if __name__ == "__main__":
    # 确保设置了 OPENROUTER_API_KEY 环境变量
    if not os.getenv("OPENROUTER_API_KEY"):
        print("⚠️  警告: OPENROUTER_API_KEY 环境变量未设置")
        print("如果要使用 LLM 提取功能，请设置此环境变量")
        print("export OPENROUTER_API_KEY='your-api-key'")
        print("\n继续测试（不使用 LLM 提取功能）...\n")
    
    # 运行测试
    asyncio.run(test_fda_tool())
    asyncio.run(test_fda_tool_via_mcp())

