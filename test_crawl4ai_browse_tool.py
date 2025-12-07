#!/usr/bin/env python3
"""
测试Crawl4AIBrowseTool是否可用
模拟训练时的工具调用方式
"""

import asyncio
import os
import sys
from pathlib import Path

# 设置环境变量（与训练脚本一致）
os.environ["MCP_TRANSPORT_PORT"] = "8003"
os.environ["MCP_TRANSPORT_HOST"] = "localhost"
os.environ["MCP_MAX_CONCURRENT_CALLS"] = "512"

# API Keys
os.environ["S2_API_KEY"] = "sk-user-F788DB8EABBDAD1858E82734A4E0C1BA"
os.environ["SERPER_API_KEY"] = "56e20b0fb1dc8a9d19fb80be90fb346e63294148"


def check_environment():
    """检查环境配置"""
    print("=" * 60)
    print("🔍 检查环境配置...")
    print("=" * 60)
    
    issues = []
    
    # 检查必需的环境变量
    required_vars = {
        "S2_API_KEY": "Semantic Scholar API Key",
        "SERPER_API_KEY": "Serper API Key (用于Google搜索)",
    }
    
    for var, description in required_vars.items():
        value = os.environ.get(var)
        if value:
            print(f"✅ {description}: {value[:10]}...")
        else:
            print(f"❌ {description}: 未设置")
            issues.append(f"环境变量 {var} 未设置")
    
    # 检查Crawl4AI配置（use_ai2_config=True时需要）
    crawl4ai_vars = {
        "CRAWL4AI_API_URL": "Crawl4AI Docker API URL",
        "CRAWL4AI_API_KEY": "Crawl4AI API Key",
        "CRAWL4AI_BLOCKLIST_PATH": "Crawl4AI Blocklist Path",
    }
    
    print("\n📦 Crawl4AI配置（use_ai2_config=True时需要）:")
    for var, description in crawl4ai_vars.items():
        value = os.environ.get(var)
        if value:
            print(f"✅ {description}: {value[:50]}...")
        else:
            print(f"⚠️  {description}: 未设置")
            issues.append(f"Crawl4AI配置 {var} 未设置（如果使用use_ai2_config=True则必需）")
    
    print("\n🌐 MCP服务器配置:")
    print(f"   Host: {os.environ.get('MCP_TRANSPORT_HOST', 'localhost')}")
    print(f"   Port: {os.environ.get('MCP_TRANSPORT_PORT', '8003')}")
    
    if issues:
        print("\n⚠️  发现配置问题:")
        for issue in issues:
            print(f"   - {issue}")
        print("\n💡 解决方法见下方的'配置说明'部分")
    else:
        print("\n✅ 环境配置检查通过！")
    
    return len(issues) == 0


