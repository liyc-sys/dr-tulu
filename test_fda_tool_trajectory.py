"""
测试 FDA Drug Label Search 工具
完整模拟轨迹生成过程中的工具调用
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "scripts" / "pubmed_data_generator"))

from trajectory_generator import MCPToolExecutor


class FDAExtendedMCPToolExecutor(MCPToolExecutor):
    """扩展的 MCP 工具执行器，支持 FDA 工具"""
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Tuple[Dict[str, Any], str]:
        """执行 MCP 工具调用，返回 (原始结果, 格式化的 tool_output)"""
        client = await self._get_client()
        
        # 映射工具名到 MCP 工具名（包含 FDA 工具）
        mcp_tool_mapping = {
            "pubmed_search": "pubmed_search",
            "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
            "google_search": "serper_google_webpage_search",
            "fda_drug_search": "fda_drug_label_search",  # FDA 工具映射
        }
        
        mcp_tool_name = mcp_tool_mapping.get(tool_name, tool_name)
        
        # 构建 MCP 参数
        mcp_params = self._build_mcp_params(tool_name, parameters, query)
        
        try:
            async with client:
                result = await client.call_tool(mcp_tool_name, mcp_params)
                
                if hasattr(result, "content") and result.content:
                    if hasattr(result.content[0], "text"):
                        raw_result = json.loads(result.content[0].text)
                    else:
                        raw_result = {"data": str(result.content[0])}
                else:
                    raw_result = {"error": "No content in response"}
                    
                # 格式化为 tool_output
                formatted_output = self._format_tool_output(tool_name, raw_result)
                return raw_result, formatted_output
                
        except Exception as e:
            error_result = {"error": str(e)}
            return error_result, f"<tool_output>Error: {str(e)}</tool_output>"
    
    def _build_mcp_params(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Dict[str, Any]:
        """构建 MCP 参数（包含 FDA 工具）"""
        if tool_name == "pubmed_search":
            return {
                "query": query,
                "limit": parameters.get("limit", 10),
                "offset": parameters.get("offset", 0)
            }
        elif tool_name == "browse_webpage":
            return {
                "url": query,
                "use_ai2_config": True,
            }
        elif tool_name == "google_search":
            return {
                "query": query,
                "num_results": parameters.get("num_results", 10)
            }
        elif tool_name == "fda_drug_search":
            # FDA 工具参数构建
            # query 是药物名称，focus 从 parameters 中获取
            return {
                "keyword": query,  # 药物名称
                "focus": parameters.get("focus", "general information"),  # 关注点
                "limit": parameters.get("limit", 3),  # 结果数量
                "use_llm_extraction": parameters.get("use_llm_extraction", True),  # 是否使用 LLM 提取
            }
        return {"query": query, **parameters}
    
    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        """将原始工具结果格式化为 <tool_output> 格式（包含 FDA 工具）"""
        # NOTE: Some MCP backends always include an "error" field (often null/None).
        # Treat it as an error only when it is non-empty.
        err = raw_result.get("error")
        if err is not None and err != "":
            return f"<tool_output>Error: {err}</tool_output>"
        
        if tool_name == "pubmed_search":
            snippets = []
            data = raw_result.get("data", [])
            for paper in data[:10]:  # 最多10篇
                pmid = paper.get("paperId", "unknown")
                title = paper.get("title", "No title")
                abstract = paper.get("abstract", "No abstract")
                year = paper.get("year", "N/A")
                venue = paper.get("venue", "N/A")
                authors = paper.get("authors", [])
                author_str = ", ".join([a.get("name", "") for a in authors[:3]])
                if len(authors) > 3:
                    author_str += " et al."
                
                snippet = f"""<snippet id="{pmid}">Title: {title}
