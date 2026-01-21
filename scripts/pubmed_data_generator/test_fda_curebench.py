"""
测试 CureBench 中 FDA 工具的使用
"""
import asyncio
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from answer_curebench_with_tools import CureBenchAnswerer


async def test_fda_tool():
    """测试 FDA 工具映射"""
    print("=" * 60)
    print("测试 CureBench FDA 工具映射")
    print("=" * 60)
    
    answerer = CureBenchAnswerer(
        local_model_url="http://localhost:8000/v1",
        model_name="test-model"
    )
    
    # 测试工具映射
    print("\n工具映射表:")
    for logical_name, mcp_name in answerer.TOOL_MAPPING.items():
        print(f"  {logical_name:20s} -> {mcp_name}")
    
    # 测试 FDA 工具调用
    print("\n\n测试 FDA 工具调用...")
    print("-" * 60)
    
    test_cases = [
        {
            "tool_name": "fda_drug_search",
            "parameters": {"focus": "adverse reactions"},
            "query": "aspirin"
        },
        {
            "tool_name": "fda_drug_search",
            "parameters": {"focus": "indications and usage"},
            "query": "metformin"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {test_case['tool_name']}({test_case['query']}, focus={test_case['parameters']['focus']})")
        
        try:
            raw_result, formatted_output = await answerer._execute_tool_with_mapping(
                test_case["tool_name"],
                test_case["parameters"],
                test_case["query"]
            )
            
            print(f"✓ 调用成功")
            print(f"原始结果键: {list(raw_result.keys())}")
            print(f"格式化输出预览:\n{formatted_output[:500]}...")
            
        except Exception as e:
            print(f"✗ 调用失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    print("注意: 需要 MCP 服务器运行在 127.0.0.1:8003")
    print("启动命令: cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
    print()
    
    asyncio.run(test_fda_tool())
