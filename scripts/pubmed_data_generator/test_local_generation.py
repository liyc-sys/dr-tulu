"""
测试本地模型轨迹生成功能
这个脚本会生成2-3个问题的轨迹，用于验证功能是否正常
"""
import asyncio
import json
import tempfile
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from generate_trajectory_from_questions import QuestionBasedTrajectoryGenerator


async def test_with_sample_questions():
    """使用示例问题测试"""
    
    # 创建临时问题文件
    sample_questions = [
        {
            "question": "What are the latest developments in CRISPR gene editing for sickle cell disease?",
            "topic": "Gene & Cell Therapy",
            "question_type": "review",
            "expected_search_terms": ["CRISPR", "sickle cell disease", "gene editing", "BCL11A"]
        },
        {
            "question": "Compare the efficacy of PD-1 inhibitors versus CTLA-4 inhibitors in melanoma treatment.",
            "topic": "Cancer Immunotherapy",
            "question_type": "efficacy_comparison",
            "expected_search_terms": ["PD-1", "CTLA-4", "melanoma", "immunotherapy"]
        }
    ]
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
        for q in sample_questions:
            f.write(json.dumps(q, ensure_ascii=False) + '\n')
        temp_file = f.name
    
    print(f"创建临时问题文件: {temp_file}")
    
    # 测试参数
    local_model_url = "http://localhost:8000/v1"
    model_name = "Qwen3-8B"
    
    print("\n" + "=" * 60)
    print("开始测试")
    print("=" * 60)
    print(f"本地模型URL: {local_model_url}")
    print(f"模型名称: {model_name}")
    print(f"测试问题数: {len(sample_questions)}")
    
    # 创建生成器
    generator = QuestionBasedTrajectoryGenerator(
        questions_file=temp_file,
        local_model_url=local_model_url,
        model_name=model_name,
        output_dir="../../pubmed_training_data",
        incremental_save=True
    )
    
    try:
        # 生成轨迹
        samples = await generator.generate_dataset(concurrency=2, limit=2)
        
        # 保存结果
        generator.save_dataset()
        
        # 显示结果
        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"✓ 成功生成 {len(samples)} 个轨迹")
        
        for i, sample in enumerate(samples, 1):
            print(f"\n--- 样本 {i} ---")
            print(f"问题: {sample.question[:80]}...")
            print(f"工具调用次数: {sample.metadata['total_tool_calls']}")
            print(f"使用的工具: {sample.metadata['tools_used']}")
            print(f"PMIDs引用: {sample.trajectory.get('pmids_cited', [])}")
            print(f"最终答案长度: {len(sample.trajectory.get('final_answer', ''))} 字符")
        
        print("\n✓ 测试成功！")
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理临时文件
        import os
        try:
            os.unlink(temp_file)
            print(f"\n清理临时文件: {temp_file}")
        except:
            pass
    
    return True


async def test_connection():
    """测试本地模型连接"""
    import httpx
    
    local_model_url = "http://localhost:8000/v1"
    
    print("测试本地模型连接...")
    print(f"URL: {local_model_url}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 测试 /v1/models 接口
            response = await client.get(f"{local_model_url}/models")
            if response.status_code == 200:
                print("✓ 模型列表接口可访问")
                models = response.json()
                print(f"  可用模型: {models}")
            else:
                print(f"⚠ 模型列表接口返回状态码: {response.status_code}")
        except Exception as e:
            print(f"✗ 无法连接到本地模型: {e}")
            print("\n请确保：")
            print("1. 本地模型服务已启动")
            print("2. 服务地址正确（默认: http://localhost:8000/v1）")
            print("3. 使用 vLLM 或其他 OpenAI 兼容的服务部署")
            return False
    
    return True


async def main():
    """主测试函数"""
    print("=" * 60)
    print("本地模型轨迹生成 - 测试脚本")
    print("=" * 60)
    
    # 1. 测试连接
    print("\n步骤 1: 测试本地模型连接")
    if not await test_connection():
        print("\n⚠️ 本地模型连接失败，跳过轨迹生成测试")
        print("请先启动本地模型服务，例如：")
        print("  vllm serve Qwen/Qwen3-8B --port 8000")
        return
    
    # 2. 测试轨迹生成
    print("\n步骤 2: 测试轨迹生成")
    await test_with_sample_questions()


if __name__ == "__main__":
    asyncio.run(main())

