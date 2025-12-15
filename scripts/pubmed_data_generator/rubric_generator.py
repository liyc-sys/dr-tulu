"""
Step 4 & 5: 工具调用标注与评分 Rubrics 生成
生成 expected_tools, evidence_pmids, answer_rubric

Rubrics 分为两部分：
1. 固定的工具调用 rubrics（4 条）- 所有数据一样
2. 内容相关的 rubrics（4-8 条）- 根据 PubMed 返回结果动态生成
"""
import json
import sys
from pathlib import Path

# 确保能找到 config 模块（支持绝对路径运行）
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from pubmed_client import PaperEvidence, EvidenceSnapshot
from question_generator import QuestionSample


@dataclass
class ToolCall:
    """预期的工具调用"""
    tool_name: str
    parameters: Dict[str, Any]
    purpose: str  # 调用目的
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EvidenceRequirement:
    """每篇论文的证据要求"""
    pmid: str
    title: str
    year: str
    venue: str
    abstract_evidence_sentence: str  # 需要从摘要中引用的证据句
    url: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RubricItem:
    """评分项"""
    category: str  # tool_use / content
    title: str
    description: str
    weight: int
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StabilityStrategy:
    """稳定性策略"""
    strategy_type: str  # cache_snapshot / query_stabilization / semantic_scoring
    description: str
    implementation: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AnswerRubric:
    """完整的评分 Rubric，分为两部分"""
    tool_rubrics: List[RubricItem]  # 固定的工具调用 rubrics（4条）
    content_rubrics: List[RubricItem]  # 内容相关的 rubrics（4-8条）
    stability_strategy: StabilityStrategy
    
    def to_dict(self) -> Dict:
        return {
            "tool_rubrics": [r.to_dict() for r in self.tool_rubrics],
            "content_rubrics": [r.to_dict() for r in self.content_rubrics],
            "stability_strategy": self.stability_strategy.to_dict()
        }
    
    @property
    def all_rubrics(self) -> List[RubricItem]:
        """获取所有 rubrics"""
        return self.tool_rubrics + self.content_rubrics


@dataclass
class TrainingSample:
    """完整的训练样本"""
    sample_id: str
    user_question: str
    expected_tools: List[ToolCall]
    evidence_pmids: List[str]
    evidence_requirements: List[EvidenceRequirement]
    answer_rubric: AnswerRubric
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "sample_id": self.sample_id,
            "user_question": self.user_question,
            "expected_tools": [t.to_dict() for t in self.expected_tools],
            "evidence_pmids": self.evidence_pmids,
            "evidence_requirements": [e.to_dict() for e in self.evidence_requirements],
            "answer_rubric": self.answer_rubric.to_dict(),
            "metadata": self.metadata
        }


def generate_tool_calls(
    query: str,
    is_pagination_task: bool = False,
    num_pages: int = 1
) -> List[ToolCall]:
    """生成预期的工具调用计划"""
    calls = []
    
    # 第一次调用
    calls.append(ToolCall(
        tool_name="pubmed_search",
        parameters={
            "keywords": query,
            "limit": 5,
            "offset": 0
        },
        purpose="检索相关医学文献"
    ))
    
    # 分页任务的额外调用
    if is_pagination_task:
        for page in range(1, num_pages):
            calls.append(ToolCall(
                tool_name="pubmed_search",
                parameters={
                    "keywords": query,
                    "limit": 5,
                    "offset": page * 5
                },
                purpose=f"获取第 {page + 1} 页结果"
            ))
    
    return calls


def extract_evidence_sentence(abstract: str, max_length: int = 200) -> str:
    """从摘要中提取证据句（取前几句或关键句）"""
    if not abstract:
        return ""
    
    # 简单策略：取摘要前200字符作为证据句参考
    # 实际使用时可以更智能地提取
    sentences = abstract.split('. ')
    evidence = []
    current_length = 0
    
    for sentence in sentences:
        if current_length + len(sentence) <= max_length:
            evidence.append(sentence)
            current_length += len(sentence) + 2
        else:
            break
    
    return '. '.join(evidence) + ('.' if evidence else '')


