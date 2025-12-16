"""
测试 trajectory_generator 中的 MCPToolExecutor
完整模拟轨迹生成过程中的工具调用
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "scripts" / "pubmed_data_generator"))

from trajectory_generator import MCPToolExecutor


async def test_pubmed_search():
    """测试 PubMed 搜索"""
    print("\n" + "=" * 60)
    print("🧬 测试 1: PubMed Search")
    print("=" * 60)
    
    executor = MCPToolExecutor()
    
    # 测试参数
    tool_name = "pubmed_search"
    parameters = {"limit": 3}
    query = "CRISPR gene editing therapy"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 查询: {query}")
    print(f"📋 参数: {parameters}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Total: {raw_result.get('total', 0)}")
        print(f"   返回数量: {len(raw_result.get('data', []))}")
        
        if raw_result.get('data'):
            print(f"\n   第一篇论文:")
            first_paper = raw_result['data'][0]
            print(f"   - PMID: {first_paper.get('paperId')}")
            print(f"   - Title: {first_paper.get('title', '')[:60]}...")
            print(f"   - Year: {first_paper.get('year')}")
        
        print()
        print("📝 格式化输出预览 (前 500 字符):")
        print("-" * 60)
        print(formatted_output[:500])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def test_browse_webpage():
    """测试 browse_webpage (Docker 版本)"""
    print("\n" + "=" * 60)
    print("🌐 测试 2: Browse Webpage (Docker)")
    print("=" * 60)
    
    executor = MCPToolExecutor()
    
    # 测试参数
    tool_name = "browse_webpage"
    parameters = {}
    query = "https://en.wikipedia.org/wiki/CRISPR"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 URL: {query}")
    print("⏳ (这可能需要一些时间...)")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if "error" in raw_result:
            print(f"❌ 失败: {raw_result['error']}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   URL: {raw_result.get('url', 'N/A')}")
        print(f"   Success: {raw_result.get('success', False)}")
        
        if "markdown" in raw_result:
            markdown_len = len(raw_result["markdown"])
            print(f"   Markdown 长度: {markdown_len:,} 字符")
        
        print()
        print("📝 格式化输出预览 (前 500 字符):")
        print("-" * 60)
        print(formatted_output[:500])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_google_search():
    """测试 Google Search"""
    print("\n" + "=" * 60)
    print("🔍 测试 3: Google Search")
    print("=" * 60)
    
    executor = MCPToolExecutor()
    
    # 测试参数
    tool_name = "google_search"
    parameters = {"num_results": 3}
    query = "CRISPR breakthrough 2024"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 查询: {query}")
    print(f"📋 参数: {parameters}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        results = raw_result.get("organic", raw_result.get("data", []))
        print(f"   返回数量: {len(results)}")
        
        if results:
            print(f"\n   第一条结果:")
            first = results[0]
            print(f"   - Title: {first.get('title', '')[:60]}...")
            print(f"   - URL: {first.get('link', first.get('url', ''))[:60]}...")
        
        print()
        print("📝 格式化输出预览 (前 500 字符):")
        print("-" * 60)
        print(formatted_output[:500])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 MCPToolExecutor 完整测试")
    print("=" * 60)
    
    # 检查环境变量
    print("\n📋 环境变量检查:")
    env_vars = {
        "MCP_TRANSPORT_HOST": os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1"),
        "MCP_TRANSPORT_PORT": os.environ.get("MCP_TRANSPORT_PORT", "8003"),
        "CRAWL4AI_API_URL": os.environ.get("CRAWL4AI_API_URL"),
        "CRAWL4AI_API_KEY": os.environ.get("CRAWL4AI_API_KEY"),
        "SERPER_API_KEY": os.environ.get("SERPER_API_KEY"),
    }
    
    for key, value in env_vars.items():
        if value:
            display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"  ✅ {key}: {display_value}")
        else:
            print(f"  ⚠️  {key}: 未设置")
    
    # 运行测试
    results = {}
    
    results["pubmed_search"] = await test_pubmed_search()
    results["browse_webpage"] = await test_browse_webpage()
    results["google_search"] = await test_google_search()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    for tool_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {tool_name:20s} : {status}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查配置")
        print()
        print("💡 常见问题:")
        print("1. 确保 MCP 服务器正在运行")
        print("2. 确保 Crawl4AI Docker 容器正在运行 (browse_webpage 需要)")
        print("3. 确保相关环境变量已设置")
    
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

