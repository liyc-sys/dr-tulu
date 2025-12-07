#!/usr/bin/env python3
"""
专门测试Crawl4AIBrowseTool是否可用
只测试browse_webpage工具，不测试其他工具
"""

import asyncio
import os
import sys
from pathlib import Path

# 设置环境变量
os.environ["MCP_TRANSPORT_PORT"] = "8003"
os.environ["MCP_TRANSPORT_HOST"] = "localhost"
os.environ["MCP_MAX_CONCURRENT_CALLS"] = "512"


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def check_crawl4ai_config():
    """检查Crawl4AI相关配置"""
    print_section("🔍 检查Crawl4AI配置")
    
    issues = []
    
    # 检查Crawl4AI配置
    crawl4ai_vars = {
        "CRAWL4AI_API_URL": "Crawl4AI Docker API URL",
        "CRAWL4AI_API_KEY": "Crawl4AI API Key",
        "CRAWL4AI_BLOCKLIST_PATH": "Crawl4AI Blocklist Path",
    }
    
    print("📦 Crawl4AI Docker配置（use_ai2_config=True时需要）:")
    for var, description in crawl4ai_vars.items():
        value = os.environ.get(var)
        if value:
            print(f"✅ {description}: {value[:50]}...")
        else:
            print(f"⚠️  {description}: 未设置")
            if var == "CRAWL4AI_BLOCKLIST_PATH":
                issues.append(f"{var} 未设置（use_ai2_config=True时必需）")
    
    print("\n🌐 MCP服务器配置:")
    print(f"   Host: {os.environ.get('MCP_TRANSPORT_HOST', 'localhost')}")
    print(f"   Port: {os.environ.get('MCP_TRANSPORT_PORT', '8003')}")
    
    if issues:
        print("\n⚠️  配置问题:")
        for issue in issues:
            print(f"   - {issue}")
    
    return len(issues) == 0


async def test_mcp_server():
    """测试MCP服务器是否运行"""
    print_section("🔌 测试MCP服务器连接")
    
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


