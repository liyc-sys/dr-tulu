#!/usr/bin/env python3
"""
测试脚本：验证 PubMed 数据生成器各组件
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# 确保能找到 config 模块（支持绝对路径运行）
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 设置环境变量
os.environ.setdefault("MCP_TRANSPORT", "StreamableHttpTransport")
os.environ.setdefault("MCP_TRANSPORT_PORT", "8003")
os.environ.setdefault("MCP_TRANSPORT_HOST", "127.0.0.1")


async def test_pubmed_client():
    """测试 PubMed MCP 客户端"""
    print("\n" + "=" * 60)
    print("测试 1: PubMed MCP 客户端")
    print("=" * 60)
    
    from pubmed_client import PubMedMCPClient
    
    client = PubMedMCPClient()
    query = "BRCA1 breast cancer PARP inhibitor"
    
    print(f"查询: {query}")
    
    try:
        evidence = await client.search(query, limit=5)
        print(f"✓ 成功! 找到 {len(evidence.papers)} 篇论文")
        
        for i, paper in enumerate(evidence.papers[:3], 1):
            print(f"\n  [{i}] PMID: {paper.pmid}")
            print(f"      标题: {paper.title[:60]}...")
            print(f"      年份: {paper.year} | 期刊: {paper.venue}")
        
        return evidence
    except Exception as e:
        print(f"✗ 失败: {e}")
        return None


async def test_topic_generator():
    """测试主题生成器"""
    print("\n" + "=" * 60)
    print("测试 2: 主题簇生成器")
    print("=" * 60)
    
    from topic_generator import generate_topic_clusters, generate_query_templates
    
    try:
        # 生成 3 个主题簇
        clusters = await generate_topic_clusters(3)
        print(f"✓ 生成了 {len(clusters)} 个主题簇")
        
        for cluster in clusters:
            print(f"\n  - {cluster['name']} ({cluster['category']})")
            print(f"    {cluster['description'][:50]}...")
        
        # 为第一个主题簇生成查询模板
        if clusters:
            queries = await generate_query_templates(clusters[0], 3)
            print(f"\n✓ 为 '{clusters[0]['name']}' 生成了 {len(queries)} 个查询模板")
            
            for q in queries:
                print(f"  - [{q['query_type']}] {q['template'][:50]}...")
        
        return clusters
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_question_generator(evidence=None):
    """测试问题生成器"""
    print("\n" + "=" * 60)
    print("测试 3: 问题生成器")
    print("=" * 60)
    
    from question_generator import generate_question_from_evidence
    
    if evidence is None:
        from pubmed_client import PubMedMCPClient
        client = PubMedMCPClient()
        evidence = await client.search("cancer immunotherapy checkpoint", limit=5)
    
    if not evidence or not evidence.papers:
        print("✗ 无证据可用")
        return None
    
    try:
        question = await generate_question_from_evidence(
            evidence=evidence,
            language="zh",
            question_id="test_q_001"
        )
        
        if question:
            print(f"✓ 生成问题成功!")
            print(f"\n  问题: {question.user_question}")
            print(f"  类型: {question.question_type}")
            print(f"  语言: {question.language}")
            print(f"  需要引用的 PMID: {question.required_pmids}")
            return question
        else:
            print("✗ 生成失败")
            return None
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_rubric_generator(evidence=None, question=None):
    """测试 Rubric 生成器"""
    print("\n" + "=" * 60)
    print("测试 4: Rubric 生成器")
    print("=" * 60)
    
    from rubric_generator import generate_training_sample
    from question_generator import QuestionSample
    from pubmed_client import PubMedMCPClient, PaperEvidence, EvidenceSnapshot
    from datetime import datetime
    
    # 如果没有提供，创建模拟数据
    if evidence is None:
        mock_papers = [
            PaperEvidence(
                pmid="12345678",
                title="Test Paper 1",
                abstract="This is a test abstract about cancer treatment.",
                year="2023",
                venue="Nature",
                url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                authors=["Smith, J."]
            ),
            PaperEvidence(
                pmid="87654321",
                title="Test Paper 2",
                abstract="This is another test abstract about immunotherapy.",
                year="2022",
                venue="Science",
                url="https://pubmed.ncbi.nlm.nih.gov/87654321/",
                authors=["Johnson, M."]
            )
        ]
        evidence = EvidenceSnapshot(
            query="cancer immunotherapy",
            limit=5,
            offset=0,
            papers=mock_papers,
            total=100,
            snapshot_time=datetime.now().isoformat()
        )
    
    if question is None:
        question = QuestionSample(
            question_id="test_001",
            user_question="免疫检查点抑制剂在癌症治疗中的最新进展是什么？请引用相关研究。",
            query_used=evidence.query,
            required_pmids=[p.pmid for p in evidence.papers[:2]],
            question_type="汇总",
            language="zh"
        )
    
    try:
        sample = generate_training_sample(
            question=question,
            evidence=evidence,
            is_pagination_task=False,
            num_pages=1,
            use_cache=True
        )
        
        print(f"✓ 生成训练样本成功!")
        print(f"\n  样本 ID: {sample.sample_id}")
        print(f"  问题: {sample.user_question[:50]}...")
        print(f"  预期工具调用: {len(sample.expected_tools)} 个")
        print(f"  证据 PMID: {sample.evidence_pmids}")
        print(f"  评分项: {len(sample.answer_rubric.rubric_items)} 个")
        print(f"  稳定性策略: {sample.answer_rubric.stability_strategy.strategy_type}")
        
        # 显示评分项
        print("\n  评分项:")
        for item in sample.answer_rubric.rubric_items:
            print(f"    - [{item.category}] {item.title} (权重: {item.weight})")
        
        return sample
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_full_pipeline():
    """测试完整流程（小规模）"""
    print("\n" + "=" * 60)
    print("测试 5: 完整流程（小规模）")
    print("=" * 60)
    
    from generate_dataset import PubMedDatasetGenerator
    
    try:
        generator = PubMedDatasetGenerator(
            num_clusters=2,
            queries_per_cluster=2,
            samples_per_query=1,
            pagination_ratio=0.0  # 暂时禁用分页
        )
        
        samples = await generator.generate_dataset()
        
        if samples:
            print(f"\n✓ 完整流程测试成功!")
            print(f"  生成了 {len(samples)} 个训练样本")
            
            # 保存到测试目录
            test_output_dir = os.path.join(
                os.path.dirname(__file__), 
                "../../pubmed_training_data/test"
            )
            generator.save_dataset(test_output_dir)
            print(f"  保存到: {test_output_dir}")
        else:
            print("✗ 未生成任何样本")
        
        return samples
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("PubMed 数据生成器测试")
    print("=" * 60)
    print("\n注意: 请确保 MCP 服务器正在运行:")
    print("  cd agent && uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp")
    print("\n还需要设置 OPENROUTER_API_KEY 环境变量")
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, choices=[1, 2, 3, 4, 5], 
                        help="运行特定测试 (1-5)")
    parser.add_argument("--all", action="store_true", help="运行所有测试")
    args = parser.parse_args()
    
    if args.all or args.test is None:
        # 运行所有测试
        evidence = await test_pubmed_client()
        await test_topic_generator()
        question = await test_question_generator(evidence)
        await test_rubric_generator(evidence, question)
        await test_full_pipeline()
    else:
        # 运行特定测试
        if args.test == 1:
            await test_pubmed_client()
        elif args.test == 2:
            await test_topic_generator()
        elif args.test == 3:
            await test_question_generator()
        elif args.test == 4:
            await test_rubric_generator()
        elif args.test == 5:
            await test_full_pipeline()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

