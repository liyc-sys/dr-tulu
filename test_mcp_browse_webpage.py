"""
测试通过 MCP 调用 browse_webpage (Docker 版本)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "scripts" / "pubmed_data_generator"))

from fastmcp import Client


async def test_mcp_browse_webpage():
    """测试 MCP 方式调用 browse_webpage (Docker 版本)"""
    
    # 读取 MCP 配置
    mcp_host = os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1")
    mcp_port = os.environ.get("MCP_TRANSPORT_PORT", "8003")
    mcp_url = f"http://{mcp_host}:{mcp_port}/mcp"
    
    print("=" * 60)
    print("🧪 测试 MCP browse_webpage (Docker 版本)")
    print("=" * 60)
    print()
    
    # 检查环境变量
    print("📋 环境变量检查:")
    print(f"  MCP_HOST: {mcp_host}")
    print(f"  MCP_PORT: {mcp_port}")
    print(f"  MCP_URL: {mcp_url}")
    
    crawl4ai_vars = {
        "CRAWL4AI_API_URL": os.environ.get("CRAWL4AI_API_URL"),
        "CRAWL4AI_API_KEY": os.environ.get("CRAWL4AI_API_KEY"),
        "CRAWL4AI_BLOCKLIST_PATH": os.environ.get("CRAWL4AI_BLOCKLIST_PATH"),
    }
    
    print(f"\n  Crawl4AI 配置:")
    for key, value in crawl4ai_vars.items():
        if value:
            display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"    ✅ {key}: {display_value}")
        else:
            print(f"    ⚠️  {key}: 未设置")
    print()
    
    # 创建 MCP 客户端
    client = Client(mcp_url, timeout=120)
    
    try:
        print("🔌 连接到 MCP 服务器...")
        async with client:
            # 测试工具调用
            test_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
            
            print(f"📄 测试 URL: {test_url}")
            print("⏳ 调用工具: crawl4ai_docker_fetch_webpage_content")
            print("   (这可能需要一些时间...)")
            print()
            
            # 调用工具
            result = await client.call_tool(
                "crawl4ai_docker_fetch_webpage_content",
                {
                    "url": test_url,
                    "use_ai2_config": True,  # 使用 AI2 配置
                    "ignore_links": True,
                    "bypass_cache": True,
                }
            )
            
            # 解析结果
            if hasattr(result, "content") and result.content:
                if hasattr(result.content[0], "text"):
                    raw_result = json.loads(result.content[0].text)
                else:
                    raw_result = {"data": str(result.content[0])}
            else:
                raw_result = {"error": "No content in response"}
            
            print("=" * 60)
            print("📊 结果分析")
            print("=" * 60)
            
            if "error" in raw_result:
                print(f"❌ 调用失败: {raw_result['error']}")
                return False
            
            # 显示结果信息
            print(f"✅ 调用成功！")
            print()
            
            print(f"📌 返回字段:")
            for key in raw_result.keys():
                print(f"   - {key}")
            print()
            
            # 显示 URL
            if "url" in raw_result:
                print(f"🔗 URL: {raw_result['url']}")
            
            # 显示成功状态
            if "success" in raw_result:
                status = "✅ 成功" if raw_result["success"] else "❌ 失败"
                print(f"📊 状态: {status}")
            
            # 显示内容长度
            if "markdown" in raw_result:
                markdown_len = len(raw_result["markdown"])
                print(f"📝 Markdown 长度: {markdown_len:,} 字符")
                print(f"📄 内容预览 (前 300 字符):")
                print("-" * 60)
                print(raw_result["markdown"][:300])
                print("-" * 60)
                print(f"📄 内容结尾 (后 200 字符):")
                print("-" * 60)
                print(raw_result["markdown"][-200:])
                print("-" * 60)
            
            if "fit_markdown" in raw_result and raw_result["fit_markdown"]:
                fit_len = len(raw_result["fit_markdown"])
                print(f"✂️  Fit Markdown 长度: {fit_len:,} 字符")
            
            # 显示错误信息（如果有）
            if "error" in raw_result and raw_result["error"]:
                print(f"⚠️  错误信息: {raw_result['error']}")
            
            print()
            print("=" * 60)
            print("✅ 测试完成！browse_webpage (Docker 版本) 工作正常")
            print("=" * 60)
            
            return True
            
    except Exception as e:
        print("=" * 60)
        print(f"❌ 测试失败")
        print("=" * 60)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print()
        
        # 给出排查建议
        print("💡 排查建议:")
        print("1. 确保 MCP 服务器正在运行:")
        print(f"   curl http://{mcp_host}:{mcp_port}/health")
        print()
        print("2. 确保环境变量已设置:")
        print("   export CRAWL4AI_API_URL='http://localhost:11235'")
        print("   export CRAWL4AI_API_KEY='mamba-out'")
        print("   export CRAWL4AI_BLOCKLIST_PATH='/path/to/blocklist.txt'")
        print()
        print("3. 确保 Crawl4AI Docker 容器正在运行:")
        print("   docker ps | grep crawl4ai")
        print()
        
        return False


if __name__ == "__main__":
    success = asyncio.run(test_mcp_browse_webpage())
    sys.exit(0 if success else 1)