async def test_crawl4ai_direct_url():
    """测试1：直接URL访问"""
    print_section("🌐 测试1: Crawl4AI - 直接URL访问")
    
    try:
        from dr_agent.tool_interface.mcp_tools import Crawl4AIBrowseTool
        
        # 与训练脚本一致的配置
        tool = Crawl4AIBrowseTool(
            tool_parser="v20250824",
            max_pages_to_fetch=1,
            timeout=180,
            name="browse_webpage",
            transport_type="StreamableHttpTransport",
            use_docker_version=True,
            use_ai2_config=True,
        )
        
        test_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
        print(f"访问URL: {test_url}")
        print("(这可能需要一些时间...)")
        
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
                    print(f"   内容预览: {doc.text[:200]}...")
                    print(f"   内容结尾: ...{doc.text[-100:]}")
                if doc.error:
                    print(f"   错误: {doc.error}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_crawl4ai_multiple_urls():
    """测试2：多个URL访问"""
    print_section("🌐 测试2: Crawl4AI - 多个URL访问")
    
    try:
        from dr_agent.tool_interface.mcp_tools import Crawl4AIBrowseTool
        from dr_agent.tool_interface.data_types import Document, DocumentToolOutput
        
        # 与训练脚本一致的配置
        tool = Crawl4AIBrowseTool(
            tool_parser="v20250824",
            max_pages_to_fetch=2,
            timeout=180,
            name="browse_webpage",
            transport_type="StreamableHttpTransport",
            use_docker_version=True,
            use_ai2_config=True,
        )
        
        # 模拟搜索结果（多个URL）
        test_urls = [
            "https://docs.python.org/3/",
            "https://www.python.org/about/",
        ]
        
        print(f"访问 {len(test_urls)} 个URL:")
        for url in test_urls:
            print(f"  - {url}")
        print("(这可能需要一些时间...)")
        
        # 创建模拟的搜索结果
        documents = [
            Document(
                title=f"Test Page {i+1}",
                snippet="Test snippet",
                url=url,
                text=None,
                score=None,
            )
            for i, url in enumerate(test_urls)
        ]
        
        mock_search_result = DocumentToolOutput(
            tool_name="google_search",
            output="",
            called=True,
            error="",
            timeout=False,
            runtime=1.0,
            call_id="test-123",
            raw_output={},
            documents=documents,
            query="test query",
        )
        
        result = await tool(mock_search_result)
        
        if result.error:
            print(f"❌ 错误: {result.error}")
            return False
        else:
            print(f"✅ 成功获取 {len(result.documents)} 个网页内容")
            for i, doc in enumerate(result.documents, 1):
                print(f"\n   页面 {i}:")
                print(f"   URL: {doc.url}")
                if doc.text:
                    print(f"   内容长度: {len(doc.text)} 字符")
                    print(f"   内容预览: {doc.text[:150]}...")
                if doc.error:
                    print(f"   错误: {doc.error}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_crawl4ai_with_local_config():
    """测试3：使用本地配置（不需要Docker）"""
    print_section("🌐 测试3: Crawl4AI - 本地配置（无Docker）")
    
    try:
        from dr_agent.tool_interface.mcp_tools import Crawl4AIBrowseTool
        
        # 使用本地配置（不需要Docker服务）
        tool = Crawl4AIBrowseTool(
            tool_parser="v20250824",
            max_pages_to_fetch=1,
            timeout=180,
            name="browse_webpage",
            transport_type="StreamableHttpTransport",
            use_docker_version=False,  # 使用本地版本
            use_ai2_config=False,      # 不使用AI2配置
        )
        
        test_url = "https://www.example.com/"
        print(f"访问URL: {test_url}")
        print("(使用本地Crawl4AI，不需要Docker服务)")
        
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
                    print(f"   内容预览: {doc.text[:200]}...")
                if doc.error:
                    print(f"   错误: {doc.error}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试流程"""
    print_section("🚀 Crawl4AIBrowseTool 专项测试")
    
    # 1. 检查配置
    check_crawl4ai_config()
    
    # 2. 检查MCP服务器
    server_ok = await test_mcp_server()
    
    if not server_ok:
        print_section("❌ 测试终止：MCP服务器未运行")
        return
    
    # 3. 运行测试
    results = {}
    
    print("\n" + "💡" * 30)
    print("开始测试Crawl4AIBrowseTool...")
    print("如果配置了Docker服务，将测试Docker版本")
    print("如果没有，将测试本地版本")
    print("💡" * 30)
    
    # 尝试Docker版本
    has_docker = os.environ.get("CRAWL4AI_API_URL") is not None
    
    if has_docker:
        print("\n检测到CRAWL4AI_API_URL，将测试Docker版本")
        results['test1_direct'] = await test_crawl4ai_direct_url()
        results['test2_multiple'] = await test_crawl4ai_multiple_urls()
    else:
        print("\n未检测到CRAWL4AI_API_URL，将测试本地版本")
        results['test3_local'] = await test_crawl4ai_with_local_config()
    
    # 4. 总结
    print_section("📊 测试结果总结")
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:20s}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 Crawl4AIBrowseTool 测试通过！")
        print("\n✨ 训练时browse_webpage工具应该可以正常工作。")
    else:
        print("\n⚠️  部分测试失败，请检查配置。")
        print("\n💡 常见问题:")
        print("   1. 如果使用Docker版本：")
        print("      - 确保CRAWL4AI_API_URL正确")
        print("      - 确保CRAWL4AI_BLOCKLIST_PATH指向有效文件")
        print("   2. 如果使用本地版本：")
        print("      - 确保crawl4ai包已安装: pip install crawl4ai")
        print("   3. 确保MCP服务器正在运行")
    
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