Authors: {author_str} | Year: {year} | Journal: {venue}
Abstract: {abstract}</snippet>"""
                snippets.append(snippet)
            
            total = raw_result.get("total", len(data))
            header = f"Found {total} results. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "browse_webpage":
            md = raw_result.get("markdown") or ""
            if md:
                content = md[:8000]
            else:
                content = json.dumps(raw_result, ensure_ascii=False)[:2000]
            return f"<tool_output><webpage>{content}</webpage></tool_output>"
        
        elif tool_name == "google_search":
            results = raw_result.get("organic", raw_result.get("data", []))
            snippets = []
            for i, r in enumerate(results[:5]):
                title = r.get("title", "")
                snippet_text = r.get("snippet", r.get("description", ""))
                link = r.get("link", r.get("url", ""))
                snippets.append(f'<snippet id="G{i+1}">Title: {title}\n{snippet_text}\nURL: {link}</snippet>')
            return f"<tool_output>\n" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "fda_drug_search":
            # FDA 工具输出格式化
            keyword = raw_result.get("keyword", "unknown")
            focus = raw_result.get("focus", "general information")
            search_strategy = raw_result.get("search_strategy", "unknown")
            extracted_info = raw_result.get("extracted_info", [])
            
            if not extracted_info:
                return f"<tool_output>No FDA information found for drug: {keyword}</tool_output>"
            
            snippets = []
            for i, info in enumerate(extracted_info[:5]):  # 最多5条
                # 截断过长的信息
                info_text = info[:2000] if len(info) > 2000 else info
                snippet = f"""<snippet id="FDA-{i+1}">Drug: {keyword} | Focus: {focus} | Strategy: {search_strategy}
{info_text}</snippet>"""
                snippets.append(snippet)
            
            header = f"Found {len(extracted_info)} FDA information entries for {keyword} (focus: {focus}):\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        # 默认格式
        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False)[:2000]}</tool_output>"


async def test_fda_drug_search():
    """测试 FDA Drug Label Search"""
    print("\n" + "=" * 60)
    print("💊 测试 1: FDA Drug Label Search - 副作用")
    print("=" * 60)
    
    executor = FDAExtendedMCPToolExecutor()
    
    # 测试参数
    tool_name = "fda_drug_search"
    parameters = {
        "focus": "adverse reactions",  # 关注点：副作用
        "limit": 2,
        "use_llm_extraction": True
    }
    query = "aspirin"  # 药物名称
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物: {query}")
    print(f"📋 关注点: {parameters['focus']}")
    print(f"📋 参数: {parameters}")
    print("⏳ (这可能需要一些时间，包括 FDA API 调用和 LLM 提取...)")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if "error" in raw_result and raw_result["error"]:
            print(f"❌ 失败: {raw_result['error']}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   关键词: {raw_result.get('keyword', 'N/A')}")
        print(f"   关注点: {raw_result.get('focus', 'N/A')}")
        print(f"   搜索策略: {raw_result.get('search_strategy', 'N/A')}")
        print(f"   提取信息数量: {len(raw_result.get('extracted_info', []))}")
        
        extracted_info = raw_result.get("extracted_info", [])
        if extracted_info:
            print(f"\n   第一条提取信息预览:")
            first_info = extracted_info[0]
            preview = first_info[:200] if len(first_info) > 200 else first_info
            print(f"   {preview}...")
        
        print()
        print("📝 格式化输出预览 (前 800 字符):")
        print("-" * 60)
        print(formatted_output[:800])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fda_drug_search_indications():
    """测试 FDA Drug Label Search - 适应症"""
    print("\n" + "=" * 60)
    print("💊 测试 2: FDA Drug Label Search - 适应症和用法")
    print("=" * 60)
    
    executor = FDAExtendedMCPToolExecutor()
    
    # 测试参数
    tool_name = "fda_drug_search"
    parameters = {
        "focus": "indications and usage",  # 关注点：适应症和用法
        "limit": 1,
        "use_llm_extraction": True
    }
    query = "metformin"  # 药物名称
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物: {query}")
    print(f"📋 关注点: {parameters['focus']}")
    print("⏳ (这可能需要一些时间...)")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if "error" in raw_result and raw_result["error"]:
            print(f"❌ 失败: {raw_result['error']}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   关键词: {raw_result.get('keyword', 'N/A')}")
        print(f"   关注点: {raw_result.get('focus', 'N/A')}")
        print(f"   搜索策略: {raw_result.get('search_strategy', 'N/A')}")
        
        extracted_info = raw_result.get("extracted_info", [])
        if extracted_info:
            print(f"\n   提取信息预览:")
            print(f"   {extracted_info[0][:300]}...")
        
        print()
        print("📝 格式化输出预览 (前 600 字符):")
        print("-" * 60)
        print(formatted_output[:600])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fda_drug_search_warnings():
    """测试 FDA Drug Label Search - 警告"""
    print("\n" + "=" * 60)
    print("💊 测试 3: FDA Drug Label Search - 警告和注意事项")
    print("=" * 60)
    
    executor = FDAExtendedMCPToolExecutor()
    
    # 测试参数
    tool_name = "fda_drug_search"
    parameters = {
        "focus": "warnings and precautions",
        "limit": 1,
        "use_llm_extraction": True
    }
    query = "ibuprofen"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物: {query}")
    print(f"📋 关注点: {parameters['focus']}")
    print("⏳ (这可能需要一些时间...)")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if "error" in raw_result and raw_result["error"]:
            print(f"❌ 失败: {raw_result['error']}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   关键词: {raw_result.get('keyword', 'N/A')}")
        print(f"   搜索策略: {raw_result.get('search_strategy', 'N/A')}")
        
        extracted_info = raw_result.get("extracted_info", [])
        if extracted_info:
            print(f"\n   提取信息数量: {len(extracted_info)}")
            print(f"   第一条信息预览:")
            print(f"   {extracted_info[0][:250]}...")
        
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


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 FDA Drug Label Search Tool 完整测试")
    print("=" * 60)
    
    # 检查环境变量
    print("\n📋 环境变量检查:")
    env_vars = {
        "MCP_TRANSPORT_HOST": os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1"),
        "MCP_TRANSPORT_PORT": os.environ.get("MCP_TRANSPORT_PORT", "8003"),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
    }
    
    for key, value in env_vars.items():
        if value:
            if key == "OPENROUTER_API_KEY":
                display_value = value[:20] + "..." if len(value) > 20 else value
            else:
                display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"  ✅ {key}: {display_value}")
        else:
            print(f"  ⚠️  {key}: 未设置")
    
    if not env_vars.get("OPENROUTER_API_KEY"):
        print("\n⚠️  警告: OPENROUTER_API_KEY 未设置")
        print("   这将导致 LLM 提取功能失败")
        print("   建议设置: export OPENROUTER_API_KEY='your-api-key'")
    
    # 运行测试
    results = {}
    
    results["fda_adverse_reactions"] = await test_fda_drug_search()
    results["fda_indications"] = await test_fda_drug_search_indications()
    results["fda_warnings"] = await test_fda_drug_search_warnings()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name:30s} : {status}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查配置")
        print()
        print("💡 常见问题:")
        print("1. 确保 MCP 服务器正在运行:")
        print("   cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
        print("2. 确保 OPENROUTER_API_KEY 环境变量已设置（用于 LLM 提取）")
        print("3. 检查网络连接（FDA API 需要网络访问）")
        print("4. 如果 FDA API 调用失败，可能是速率限制，稍后重试")
    
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

