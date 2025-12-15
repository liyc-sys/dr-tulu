"""
Step 3: 基于证据库反向生成问题
生成必须依赖 pubmed_search 才能高质量回答的问题
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pubmed_client import PaperEvidence, EvidenceSnapshot
from topic_generator import call_llm, extract_json


@dataclass
class QuestionSample:
    """生成的问题样本"""
    question_id: str
    user_question: str
    query_used: str
    required_pmids: List[str]
    question_type: str  # 比较/汇总/抽取/分类/统计
    language: str  # zh/en
    
    def to_dict(self) -> Dict:
        return asdict(self)


QUESTION_GENERATION_PROMPT = """你是一个医学研究助手。基于以下 PubMed 搜索结果，生成一个高质量的研究问题。

**搜索查询**: {query}

**检索到的论文**:
{papers_info}

**要求**:
1. 问题必须让"不调用 pubmed_search"难以高质量回答
2. 答案必须引用具体的 PMID（硬要求）
3. 答案必须从摘要中提取/归纳证据句
4. 问题不能仅靠常识回答
5. 问题类型可以是: 比较研究结果、汇总多篇证据、抽取特定信息、分类分析、统计趋势
6. 语言: {language}

**问题类型选择指南**:
- **比较**: 比较不同研究的方法/结果/结论
- **汇总**: 综合多项研究的发现
- **抽取**: 从论文中提取特定数据/方法/结论
- **分类**: 按某标准分类分析不同研究
- **统计**: 基于多篇论文进行趋势/数量分析

请生成一个问题，并指定期望引用的 PMID 列表（从上述论文中选择 2-5 篇最相关的）。

输出 JSON 格式:
```json
{{
  "user_question": "生成的问题（{language}）",
  "question_type": "比较/汇总/抽取/分类/统计",
  "required_pmids": ["PMID1", "PMID2", ...],
  "reasoning": "为什么这个问题必须调用 PubMed 搜索才能回答好"
}}
```

只输出 JSON，不要其他内容。
"""


def format_papers_for_prompt(papers: List[PaperEvidence]) -> str:
    """格式化论文信息用于 prompt"""
    parts = []
    for i, paper in enumerate(papers, 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."
        
        abstract_preview = paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract
        
        part = f"""
**论文 {i}**:
- PMID: {paper.pmid}
- 标题: {paper.title}
- 作者: {authors_str}
- 年份: {paper.year}
- 期刊: {paper.venue}
- 摘要: {abstract_preview}
"""
        parts.append(part)
    
    return "\n".join(parts)


async def generate_question_from_evidence(
    evidence: EvidenceSnapshot,
    language: str = "zh",
    question_id: str = None
) -> Optional[QuestionSample]:
    """从证据快照生成问题"""
    
    if not evidence.papers:
        return None
    
    papers_info = format_papers_for_prompt(evidence.papers)
    
    prompt = QUESTION_GENERATION_PROMPT.format(
        query=evidence.query,
        papers_info=papers_info,
        language="中文" if language == "zh" else "English"
    )
    
    try:
        response = await call_llm(prompt, temperature=0.7)
        result = extract_json(response)
        
        return QuestionSample(
            question_id=question_id or f"q_{hash(evidence.query)}",
            user_question=result["user_question"],
            query_used=evidence.query,
            required_pmids=result["required_pmids"],
            question_type=result["question_type"],
            language=language
        )
    except Exception as e:
        print(f"生成问题失败: {e}")
        return None


# 分页任务专用 prompt
PAGINATION_QUESTION_PROMPT = """你是一个医学研究助手。基于以下 PubMed 搜索结果（来自多页检索），生成一个需要分页查询的研究问题。

**搜索查询**: {query}

**第一页结果 (offset=0)**:
{page1_papers}

**第二页结果 (offset={page2_offset})**:
{page2_papers}

**要求**:
1. 问题必须涉及较多论文（超过单页 5 篇），需要分页检索
2. 答案必须引用来自不同页的 PMID
3. 问题类型通常是: 系统性汇总、全面比较、趋势分析、文献综述
4. 语言: {language}

输出 JSON 格式:
```json
{{
  "user_question": "生成的问题（{language}）",
  "question_type": "汇总/比较/统计",
  "required_pmids": ["PMID1", "PMID2", ...],
  "pagination_hint": "该问题需要检索多页才能充分回答",
  "expected_pages": 2
}}
```

只输出 JSON，不要其他内容。
"""


async def generate_pagination_question(
    evidence_pages: List[EvidenceSnapshot],
    language: str = "zh",
    question_id: str = None
) -> Optional[QuestionSample]:
    """生成需要分页查询的问题"""
    
    if len(evidence_pages) < 2:
        return None
    
    page1 = evidence_pages[0]
    page2 = evidence_pages[1]
    
    if not page1.papers or not page2.papers:
        return None
    
    prompt = PAGINATION_QUESTION_PROMPT.format(
        query=page1.query,
        page1_papers=format_papers_for_prompt(page1.papers),
        page2_offset=page2.offset,
        page2_papers=format_papers_for_prompt(page2.papers),
        language="中文" if language == "zh" else "English"
    )
    
    try:
        response = await call_llm(prompt, temperature=0.7)
        result = extract_json(response)
        
        return QuestionSample(
            question_id=question_id or f"q_pag_{hash(page1.query)}",
            user_question=result["user_question"],
            query_used=page1.query,
            required_pmids=result["required_pmids"],
            question_type=result["question_type"],
            language=language
        )
    except Exception as e:
        print(f"生成分页问题失败: {e}")
        return None


if __name__ == "__main__":
    import asyncio
    from pubmed_client import PubMedMCPClient
    
    async def test():
        print("测试问题生成...")
        
        # 先获取证据
        client = PubMedMCPClient()
        evidence = await client.search("BRCA1 breast cancer therapy", limit=5)
        
        if evidence.papers:
            print(f"\n检索到 {len(evidence.papers)} 篇论文")
            
            # 生成问题
            question = await generate_question_from_evidence(evidence, language="zh")
            
            if question:
                print(f"\n生成的问题:")
                print(f"  问题: {question.user_question}")
                print(f"  类型: {question.question_type}")
                print(f"  需要引用的 PMID: {question.required_pmids}")
    
    asyncio.run(test())

