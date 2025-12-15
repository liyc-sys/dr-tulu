#!/usr/bin/env python3
"""
离线测试脚本：验证数据结构和 LLM 调用（不需要 MCP 服务器）
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 确保能找到 config 模块（支持绝对路径运行）
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 设置测试用的 API Key（从已有配置中获取）
if not os.environ.get("OPENROUTER_API_KEY"):
    os.environ["OPENROUTER_API_KEY"] = "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"


async def test_data_structures():
    """测试数据结构（两部分 rubrics 结构）"""
    print("\n" + "=" * 60)
    print("测试 1: 数据结构（两部分 rubrics）")
    print("=" * 60)
    
    from pubmed_client import PaperEvidence, EvidenceSnapshot
    from question_generator import QuestionSample
    from rubric_generator import (
        ToolCall, EvidenceRequirement, RubricItem, 
        StabilityStrategy, AnswerRubric, TrainingSample,
        generate_training_sample, generate_training_sample_sync
    )
    
    # 创建模拟数据
    papers = [
        PaperEvidence(
            pmid="39355906",
            title="LRP1 Repression by SNAIL Results in ECM Remodeling in Genetic Risk for Vascular Diseases",
            abstract="This study investigates the role of LRP1 in vascular disease pathogenesis. We found that SNAIL-mediated LRP1 repression leads to significant changes in extracellular matrix composition. These findings provide new insights into genetic risk factors for cardiovascular diseases.",
            year="2024",
            venue="Nature Communications",
            url="https://pubmed.ncbi.nlm.nih.gov/39355906/",
            authors=["Wang, X.", "Li, Y.", "Chen, Z."]
        ),
        PaperEvidence(
            pmid="38123456",
            title="BRCA1 mutations and PARP inhibitor response in breast cancer",
            abstract="We conducted a comprehensive analysis of BRCA1 mutations and their impact on PARP inhibitor sensitivity. Patients with pathogenic BRCA1 variants showed significantly improved progression-free survival when treated with olaparib compared to standard chemotherapy. The median PFS was 12.3 months vs 5.8 months.",
            year="2023",
            venue="Journal of Clinical Oncology",
            url="https://pubmed.ncbi.nlm.nih.gov/38123456/",
            authors=["Smith, J.", "Johnson, M.", "Davis, K."]
        ),
        PaperEvidence(
            pmid="37654321",
            title="Novel immunotherapy combinations in metastatic melanoma",
            abstract="This phase III trial evaluated the combination of nivolumab and ipilimumab in advanced melanoma. The combination therapy resulted in improved overall survival compared to monotherapy, with a manageable safety profile. ORR was 58% with a median OS of 36.9 months.",
            year="2023",
            venue="New England Journal of Medicine",
            url="https://pubmed.ncbi.nlm.nih.gov/37654321/",
            authors=["Brown, A.", "Wilson, R."]
        )
    ]
    
    evidence = EvidenceSnapshot(
        query="cancer targeted therapy immunotherapy",
        limit=5,
        offset=0,
        papers=papers,
        total=150,
        snapshot_time=datetime.now().isoformat()
    )
    
    question = QuestionSample(
        question_id="test_offline_001",
        user_question="比较 BRCA1 突变乳腺癌的 PARP 抑制剂治疗与免疫治疗的最新研究进展，需要引用具体论文并提供摘要证据。",
        query_used=evidence.query,
        required_pmids=["38123456", "37654321"],
        question_type="比较",
        language="zh"
    )
    
    print(f"✓ 创建了模拟证据库: {len(papers)} 篇论文")
    print(f"✓ 创建了模拟问题: {question.question_type} 类型")
    
    # 使用 LLM 生成完整训练样本（异步版本）
    print("\n正在使用 LLM 生成内容 rubrics...")
    sample = await generate_training_sample(
        question=question,
        evidence=evidence,
        is_pagination_task=False,
        num_pages=1,
        use_cache=True,
        use_llm_for_content_rubrics=True
    )
    
    print(f"\n✓ 生成了完整训练样本:")
    print(f"  - 样本 ID: {sample.sample_id}")
    print(f"  - 预期工具调用: {len(sample.expected_tools)} 个")
    print(f"  - 证据 PMID: {sample.evidence_pmids}")
    
    # 验证两部分 rubrics
    print(f"\n  工具调用 rubrics ({len(sample.answer_rubric.tool_rubrics)} 条，固定):")
    for item in sample.answer_rubric.tool_rubrics:
        print(f"    [{item.category}] {item.title} (权重: {item.weight})")
    
    print(f"\n  内容相关 rubrics ({len(sample.answer_rubric.content_rubrics)} 条，动态生成):")
    for item in sample.answer_rubric.content_rubrics:
        print(f"    [{item.category}] {item.title}")
        print(f"      -> {item.description[:60]}...")
    
    # 输出完整 JSON
    print("\n完整样本 JSON:")
    print(json.dumps(sample.to_dict(), indent=2, ensure_ascii=False)[:3000] + "...")
    
    return sample


async def test_llm_call():
    """测试 LLM API 调用"""
    print("\n" + "=" * 60)
    print("测试 2: LLM API 调用 (OpenRouter)")
    print("=" * 60)
    
    from topic_generator import call_llm, extract_json
    
    test_prompt = """请生成 2 个医学研究主题，以 JSON 格式返回：
```json
{
  "topics": [
    {"name": "主题名称", "description": "简短描述"}
  ]
}
```
只输出 JSON，不要其他内容。
"""
    
    try:
        print("正在调用 OpenRouter API...")
        response = await call_llm(test_prompt, temperature=0.7)
        print(f"✓ API 调用成功!")
        print(f"\n响应内容:\n{response[:500]}...")
        
        # 尝试解析 JSON
        try:
            result = extract_json(response)
            print(f"\n✓ JSON 解析成功: {len(result.get('topics', []))} 个主题")
        except Exception as e:
            print(f"\n⚠ JSON 解析失败: {e}")
        
        return response
    except Exception as e:
        print(f"✗ API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_topic_generation():
    """测试主题生成"""
    print("\n" + "=" * 60)
    print("测试 3: 主题簇生成")
    print("=" * 60)
    
    from topic_generator import generate_topic_clusters
    
    try:
        print("正在生成 2 个主题簇...")
        clusters = await generate_topic_clusters(2)
        
        if clusters:
            print(f"✓ 生成成功! {len(clusters)} 个主题簇:")
            for c in clusters:
                print(f"\n  - {c.get('name', 'N/A')}")
                print(f"    类别: {c.get('category', 'N/A')}")
                print(f"    描述: {c.get('description', 'N/A')[:80]}...")
        else:
            print("⚠ 未生成主题簇")
        
        return clusters
    except Exception as e:
        print(f"✗ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """运行离线测试"""
    print("=" * 60)
    print("PubMed 数据生成器 - 离线测试")
    print("=" * 60)
    print("此测试不需要 MCP 服务器，仅验证数据结构和 LLM API")
    print("Rubrics 结构：工具调用 rubrics (4条固定) + 内容 rubrics (4-8条动态)")
    
    # 测试 1: 数据结构（两部分 rubrics）
    await test_data_structures()
    
    # 测试 2: LLM API 调用
    await test_llm_call()
    
    # 测试 3: 主题生成
    await test_topic_generation()
    
    print("\n" + "=" * 60)
    print("离线测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

