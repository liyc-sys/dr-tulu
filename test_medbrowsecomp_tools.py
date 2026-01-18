"""
测试 MedBrowseComp MCP 工具
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


class MedBrowseCompMCPToolExecutor(MCPToolExecutor):
    """扩展的 MCP 工具执行器，支持 MedBrowseComp 工具"""
    
    def _build_mcp_params(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Dict[str, Any]:
        """构建 MCP 参数"""
        mcp_params = {}
        
        if tool_name == "medbrowsecomp_search":
            mcp_params["query"] = query
            if "prefer_url" in parameters:
                mcp_params["prefer_url"] = parameters["prefer_url"]
            if "reason" in parameters:
                mcp_params["reason"] = parameters["reason"]
        
        elif tool_name == "get_trial_info":
            mcp_params["nct_id"] = query
        
        elif tool_name in ["get_drug_patents", "get_drug_approvals", "get_drug_exclusivities"]:
            mcp_params["ingredients"] = query
        
        else:
            # 默认使用原始参数
            mcp_params = parameters.copy()
            mcp_params["query"] = query
        
        return mcp_params
    
    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        """将原始工具结果格式化为 <tool_output> 格式"""
        # NOTE: Some MCP backends always include an "error" field (often null/None).
        # Treat it as an error only when it is non-empty.
        err = raw_result.get("error")
        if err is not None and err != "":
            return f"<tool_output>Error: {err}</tool_output>"
        
        if not raw_result.get("success", False):
            error_msg = raw_result.get("error", "Unknown error")
            return f"<tool_output>Error: {error_msg}</tool_output>"
        
        if tool_name == "medbrowsecomp_search":
            metadata = raw_result.get("_search_metadata", {})
            func_called = metadata.get("function_called", "")
            
            if func_called == "get_trial_info":
                # 临床试验信息
                snippets = []
                nct_id = raw_result.get("nct_id", "")
                sponsor = raw_result.get("sponsor", "")
                status = raw_result.get("recruitment_status", "")
                ingredients = raw_result.get("ingredients", [])
                sources = raw_result.get("sources", [])
                
                snippet_parts = [f"NCT ID: {nct_id}"]
                if sponsor:
                    snippet_parts.append(f"Sponsor: {sponsor}")
                if status:
                    snippet_parts.append(f"Status: {status}")
                if ingredients:
                    ing_str = ", ".join(ingredients) if isinstance(ingredients, list) else str(ingredients)
                    snippet_parts.append(f"Ingredients: {ing_str}")
                
                snippet = f'<snippet id="{nct_id}">\n' + "\n".join(snippet_parts)
                if sources:
                    snippet += f"\nSource: {sources[0]}"
                snippet += "\n</snippet>"
                snippets.append(snippet)
                
                return f"<tool_output>\n" + "\n".join(snippets) + "\n</tool_output>"
            
            elif func_called == "get_drug_patents":
                # 专利信息
                snippets = []
                patents = raw_result.get("patents", [])
                ingredients = raw_result.get("ingredients", [])
                
                for i, pat in enumerate(patents[:5]):
                    snippet_parts = [
                        f"Patent Number: {pat.get('number', 'N/A')}",
                        f"Jurisdiction: {pat.get('jurisdiction', 'N/A')}",
                        f"Expiry Date: {pat.get('expiry_date', 'N/A')}",
                    ]
                    if pat.get("notes"):
                        snippet_parts.append(f"Notes: {pat['notes']}")
                    
                    snippet = f'<snippet id="patent_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                    snippets.append(snippet)
                
                header = f"Found {len(patents)} patents for {ingredients}. Showing top {len(snippets)}:\n"
                return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
            
            elif func_called == "get_drug_approvals":
                # 批准信息
                snippets = []
                approvals = raw_result.get("approvals", [])
                ingredients = raw_result.get("ingredients", [])
                
                for i, appr in enumerate(approvals[:5]):
                    snippet_parts = [
                        f"Product Name: {appr.get('product_name', 'N/A')}",
                        f"Active Ingredient: {appr.get('active_ingredient', 'N/A')}",
                        f"Approval Date: {appr.get('approval_date', 'N/A')}",
                        f"Status: {appr.get('status', 'N/A')}",
                    ]
                    if appr.get("marketing_authorisation_holder"):
                        snippet_parts.append(f"Company: {appr['marketing_authorisation_holder']}")
                    
                    snippet = f'<snippet id="approval_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                    snippets.append(snippet)
                
                header = f"Found {len(approvals)} approvals for {ingredients}. Showing top {len(snippets)}:\n"
                return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
            
            elif func_called == "get_drug_exclusivities":
                # 独占期信息
                snippets = []
                exclusivities = raw_result.get("exclusivities", [])
                ingredients = raw_result.get("ingredients", [])
                
                for i, excl in enumerate(exclusivities[:5]):
                    snippet_parts = [
                        f"Type: {excl.get('type', 'N/A')}",
                        f"Region: {excl.get('region', 'N/A')}",
                        f"Start Date: {excl.get('start_date', 'N/A')}",
                        f"End Date: {excl.get('end_date', 'N/A')}",
                    ]
                    if excl.get("notes"):
                        snippet_parts.append(f"Notes: {excl['notes']}")
                    
                    snippet = f'<snippet id="exclusivity_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                    snippets.append(snippet)
                
                header = f"Found {len(exclusivities)} exclusivities for {ingredients}. Showing top {len(snippets)}:\n"
                return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "get_trial_info":
            snippets = []
            nct_id = raw_result.get("nct_id", "")
            sponsor = raw_result.get("sponsor", "")
            status = raw_result.get("recruitment_status", "")
            ingredients = raw_result.get("ingredients", [])
            sources = raw_result.get("sources", [])
            
            snippet_parts = [f"NCT ID: {nct_id}"]
            if sponsor:
                snippet_parts.append(f"Sponsor: {sponsor}")
            if status:
                snippet_parts.append(f"Status: {status}")
            if ingredients:
                ing_str = ", ".join(ingredients) if isinstance(ingredients, list) else str(ingredients)
                snippet_parts.append(f"Ingredients: {ing_str}")
            
            snippet = f'<snippet id="{nct_id}">\n' + "\n".join(snippet_parts)
            if sources:
                snippet += f"\nSource: {sources[0]}"
            snippet += "\n</snippet>"
            snippets.append(snippet)
            
            return f"<tool_output>\n" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "get_drug_patents":
            snippets = []
            patents = raw_result.get("patents", [])
            ingredients = raw_result.get("ingredients", [])
            
            for i, pat in enumerate(patents[:5]):
                snippet_parts = [
                    f"Patent Number: {pat.get('number', 'N/A')}",
                    f"Jurisdiction: {pat.get('jurisdiction', 'N/A')}",
                    f"Expiry Date: {pat.get('expiry_date', 'N/A')}",
                ]
                if pat.get("notes"):
                    snippet_parts.append(f"Notes: {pat['notes']}")
                
                snippet = f'<snippet id="patent_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                snippets.append(snippet)
            
            header = f"Found {len(patents)} patents for {ingredients}. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "get_drug_approvals":
            snippets = []
            approvals = raw_result.get("approvals", [])
            ingredients = raw_result.get("ingredients", [])
            
            for i, appr in enumerate(approvals[:5]):
                snippet_parts = [
                    f"Product Name: {appr.get('product_name', 'N/A')}",
                    f"Active Ingredient: {appr.get('active_ingredient', 'N/A')}",
                    f"Approval Date: {appr.get('approval_date', 'N/A')}",
                    f"Status: {appr.get('status', 'N/A')}",
                ]
                if appr.get("marketing_authorisation_holder"):
                    snippet_parts.append(f"Company: {appr['marketing_authorisation_holder']}")
                
                snippet = f'<snippet id="approval_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                snippets.append(snippet)
            
            header = f"Found {len(approvals)} approvals for {ingredients}. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "get_drug_exclusivities":
            snippets = []
            exclusivities = raw_result.get("exclusivities", [])
            ingredients = raw_result.get("ingredients", [])
            
            for i, excl in enumerate(exclusivities[:5]):
                snippet_parts = [
                    f"Type: {excl.get('type', 'N/A')}",
                    f"Region: {excl.get('region', 'N/A')}",
                    f"Start Date: {excl.get('start_date', 'N/A')}",
                    f"End Date: {excl.get('end_date', 'N/A')}",
                ]
                if excl.get("notes"):
                    snippet_parts.append(f"Notes: {excl['notes']}")
                
                snippet = f'<snippet id="exclusivity_{i+1}">\n' + "\n".join(snippet_parts) + "\n</snippet>"
                snippets.append(snippet)
            
            header = f"Found {len(exclusivities)} exclusivities for {ingredients}. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        # 默认格式化
        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False)[:2000]}</tool_output>"
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Tuple[Dict[str, Any], str]:
        """执行 MCP 工具调用，返回 (原始结果, 格式化的 tool_output)"""
        client = await self._get_client()
        
        # 映射工具名到 MCP 工具名
        mcp_tool_mapping = {
            "medbrowsecomp_search": "medbrowsecomp_search",
            "get_trial_info": "get_trial_info",
            "get_drug_patents": "get_drug_patents",
            "get_drug_approvals": "get_drug_approvals",
            "get_drug_exclusivities": "get_drug_exclusivities",
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


async def test_medbrowsecomp_search():
    """测试统一的 MedBrowseComp 搜索工具"""
    print("\n" + "=" * 60)
    print("🔍 测试 1: MedBrowseComp Search (统一搜索)")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数 - NCT 编号查询
    tool_name = "medbrowsecomp_search"
    parameters = {}
    query = "NCT02838420"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 查询: {query}")
    print(f"📋 参数: {parameters}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Success: {raw_result.get('success', False)}")
        
        metadata = raw_result.get("_search_metadata", {})
        func_called = metadata.get("function_called", "")
        print(f"   调用的函数: {func_called}")
        
        if "nct_id" in raw_result:
            print(f"   NCT ID: {raw_result.get('nct_id')}")
        if "sponsor" in raw_result:
            print(f"   Sponsor: {raw_result.get('sponsor')}")
        if "recruitment_status" in raw_result:
            print(f"   Status: {raw_result.get('recruitment_status')}")
        
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


async def test_get_trial_info():
    """测试获取临床试验信息"""
    print("\n" + "=" * 60)
    print("🏥 测试 2: Get Trial Info")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数
    tool_name = "get_trial_info"
    parameters = {}
    query = "NCT02838420"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 NCT ID: {query}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   NCT ID: {raw_result.get('nct_id')}")
        print(f"   Sponsor: {raw_result.get('sponsor', 'N/A')}")
        print(f"   Status: {raw_result.get('recruitment_status', 'N/A')}")
        
        ingredients = raw_result.get("ingredients", [])
        if ingredients:
            if isinstance(ingredients, list):
                print(f"   Ingredients: {', '.join(ingredients)}")
            else:
                print(f"   Ingredients: {ingredients}")
        
        sources = raw_result.get("sources", [])
        if sources:
            print(f"   Source: {sources[0]}")
        
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


async def test_get_drug_patents():
    """测试获取药物专利信息"""
    print("\n" + "=" * 60)
    print("📜 测试 3: Get Drug Patents")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数
    tool_name = "get_drug_patents"
    parameters = {}
    query = "crizotinib"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物成分: {query}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Ingredients: {raw_result.get('ingredients', [])}")
        print(f"   Count: {raw_result.get('count', 0)}")
        
        patents = raw_result.get("patents", [])
        if patents:
            print(f"\n   第一条专利:")
            first_patent = patents[0]
            print(f"   - Number: {first_patent.get('number', 'N/A')}")
            print(f"   - Jurisdiction: {first_patent.get('jurisdiction', 'N/A')}")
            print(f"   - Expiry Date: {first_patent.get('expiry_date', 'N/A')}")
        
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


async def test_get_drug_approvals():
    """测试获取药物批准信息"""
    print("\n" + "=" * 60)
    print("✅ 测试 4: Get Drug Approvals")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数
    tool_name = "get_drug_approvals"
    parameters = {}
    query = "crizotinib"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物成分: {query}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Ingredients: {raw_result.get('ingredients', [])}")
        print(f"   Count: {raw_result.get('count', 0)}")
        
        approvals = raw_result.get("approvals", [])
        if approvals:
            print(f"\n   第一条批准信息:")
            first_approval = approvals[0]
            print(f"   - Product Name: {first_approval.get('product_name', 'N/A')}")
            print(f"   - Active Ingredient: {first_approval.get('active_ingredient', 'N/A')}")
            print(f"   - Approval Date: {first_approval.get('approval_date', 'N/A')}")
            print(f"   - Company: {first_approval.get('marketing_authorisation_holder', 'N/A')}")
        
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


async def test_get_drug_exclusivities():
    """测试获取药物独占期信息"""
    print("\n" + "=" * 60)
    print("🔒 测试 5: Get Drug Exclusivities")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数
    tool_name = "get_drug_exclusivities"
    parameters = {}
    query = "crizotinib"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 药物成分: {query}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Ingredients: {raw_result.get('ingredients', [])}")
        print(f"   Count: {raw_result.get('count', 0)}")
        
        exclusivities = raw_result.get("exclusivities", [])
        if exclusivities:
            print(f"\n   第一条独占期信息:")
            first_excl = exclusivities[0]
            print(f"   - Type: {first_excl.get('type', 'N/A')}")
            print(f"   - Region: {first_excl.get('region', 'N/A')}")
            print(f"   - Start Date: {first_excl.get('start_date', 'N/A')}")
            print(f"   - End Date: {first_excl.get('end_date', 'N/A')}")
        
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


async def test_medbrowsecomp_search_with_reason():
    """测试带 reason 参数的统一搜索"""
    print("\n" + "=" * 60)
    print("🔍 测试 6: MedBrowseComp Search (带 reason 参数)")
    print("=" * 60)
    
    executor = MedBrowseCompMCPToolExecutor()
    
    # 测试参数 - 查询专利
    tool_name = "medbrowsecomp_search"
    parameters = {"reason": "patent"}
    query = "ingredients crizotinib"
    
    print(f"📋 工具: {tool_name}")
    print(f"📋 查询: {query}")
    print(f"📋 参数: {parameters}")
    print()
    
    try:
        raw_result, formatted_output = await executor.execute_tool(
            tool_name, parameters, query
        )
        
        if not raw_result.get("success", False):
            print(f"❌ 失败: {raw_result.get('error', 'Unknown error')}")
            return False
        
        print("✅ 调用成功！")
        print()
        print("📊 原始结果:")
        print(f"   Success: {raw_result.get('success', False)}")
        
        metadata = raw_result.get("_search_metadata", {})
        func_called = metadata.get("function_called", "")
        print(f"   调用的函数: {func_called}")
        
        if func_called == "get_drug_patents":
            patents = raw_result.get("patents", [])
            print(f"   专利数量: {len(patents)}")
            if patents:
                print(f"   第一条专利号: {patents[0].get('number', 'N/A')}")
        
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
    print("🧪 MedBrowseComp MCP 工具完整测试")
    print("=" * 60)
    
    # 检查环境变量
    print("\n📋 环境变量检查:")
    env_vars = {
        "MCP_TRANSPORT_HOST": os.environ.get("MCP_TRANSPORT_HOST", "127.0.0.1"),
        "MCP_TRANSPORT_PORT": os.environ.get("MCP_TRANSPORT_PORT", "8003"),
        "ORANGE_BOOK_CACHE_DIR": os.environ.get("ORANGE_BOOK_CACHE_DIR"),
        "ORANGE_BOOK_ZIP_URL": os.environ.get("ORANGE_BOOK_ZIP_URL"),
    }
    
    for key, value in env_vars.items():
        if value:
            display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"  ✅ {key}: {display_value}")
        else:
            print(f"  ⚠️  {key}: 未设置")
    
    # 运行测试
    results = {}
    
    results["medbrowsecomp_search"] = await test_medbrowsecomp_search()
    results["get_trial_info"] = await test_get_trial_info()
    results["get_drug_patents"] = await test_get_drug_patents()
    results["get_drug_approvals"] = await test_get_drug_approvals()
    results["get_drug_exclusivities"] = await test_get_drug_exclusivities()
    results["medbrowsecomp_search_with_reason"] = await test_medbrowsecomp_search_with_reason()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    for tool_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {tool_name:35s} : {status}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查配置")
        print()
        print("💡 常见问题:")
        print("1. 确保 MCP 服务器正在运行")
        print("2. 确保网络连接正常（需要访问 ClinicalTrials.gov 和 FDA Orange Book）")
        print("3. 如果 Orange Book 工具失败，可以设置 ORANGE_BOOK_CACHE_DIR 环境变量")
        print("4. 如果 Orange Book ZIP 下载失败，可以设置 ORANGE_BOOK_ZIP_URL 环境变量")
        print()
        print("启动 MCP server:")
        print("cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
    
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

