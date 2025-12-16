#!/usr/bin/env python3
"""
测试脚本：验证 GPT-5 轨迹生成功能
"""
import asyncio
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 设置环境变量
os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")


async def test_trajectory_generation():
    """测试轨迹生成"""
    print("\n" + "=" * 60)
    print("测试 GPT-5 轨迹生成")
    print("=" * 60)
    
    from trajectory_generator import GPT5TrajectoryGenerator, generate_content_rubrics_from_trajectory
    
    # 使用 gpt-4o 作为测试
    generator = GPT5TrajectoryGenerator(model="openai/gpt-4o")
    
    question = "BRCA1 基因突变与乳腺癌 PARP 抑制剂治疗的疗效关系是什么？请引用具体研究数据。"
    
    print(f"\n问题: {question}\n")
    print("正在生成工具调用轨迹（需要 MCP 服务器运行）...")
    
    try:
        trajectory = await generator.generate_trajectory(question)
        
        print(f"\n✓ 轨迹生成成功!")
        print(f"  - 步骤数: {len(trajectory.steps)}")
        print(f"  - 工具调用次数: {trajectory.total_tool_calls}")
        print(f"  - 使用的工具: {trajectory.tools_used}")
        
        print(f"\n轨迹步骤:")
        for step in trajectory.steps:
            print(f"  [{step.step_index}] {step.role}")
            if step.tool_calls:
                for tc in step.tool_calls:
                    print(f"      -> {tc.tool_name}({json.dumps(tc.arguments, ensure_ascii=False)[:50]}...)")
            if step.content:
                print(f"      内容: {step.content[:100]}...")
        
        print(f"\n最终回答 (前300字):")
        print(trajectory.final_answer[:300] + "...")
        
        # 生成 content rubrics
        print("\n正在生成内容 rubrics...")
        content_rubrics = await generate_content_rubrics_from_trajectory(question, trajectory)
        
        print(f"\n✓ 生成了 {len(content_rubrics)} 条内容 rubrics:")
        for r in content_rubrics:
            print(f"  - {r['title']}: {r['description'][:60]}...")
        
        return trajectory, content_rubrics
        
    except Exception as e:
        print(f"\n✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


async def test_full_pipeline():
    """测试完整流程"""
    print("\n" + "=" * 60)
    print("测试完整数据生成流程")
    print("=" * 60)
    
    from generate_trajectory_dataset import TrajectoryDatasetGenerator
    
    generator = TrajectoryDatasetGenerator(
        model="openai/gpt-4o",
        num_questions=2,  # 测试时只生成 2 个
        language="zh"
    )
    
    try:
        samples = await generator.generate_dataset()
        
        if samples:
            print(f"\n✓ 生成了 {len(samples)} 个完整样本")
            
            for i, sample in enumerate(samples, 1):
                print(f"\n样本 {i}:")
                print(f"  问题: {sample.question[:50]}...")
                print(f"  工具调用次数: {sample.metadata.get('total_tool_calls', 0)}")
                print(f"  工具 rubrics: {len(sample.tool_rubrics)} 条")
                print(f"  内容 rubrics: {len(sample.content_rubrics)} 条")
            
            # 保存到测试目录
            test_output = os.path.join(SCRIPT_DIR, "../../pubmed_training_data/test_trajectory")
            generator.save_dataset(test_output)
            
        return samples
        
    except Exception as e:
        print(f"\n✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """运行测试"""
    print("=" * 60)
    print("PubMed 轨迹数据生成器测试")
    print("=" * 60)
    print("\n注意事项:")
    print("1. 需要设置 OPENROUTER_API_KEY 环境变量")
    print("2. 需要 MCP 服务器正在运行:")
    print("   cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=str, choices=["trajectory", "full"], 
                        default="trajectory", help="运行哪个测试")
    args = parser.parse_args()
    
    if args.test == "trajectory":
        await test_trajectory_generation()
    else:
        await test_full_pipeline()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