async def test_mcp_server():
    """测试MCP服务器是否运行"""
    print("\n" + "=" * 60)
    print("🔌 测试MCP服务器连接...")
    print("=" * 60)
    
    try:
        import httpx
        host = os.environ.get("MCP_TRANSPORT_HOST", "localhost")
        port = os.environ.get("MCP_TRANSPORT_PORT", "8003")
        url = f"http://{host}:{port}/health"
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                print(f"✅ MCP服务器运行正常: {url}")
                return True
            else:
                print(f"❌ MCP服务器返回错误: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ 无法连接到MCP服务器: {e}")
        print("\n💡 请先启动MCP服务器:")
        print(f"   cd {Path(__file__).parent / 'agent'}")
        print("   uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
        return False


async def test_snippet_search():
    """测试snippet_search工具（Semantic Scholar）"""
    print("\n" + "=" * 60)
    print("📚 测试 snippet_search (Semantic Scholar)")
    print("=" * 60)
    
    try:
        from dr_agent.tool_interface.mcp_tools import SemanticScholarSnippetSearchTool
        
        tool = SemanticScholarSnippetSearchTool(
            tool_parser="v20250824",
            number_documents_to_search=3,
            timeout=60,
            name="snippet_search",
            transport_type="StreamableHttpTransport",
        )
        
        query = "large language model"
        print(f"查询: {query}")
        
        result = await tool({"query": query, "limit": 3})
        
        if result.error:
            print(f"❌ 错误: {result.error}")
            return False
        else:
            print(f"✅ 成功获取 {len(result.documents)} 个结果")
            for i, doc in enumerate(result.documents[:2], 1):
                print(f"\n   结果 {i}:")
                print(f"   标题: {doc.title[:80]}...")
                print(f"   片段: {doc.snippet[:100]}...")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_google_search():
    """测试google_search工具（Serper）"""
    print("\n" + "=" * 60)
    print("🔍 测试 google_search (Serper)")
    print("=" * 60)
    
    try:
        from dr_agent.tool_interface.mcp_tools import SerperSearchTool
        
        tool = SerperSearchTool(
            tool_parser="v20250824",
            number_documents_to_search=5,
            timeout=60,
            name="google_search",
            transport_type="StreamableHttpTransport",
        )
        
        query = "python programming tutorial"
        print(f"查询: {query}")
        
        result = await tool({"query": query})
        
        if result.error:
            print(f"❌ 错误: {result.error}")
            return False
        else:
            print(f"✅ 成功获取 {len(result.documents)} 个结果")
            for i, doc in enumerate(result.documents[:3], 1):
                print(f"\n   结果 {i}:")
                print(f"   标题: {doc.title[:80]}")
                print(f"   URL: {doc.url}")
                print(f"   摘要: {doc.snippet[:100]}...")
            
            # 返回结果供browse_webpage测试使用
            return result
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_browse_webpage(search_result=None):
    """测试browse_webpage工具（Crawl4AI）"""
    print("\n" + "=" * 60)
    print("🌐 测试 browse_webpage (Crawl4AI)")
    print("=" * 60)
    
    try:
        from dr_agent.tool_interface.mcp_tools import Crawl4AIBrowseTool
        
        # 与训练脚本一致的配置
        tool = Crawl4AIBrowseTool(
            tool_parser="v20250824",
            max_pages_to_fetch=2,
            timeout=180,
            name="browse_webpage",
            transport_type="StreamableHttpTransport",
            use_docker_version=True,  # 训练脚本使用Docker版本
            use_ai2_config=True,      # 训练脚本使用AI2配置
        )
        
        # 测试方式1：直接URL
        test_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
        print(f"\n测试1 - 直接URL: {test_url}")
        
        result = await tool({"url": test_url})
        
        if result.error:
            print(f"❌ 错误: {result.error}")
            return False
        else:
            print(f"✅ 成功获取网页内容")
            for i, doc in enumerate(result.documents, 1):
                print(f"\n   页面 {i}:")
                print(f"   URL: {doc.url}")
                if doc.text:
                    print(f"   内容长度: {len(doc.text)} 字符")
                    print(f"   内容预览: {doc.text[:150]}...")
                if doc.error:
                    print(f"   错误: {doc.error}")
        
        # 测试方式2：使用搜索结果（模拟训练时的链式调用）
        if search_result and hasattr(search_result, 'documents'):
            print(f"\n测试2 - 从搜索结果获取URL:")
            result2 = await tool(search_result)
            
            if result2.error:
                print(f"❌ 错误: {result2.error}")
            else:
                print(f"✅ 成功获取 {len(result2.documents)} 个网页内容")
                for i, doc in enumerate(result2.documents[:2], 1):
                    print(f"\n   页面 {i}:")
                    print(f"   URL: {doc.url}")
                    if doc.text:
                        print(f"   内容长度: {len(doc.text)} 字符")
        
        return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("🚀 Dr-Tulu 工具测试脚本（完整集成测试）")
    print("=" * 60)
    
    print("\n💡 说明：")
    print("   本脚本测试训练时使用的所有3个工具：")
    print("   1. snippet_search (Semantic Scholar)")
    print("   2. google_search (Serper)")
    print("   3. browse_webpage (Crawl4AI)")
    print("\n   如果只想测试Crawl4AI，请运行: python test_crawl4ai_only.py")
    print("=" * 60)
    
    # 1. 检查环境
    env_ok = check_environment()
    
    # 2. 检查MCP服务器
    server_ok = await test_mcp_server()
    
    if not server_ok:
        print("\n" + "=" * 60)
        print("❌ 测试终止：MCP服务器未运行")
        print("=" * 60)
        return
    
    # 3. 测试工具
    results = {}
    
    # 测试snippet_search
    results['snippet_search'] = await test_snippet_search()
    
    # 测试google_search
    search_result = await test_google_search()
    results['google_search'] = search_result is not False
    
    # 测试browse_webpage
    results['browse_webpage'] = await test_browse_webpage(search_result)
    
    # 4. 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    for tool_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{tool_name:20s}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 所有工具测试通过！训练环境配置正确。")
    else:
        print("\n⚠️  部分工具测试失败，请检查配置。")
    
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

