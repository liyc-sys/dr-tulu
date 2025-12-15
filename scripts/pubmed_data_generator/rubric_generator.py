"""
Step 4 & 5: 工具调用标注与评分 Rubrics 生成
生成 expected_tools, evidence_pmids, answer_rubric
"""
import json
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
    category: str  # tool_use / verifiability / task_completion
    title: str
    description: str
    weight: int
    pass_condition: str
    fail_condition: str
    
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
    """完整的评分 Rubric"""
    rubric_items: List[RubricItem]
    stability_strategy: StabilityStrategy
    
    def to_dict(self) -> Dict:
        return {
            "rubric_items": [r.to_dict() for r in self.rubric_items],
            "stability_strategy": self.stability_strategy.to_dict()
        }


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


def generate_rubric_items(
    question_type: str,
    num_required_papers: int,
    is_pagination_task: bool = False
) -> List[RubricItem]:
    """生成评分项列表"""
    items = []
    
    # 1. 工具使用分
    items.append(RubricItem(
        category="tool_use",
        title="正确调用 pubmed_search",
        description="模型必须调用 pubmed_search 工具进行文献检索",
        weight=3,
        pass_condition="调用了 pubmed_search 且参数格式正确",
        fail_condition="未调用 pubmed_search 或参数错误"
    ))
    
    if is_pagination_task:
        items.append(RubricItem(
            category="tool_use",
            title="正确使用分页",
            description="模型必须使用 offset 参数进行分页检索",
            weight=2,
            pass_condition="调用了多次 pubmed_search 并使用不同 offset",
            fail_condition="未进行分页检索或 offset 使用不正确"
        ))
    
    # 2. 可验证性分
    items.append(RubricItem(
        category="verifiability",
        title="引用正确的 PMID",
        description="输出必须包含正确的 PMID，与证据库对齐",
        weight=3,
        pass_condition=f"正确引用了至少 {min(2, num_required_papers)} 个 PMID",
        fail_condition="未引用 PMID 或 PMID 不在证据库中"
    ))
    
    items.append(RubricItem(
        category="verifiability",
        title="提供年份和期刊信息",
        description="每篇被引用文献必须给出 year 和 venue",
        weight=2,
        pass_condition="所有引用的论文都包含 year 和 venue 信息",
        fail_condition="缺少 year 或 venue 信息"
    ))
    
    items.append(RubricItem(
        category="verifiability",
        title="摘要证据句对齐",
        description="每篇被引用文献必须给出 1 句摘要证据句",
        weight=3,
        pass_condition="提供的证据句能在对应 abstract 中找到或紧贴 abstract 改写",
        fail_condition="证据句与 abstract 不匹配或完全缺失"
    ))
    
    # 3. 任务完成分
    task_descriptions = {
        "比较": "完成不同研究的对比分析",
        "汇总": "综合归纳多项研究的发现",
        "抽取": "准确抽取特定信息",
        "分类": "按标准分类分析不同研究",
        "统计": "完成趋势/数量分析"
    }
    
    items.append(RubricItem(
        category="task_completion",
        title=f"完成{question_type}任务",
        description=task_descriptions.get(question_type, "完成指定任务"),
        weight=3,
        pass_condition=f"成功{task_descriptions.get(question_type, '完成任务')}",
        fail_condition="未完成任务目标或分析不完整"
    ))
    
    return items


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


def generate_training_sample(
    question: QuestionSample,
    evidence: EvidenceSnapshot,
    is_pagination_task: bool = False,
    num_pages: int = 1,
    use_cache: bool = True
) -> TrainingSample:
    """生成完整的训练样本"""
    
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
    
    # 生成评分项
    rubric_items = generate_rubric_items(
        question_type=question.question_type,
        num_required_papers=len(question.required_pmids),
        is_pagination_task=is_pagination_task
    )
    
    # 生成稳定性策略
    stability_strategy = generate_stability_strategy(
        query=evidence.query,
        use_cache=use_cache
    )
    
    # 组装 rubric
    answer_rubric = AnswerRubric(
        rubric_items=rubric_items,
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
            "total_papers_available": evidence.total
        }
    )


if __name__ == "__main__":
    # 测试
    from pubmed_client import PaperEvidence, EvidenceSnapshot
    from datetime import datetime
    
    # 模拟数据
    mock_papers = [
        PaperEvidence(
            pmid="12345678",
            title="BRCA1 mutations in breast cancer treatment",
            abstract="This study investigates the role of BRCA1 mutations in treatment response. We found that patients with BRCA1 mutations showed improved response to PARP inhibitors.",
            year="2023",
            venue="Nature Medicine",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            authors=["Smith, J.", "Johnson, M."]
        ),
        PaperEvidence(
            pmid="87654321",
            title="Novel therapies for BRCA-associated cancers",
            abstract="We review recent advances in targeted therapies for BRCA-associated breast cancer. PARP inhibitors have shown significant efficacy.",
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
    
    sample = generate_training_sample(mock_question, mock_evidence)
    print(json.dumps(sample.to_dict(), indent=2, ensure_ascii=False))