def generate_evidence_requirements(
    papers: List[PaperEvidence],
    required_pmids: List[str]
) -> List[EvidenceRequirement]:
    """生成证据要求列表"""
    requirements = []
    
    pmid_to_paper = {p.pmid: p for p in papers}
    
    for pmid in required_pmids:
        if pmid in pmid_to_paper:
            paper = pmid_to_paper[pmid]
            requirements.append(EvidenceRequirement(
                pmid=pmid,
                title=paper.title,
                year=paper.year or "Unknown",
                venue=paper.venue or "Unknown",
                abstract_evidence_sentence=extract_evidence_sentence(paper.abstract),
                url=paper.url
            ))
    
    return requirements


def generate_fixed_tool_rubrics(
    num_required_papers: int,
    is_pagination_task: bool = False
) -> List[RubricItem]:
    """
    生成固定的工具调用 rubrics（4条，所有数据一样）
    """
    items = []
    
    # 1. 正确调用 pubmed_search
    items.append(RubricItem(
        category="tool_use",
        title="正确调用 pubmed_search",
        description="模型必须调用 pubmed_search 工具进行文献检索，参数格式正确",
        weight=3
    ))
    
    # 2. 引用正确的 PMID
    items.append(RubricItem(
        category="tool_use",
        title="引用正确的 PMID",
        description=f"输出必须包含正确的 PMID（至少 {min(2, num_required_papers)} 个），与工具返回结果对齐",
        weight=3
    ))
    
    # 3. 提供年份和期刊信息
    items.append(RubricItem(
        category="tool_use",
        title="提供年份和期刊信息",
        description="每篇被引用文献必须给出发表年份(year)和期刊名称(venue)",
        weight=2
    ))
    
    # 4. 摘要证据句对齐
    items.append(RubricItem(
        category="tool_use",
        title="摘要证据句对齐",
        description="每篇被引用文献必须给出至少 1 句摘要证据句，可从 abstract 中摘写或紧贴改写",
        weight=3
    ))
    
    return items


# LLM prompt for generating content rubrics
CONTENT_RUBRICS_PROMPT = """你是一个医学研究评估专家。基于以下问题和检索到的论文，生成 4-8 条内容评分项（content rubrics）。

**用户问题**: {question}

**检索到的论文摘要**:
{papers_info}

**要求**:
1. 每条 rubric 描述模型回答时必须提到的一个具体知识点
2. 这些知识点必须能从上述论文摘要中找到依据
3. rubric 应该具体、可验证，不要太泛泛而谈
4. 生成 4-8 条，涵盖论文中的关键发现、方法、结论等
5. 每条 rubric 的权重为 3

**输出 JSON 格式**:
```json
{{
  "content_rubrics": [
    {{
      "title": "简短标题（5-15字）",
      "description": "详细描述模型应该提到的具体内容点"
    }}
  ]
}}
```

只输出 JSON，不要其他内容。
"""


