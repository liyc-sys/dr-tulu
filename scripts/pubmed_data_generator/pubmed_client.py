"""
Step 2: PubMed 搜索客户端
通过 MCP 服务器调用 pubmed_search 工具，采样证据库
"""
import asyncio
import json
import sys
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# 添加 agent 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agent"))

from config import MCP_HOST, MCP_PORT, MCP_TRANSPORT, DEFAULT_LIMIT, DEFAULT_OFFSET


@dataclass
class PaperEvidence:
    """论文证据记录"""
    pmid: str
    title: str
    abstract: str
    year: Optional[str]
    venue: Optional[str]
    url: str
    authors: List[str]
    citation_count: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EvidenceSnapshot:
    """证据库快照 - 用于稳定性缓存"""
    query: str
    limit: int
    offset: int
    papers: List[PaperEvidence]
    total: int
    snapshot_time: str
    
    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "limit": self.limit,
            "offset": self.offset,
            "papers": [p.to_dict() for p in self.papers],
            "total": self.total,
            "snapshot_time": self.snapshot_time
        }


class PubMedMCPClient:
    """通过 MCP 服务器调用 PubMed 搜索"""
    
    def __init__(self, host: str = MCP_HOST, port: str = MCP_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/mcp"
        self._client = None
        
    async def _get_client(self):
        """懒加载 MCP 客户端"""
        if self._client is None:
            from fastmcp import Client
            self._client = Client(self.base_url, timeout=60)
        return self._client
    
    async def search(
        self,
        query: str,
        limit: int = DEFAULT_LIMIT,
        offset: int = DEFAULT_OFFSET
    ) -> EvidenceSnapshot:
        """执行 PubMed 搜索并返回证据快照"""
        from datetime import datetime
        
        client = await self._get_client()
        
        async with client:
            result = await client.call_tool(
                "pubmed_search",
                {"query": query, "limit": limit, "offset": offset}
            )
            
            # 解析响应
            if hasattr(result, "content") and result.content:
                if hasattr(result.content[0], "text"):
                    raw_data = json.loads(result.content[0].text)
                else:
                    raw_data = result.content[0]
            else:
                raise ValueError("No content in MCP response")
        
        # 转换为 PaperEvidence 对象
        papers = []
        for item in raw_data.get("data", []):
            authors = []
            for author in item.get("authors", []):
                if isinstance(author, dict) and "name" in author:
                    authors.append(author["name"])
                elif isinstance(author, str):
                    authors.append(author)
            
            paper = PaperEvidence(
                pmid=str(item.get("paperId", "")),
                title=item.get("title", ""),
                abstract=item.get("abstract", ""),
                year=item.get("year"),
                venue=item.get("venue"),
                url=item.get("url", ""),
                authors=authors,
                citation_count=item.get("citationCount")
            )
            papers.append(paper)
        
        return EvidenceSnapshot(
            query=query,
            limit=limit,
            offset=offset,
            papers=papers,
            total=raw_data.get("total", len(papers)),
            snapshot_time=datetime.now().isoformat()
        )
    
    async def search_with_pagination(
        self,
        query: str,
        total_papers: int = 10,
        page_size: int = 5
    ) -> List[EvidenceSnapshot]:
        """分页搜索，返回多个快照"""
        snapshots = []
        offset = 0
        
        while offset < total_papers:
            limit = min(page_size, total_papers - offset)
            snapshot = await self.search(query, limit=limit, offset=offset)
            snapshots.append(snapshot)
            
            if len(snapshot.papers) < limit:
                break  # 没有更多结果
            
            offset += limit
        
        return snapshots


async def sample_evidence_for_query(
    query: str,
    limit: int = 5,
    offset: int = 0
) -> Optional[EvidenceSnapshot]:
    """为单个查询采样证据库"""
    client = PubMedMCPClient()
    try:
        snapshot = await client.search(query, limit=limit, offset=offset)
        return snapshot
    except Exception as e:
        print(f"搜索失败: {query} - {e}")
        return None


async def instantiate_query_template(
    template: str,
    variables: Dict[str, str] = None
) -> str:
    """实例化查询模板，替换变量占位符"""
    if variables is None:
        variables = {}
    
    query = template
    for var_name, var_value in variables.items():
        query = query.replace(f"{{{var_name}}}", var_value)
    
    # 移除未替换的变量占位符（使用默认或留空）
    import re
    query = re.sub(r'\{[^}]+\}', '', query)
    query = ' '.join(query.split())  # 清理多余空格
    
    return query


if __name__ == "__main__":
    async def test():
        print("测试 PubMed MCP 客户端...")
        client = PubMedMCPClient()
        
        test_query = "BRCA1 breast cancer treatment"
        print(f"\n查询: {test_query}")
        
        snapshot = await client.search(test_query, limit=5)
        print(f"\n找到 {len(snapshot.papers)} 篇论文:")
        
        for i, paper in enumerate(snapshot.papers, 1):
            print(f"\n{i}. PMID: {paper.pmid}")
            print(f"   标题: {paper.title[:80]}...")
            print(f"   年份: {paper.year}")
            print(f"   期刊: {paper.venue}")
            print(f"   摘要前200字: {paper.abstract[:200]}...")
        
        print(f"\n快照时间: {snapshot.snapshot_time}")
    
    asyncio.run(test())

