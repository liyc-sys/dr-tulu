"""
测试本地DR-Tulu-8B模型是否正常工作
包括：模型实例连接测试、简单问答测试、完整轨迹生成测试
"""
import asyncio
import httpx
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "scripts" / "pubmed_data_generator"))

from generate_trajectory_from_questions import LocalModelTrajectoryGenerator


# 模型端口列表
MODEL_PORTS = [8000, 8001, 8002, 8009, 8004, 8005, 8006, 8007]


async def test_model_connection(port: int) -> bool:
    """测试单个模型实例连接"""
    url = f"http://localhost:{port}/v1"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 测试 /v1/models 接口
            response = await client.get(f"{url}/models")
            if response.status_code == 200:
                return True
            return False
        except Exception:
            return False


async def test_all_connections():
    """测试所有模型实例连接"""
    print("\n" + "=" * 60)
    print("🔌 测试 1: 模型实例连接")
    print("=" * 60)
    
    results = {}
    for port in MODEL_PORTS:
        success = await test_model_connection(port)
        status = "✅" if success else "❌"
        print(f"  端口 {port}: {status}")
        results[port] = success
    
    ok_count = sum(results.values())
    total = len(MODEL_PORTS)
    print(f"\n📊 结果: {ok_count}/{total} 个实例正常")
    
    return ok_count, results


async def test_model_generation(port: int) -> bool:
    """测试模型生成能力"""
    url = f"http://localhost:{port}/v1"
    
    print(f"\n正在测试端口 {port}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "DR-Tulu-8B",
                    "messages": [
                        {"role": "user", "content": "Hello, can you help me?"}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    print(f"  ✅ 生成成功")
                    print(f"  📝 回复: {content[:100]}...")
                    return True
            
            print(f"  ❌ 生成失败: HTTP {response.status_code}")
            return False
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")
            return False


async def test_simple_generation():
    """测试简单生成"""
    print("\n" + "=" * 60)
    print("💬 测试 2: 简单生成测试")
    print("=" * 60)
    
    # 只测试第一个可用的实例
    for port in MODEL_PORTS:
        if await test_model_connection(port):
            success = await test_model_generation(port)
            if success:
                print(f"\n✅ 端口 {port} 生成测试通过")
                return True
            else:
                print(f"\n⚠️ 端口 {port} 生成测试失败，尝试下一个...")
    
    print("\n❌ 所有实例生成测试失败")
    return False


async def test_trajectory_generation():
    """测试完整轨迹生成"""
    print("\n" + "=" * 60)
    print("🧬 测试 3: 完整轨迹生成测试")
    print("=" * 60)
    
    # 找第一个可用的端口
    available_port = None
    for port in MODEL_PORTS:
        if await test_model_connection(port):
            available_port = port
            break
    
    if not available_port:
        print("❌ 没有可用的模型实例")
        return False
    
    print(f"使用端口: {available_port}")
    
    # 创建轨迹生成器
    generator = LocalModelTrajectoryGenerator(
        local_model_url=f"http://localhost:{available_port}/v1",
        model_name="DR-Tulu-8B",
        max_turns=5  # 限制轮次，加快测试
    )
    
    # 简单的测试问题
    test_question = "What is CRISPR gene editing?"
    
    print(f"测试问题: {test_question}")
    print("⏳ 生成轨迹中（可能需要1-2分钟）...")
    
    try:
        trajectory = await generator.generate_trajectory(test_question)
        
        print("\n✅ 轨迹生成成功！")
        print(f"\n📊 轨迹信息:")
        print(f"  - 工具调用次数: {trajectory.total_tool_calls}")
        print(f"  - 使用的工具: {trajectory.tools_used}")
        print(f"  - PMIDs引用: {trajectory.pmids_cited}")
        print(f"  - 最终答案长度: {len(trajectory.final_answer)} 字符")
        
        if trajectory.total_tool_calls > 0:
            print(f"\n📋 第一次工具调用:")
            first_call = trajectory.tool_calls[0]
            print(f"  - 工具: {first_call.tool_name}")
            print(f"  - 查询: {first_call.query}")
        
        print(f"\n📝 轨迹预览 (前300字符):")
        print("-" * 60)
        print(trajectory.interleaved_text[:300])
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 轨迹生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mcp_server():
    """测试MCP服务器连接"""
    print("\n" + "=" * 60)
    print("🔧 测试 4: MCP服务器连接")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get("http://127.0.0.1:8003/mcp/health")
            if response.status_code == 200:
                print("  ✅ MCP服务器正常 (端口8003)")
                return True
            else:
                print(f"  ❌ MCP服务器异常: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ MCP服务器无响应: {e}")
            return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 本地DR-Tulu-8B模型完整测试")
    print("=" * 60)
    print(f"\n测试端口: {MODEL_PORTS}")
    
    # 运行测试
    results = {}
    
    # 1. 连接测试
    ok_count, connection_results = await test_all_connections()
    results["connection"] = ok_count > 0
    
    if ok_count == 0:
        print("\n❌ 没有可用的模型实例，停止后续测试")
        print("\n💡 请确保模型实例已启动:")
        print("   参考: scripts/pubmed_data_generator/start_local_model.sh")
        return False
    
    # 2. 简单生成测试
    results["generation"] = await test_simple_generation()
    
    # 3. MCP服务器测试
    results["mcp"] = await test_mcp_server()
    
    # 4. 完整轨迹生成测试（如果前面都通过）
    if results["generation"] and results["mcp"]:
        results["trajectory"] = await test_trajectory_generation()
    else:
        print("\n⚠️ 跳过轨迹生成测试（基础测试未通过）")
        results["trajectory"] = False
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    print(f"  模型实例连接:      {'✅ 通过' if results['connection'] else '❌ 失败'} ({ok_count}/{len(MODEL_PORTS)} 可用)")
    print(f"  简单生成测试:      {'✅ 通过' if results['generation'] else '❌ 失败'}")
    print(f"  MCP服务器连接:     {'✅ 通过' if results['mcp'] else '❌ 失败'}")
    print(f"  完整轨迹生成:      {'✅ 通过' if results['trajectory'] else '❌ 失败'}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("🎉 所有测试通过！可以开始生成轨迹")
        print()
        print("运行命令:")
        print("  cd /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator")
        print("  bash run_multi_instance.sh /path/to/questions.jsonl")
    else:
        print("⚠️ 部分测试失败，请检查:")
        if not results['connection']:
            print("  ❌ 启动模型实例 (start_local_model.sh)")
        if not results['mcp']:
            print("  ❌ 启动MCP服务器")
        if not results['generation']:
            print("  ❌ 检查模型是否正常响应")
    
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