async def generate_content_rubrics_with_llm(
    question: str,
    papers: List[PaperEvidence]
) -> List[RubricItem]:
    """
    使用 LLM 根据论文内容生成内容相关的 rubrics（4-8条）
    """
    from topic_generator import call_llm, extract_json
    
    # 格式化论文信息
    papers_info = []
    for i, paper in enumerate(papers, 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."
        
        abstract_preview = paper.abstract[:600] if paper.abstract else "无摘要"
        
        papers_info.append(f"""
**论文 {i}** (PMID: {paper.pmid})
- 标题: {paper.title}
- 作者: {authors_str}
- 年份: {paper.year} | 期刊: {paper.venue}
- 摘要: {abstract_preview}
""")
    
    prompt = CONTENT_RUBRICS_PROMPT.format(
        question=question,
        papers_info="\n".join(papers_info)
    )
    
    try:
        response = await call_llm(prompt, temperature=0.5)
        result = extract_json(response)
        
        rubrics = []
        for item in result.get("content_rubrics", []):
            rubrics.append(RubricItem(
                category="content",
                title=item["title"],
                description=item["description"],
                weight=3
            ))
        
        # 确保至少有 4 条，最多 8 条
        if len(rubrics) < 4:
            # 如果太少，添加一些通用的
            default_rubrics = [
                RubricItem(category="content", title="研究方法描述", description="提到论文中使用的主要研究方法", weight=3),
                RubricItem(category="content", title="主要发现总结", description="总结论文的主要研究发现", weight=3),
                RubricItem(category="content", title="临床意义", description="讨论研究结果的临床应用价值", weight=3),
                RubricItem(category="content", title="研究局限性", description="提及研究的局限性或未来方向", weight=3),
            ]
            rubrics.extend(default_rubrics[:4 - len(rubrics)])
        
        return rubrics[:8]  # 最多 8 条
        
    except Exception as e:
        print(f"生成内容 rubrics 失败: {e}")
        # 返回默认的内容 rubrics
        return [
            RubricItem(category="content", title="研究背景", description="提到研究的背景和动机", weight=3),
            RubricItem(category="content", title="研究方法", description="描述论文中使用的主要研究方法", weight=3),
            RubricItem(category="content", title="主要发现", description="总结论文的主要研究发现和结论", weight=3),
            RubricItem(category="content", title="临床意义", description="讨论研究结果的临床应用价值或科学意义", weight=3),
        ]


def generate_content_rubrics_sync(
    question: str,
    papers: List[PaperEvidence]
) -> List[RubricItem]:
    """
    同步版本：根据论文内容生成内容相关的 rubrics（不调用 LLM）
    用于测试或回退场景
    """
    rubrics = []
    
    # 根据论文数量和内容生成具体的 rubrics
    for i, paper in enumerate(papers[:4]):  # 最多基于前 4 篇论文
        if paper.abstract:
            # 从摘要中提取关键信息作为 rubric
            abstract_preview = paper.abstract[:100]
            rubrics.append(RubricItem(
                category="content",
                title=f"论文{paper.pmid}的关键发现",
                description=f"提到 {paper.title[:50]}... 中的主要研究发现",
                weight=3
            ))
    
    # 添加通用的内容 rubrics
    if len(rubrics) < 4:
        general_rubrics = [
            RubricItem(category="content", title="研究方法对比", description="对比不同论文使用的研究方法", weight=3),
            RubricItem(category="content", title="数据/样本描述", description="提到研究中的数据来源或样本特征", weight=3),
            RubricItem(category="content", title="结果解读", description="正确解读论文中的主要结果和数据", weight=3),
            RubricItem(category="content", title="综合结论", description="基于多篇论文给出综合性的结论", weight=3),
        ]
        rubrics.extend(general_rubrics[:4 - len(rubrics)])
    
    return rubrics[:8]


def generate_stability_strategy(
    query: str,
    use_cache: bool = True
) -> StabilityStrategy:
    """生成稳定性策略"""
    
    # 检查查询是否包含强限定
    has_quotes = '"' in query
    has_year = any(str(year) in query for year in range(2015, 2030))
    has_boolean = any(op in query.upper() for op in ['AND', 'OR', 'NOT'])
    
    is_stable_query = has_quotes or (has_year and has_boolean)
    
    if use_cache:
        return StabilityStrategy(
            strategy_type="cache_snapshot",
            description="该样本依赖对 pubmed_search 返回做快照缓存",
            implementation="评测时使用缓存的证据库快照，避免实时 API 调用带来的漂移"
        )
    elif is_stable_query:
        return StabilityStrategy(
            strategy_type="query_stabilization",
            description="查询模板包含强限定（短语引号、年份窗口、布尔组合）以降低漂移",
            implementation="查询已优化为稳定形式，返回结果相对固定"
        )
    else:
        return StabilityStrategy(
            strategy_type="semantic_scoring",
            description="评测不强制命中同一篇绝对固定集合",
            implementation="要求输出 PMID 与摘要证据句可对齐，允许返回相似但不完全相同的论文集"
        )


async def generate_training_sample(
    question: QuestionSample,
    evidence: EvidenceSnapshot,
    is_pagination_task: bool = False,
    num_pages: int = 1,
    use_cache: bool = True,
    use_llm_for_content_rubrics: bool = True
) -> TrainingSample:
    """
    生成完整的训练样本
    
    Args:
        question: 问题样本
        evidence: 证据快照
        is_pagination_task: 是否分页任务
        num_pages: 页数
        use_cache: 是否使用缓存
        use_llm_for_content_rubrics: 是否使用 LLM 生成内容 rubrics
    """
    
    # 生成工具调用计划
    expected_tools = generate_tool_calls(
        query=evidence.query,
        is_pagination_task=is_pagination_task,
        num_pages=num_pages
    )
    
    # 生成证据要求
    evidence_requirements = generate_evidence_requirements(
        papers=evidence.papers,
        required_pmids=question.required_pmids
    )
    
    # 生成固定的工具调用 rubrics（4条）
    tool_rubrics = generate_fixed_tool_rubrics(
        num_required_papers=len(question.required_pmids),
        is_pagination_task=is_pagination_task
    )
    
    # 生成内容相关的 rubrics（4-8条）
    if use_llm_for_content_rubrics:
        # 筛选需要引用的论文
        required_papers = [p for p in evidence.papers if p.pmid in question.required_pmids]
        content_rubrics = await generate_content_rubrics_with_llm(
            question=question.user_question,
            papers=required_papers if required_papers else evidence.papers
        )
    else:
        content_rubrics = generate_content_rubrics_sync(
            question=question.user_question,
            papers=evidence.papers
        )
    
    # 生成稳定性策略
    stability_strategy = generate_stability_strategy(
        query=evidence.query,
        use_cache=use_cache
    )
    
    # 组装 rubric（两部分）
    answer_rubric = AnswerRubric(
        tool_rubrics=tool_rubrics,
        content_rubrics=content_rubrics,
        stability_strategy=stability_strategy
    )
    
    return TrainingSample(
        sample_id=question.question_id,
        user_question=question.user_question,
        expected_tools=expected_tools,
        evidence_pmids=question.required_pmids,
        evidence_requirements=evidence_requirements,
        answer_rubric=answer_rubric,
        metadata={
            "query_used": evidence.query,
            "question_type": question.question_type,
            "language": question.language,
            "is_pagination_task": is_pagination_task,
            "evidence_snapshot_time": evidence.snapshot_time,
            "total_papers_available": evidence.total,
            "num_tool_rubrics": len(tool_rubrics),
            "num_content_rubrics": len(content_rubrics)
        }
    )


def generate_training_sample_sync(
    question: QuestionSample,
    evidence: EvidenceSnapshot,
    is_pagination_task: bool = False,
    num_pages: int = 1,
    use_cache: bool = True
) -> TrainingSample:
    """
    同步版本：生成完整的训练样本（不调用 LLM）
    用于测试或回退场景
    """
    # 生成工具调用计划
    expected_tools = generate_tool_calls(
        query=evidence.query,
        is_pagination_task=is_pagination_task,
        num_pages=num_pages
    )
    
    # 生成证据要求
    evidence_requirements = generate_evidence_requirements(
        papers=evidence.papers,
        required_pmids=question.required_pmids
    )
    
    # 生成固定的工具调用 rubrics（4条）
    tool_rubrics = generate_fixed_tool_rubrics(
        num_required_papers=len(question.required_pmids),
        is_pagination_task=is_pagination_task
    )
    
    # 生成内容相关的 rubrics（同步版本）
    content_rubrics = generate_content_rubrics_sync(
        question=question.user_question,
        papers=evidence.papers
    )
    
    # 生成稳定性策略
    stability_strategy = generate_stability_strategy(
        query=evidence.query,
        use_cache=use_cache
    )
    
    # 组装 rubric（两部分）
    answer_rubric = AnswerRubric(
        tool_rubrics=tool_rubrics,
        content_rubrics=content_rubrics,
        stability_strategy=stability_strategy
    )
    
    return TrainingSample(
        sample_id=question.question_id,
        user_question=question.user_question,
        expected_tools=expected_tools,
        evidence_pmids=question.required_pmids,
        evidence_requirements=evidence_requirements,
        answer_rubric=answer_rubric,
        metadata={
            "query_used": evidence.query,
            "question_type": question.question_type,
            "language": question.language,
            "is_pagination_task": is_pagination_task,
            "evidence_snapshot_time": evidence.snapshot_time,
            "total_papers_available": evidence.total,
            "num_tool_rubrics": len(tool_rubrics),
            "num_content_rubrics": len(content_rubrics)
        }
    )


if __name__ == "__main__":
    import asyncio
    from pubmed_client import PaperEvidence, EvidenceSnapshot
    from datetime import datetime
    
    async def test():
        # 模拟数据
        mock_papers = [
            PaperEvidence(
                pmid="12345678",
                title="BRCA1 mutations in breast cancer treatment response to PARP inhibitors",
                abstract="This study investigates the role of BRCA1 mutations in treatment response. We found that patients with BRCA1 mutations showed improved response to PARP inhibitors with a median progression-free survival of 12.3 months compared to 5.8 months in the control group. The overall response rate was 67% in the BRCA1-mutated cohort.",
                year="2023",
                venue="Nature Medicine",
                url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                authors=["Smith, J.", "Johnson, M."]
            ),
            PaperEvidence(
                pmid="87654321",
                title="Novel therapies for BRCA-associated cancers: A comprehensive review",
                abstract="We review recent advances in targeted therapies for BRCA-associated breast cancer. PARP inhibitors including olaparib, niraparib, and talazoparib have shown significant efficacy in clinical trials. Combination therapies with immunotherapy are emerging as promising strategies.",
                year="2022",
                venue="Cancer Research",
                url="https://pubmed.ncbi.nlm.nih.gov/87654321/",
                authors=["Brown, A.", "Davis, K."]
            )
        ]
        
        mock_evidence = EvidenceSnapshot(
            query="BRCA1 breast cancer treatment",
            limit=5,
            offset=0,
            papers=mock_papers,
            total=100,
            snapshot_time=datetime.now().isoformat()
        )
        
        mock_question = QuestionSample(
            question_id="test_001",
            user_question="BRCA1 突变乳腺癌患者的靶向治疗选择有哪些？请引用相关研究并提供证据。",
            query_used="BRCA1 breast cancer treatment",
            required_pmids=["12345678", "87654321"],
            question_type="汇总",
            language="zh"
        )
        
        print("=" * 60)
        print("测试 Rubric 生成（两部分结构）")
        print("=" * 60)
        
        # 测试异步版本（使用 LLM）
        print("\n使用 LLM 生成内容 rubrics...")
        sample = await generate_training_sample(mock_question, mock_evidence, use_llm_for_content_rubrics=True)
        
        print(f"\n工具调用 rubrics ({len(sample.answer_rubric.tool_rubrics)} 条):")
        for r in sample.answer_rubric.tool_rubrics:
            print(f"  - [{r.category}] {r.title}")
        
        print(f"\n内容相关 rubrics ({len(sample.answer_rubric.content_rubrics)} 条):")
        for r in sample.answer_rubric.content_rubrics:
            print(f"  - [{r.category}] {r.title}: {r.description[:50]}...")
        
        print("\n完整样本 JSON:")
        print(json.dumps(sample.to_dict(), indent=2, ensure_ascii=False))
    
    asyncio.run(test())

