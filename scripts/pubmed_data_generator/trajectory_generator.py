"""
轨迹生成器：调用 GPT-5 连接 MCP 工具，生成 interleaved 工具调用轨迹
格式：<think>思考</think> -> <call_tool>调用</call_tool> -> <tool_output>结果</tool_output> -> ... -> <answer>答案</answer>
"""
import asyncio
import json
import sys
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
import httpx

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MCP_HOST, MCP_PORT


# dr-tulu 风格的 system prompt
SYSTEM_PROMPT = """You are a research assistant who answers questions through iterative reasoning and research.

## Process
- Use <think></think> tags to show your reasoning at any point.
- Use <call_tool name="...">query</call_tool> when you need information (see tools below).
- You can alternate between thinking and searching multiple times.
- Only provide <answer></answer> tags when you have enough information for a complete response.
- Support every non-trivial claim with retrieved evidence. Wrap the exact claim span in <cite id="ID1,ID2">...</cite>, where id are snippet IDs from searched results (comma-separated if multiple). Use only returned snippets; never invent IDs.

## Calling Tools (<call_tool name="...">query</call_tool>)
- You can use the following tools:

1. pubmed_search 
- Purpose: search medical and scientific papers from PubMed database.
- Input via: <call_tool name="pubmed_search">your query</call_tool>
- Output: paper snippets with PMID, title, abstract, year, venue, authors.
- Optional parameters:
  - limit: number of results (default: 10)
  - offset: pagination offset (default: 0)
- Example: <call_tool name="pubmed_search" limit="5">BRCA1 breast cancer PARP inhibitors</call_tool>

2. browse_webpage 
- Purpose: open a specific URL and extract readable page text.
- Input via: <call_tool name="browse_webpage">https://example.com/article</call_tool>
- Output: webpage content.

3. google_search 
- Purpose: general web search.
- Input via: <call_tool name="google_search">your query</call_tool>
- Output: web search snippets.

## Important Constraints (MUST FOLLOW)
- **CRITICAL: pubmed_search can be called AT MOST 3 times in total. Do NOT exceed this limit.**
- Plan your search strategy carefully before making any call.
- Use precise, comprehensive keyword combinations to maximize results from each search.
- Combine multiple concepts in a single query instead of making separate searches.
- If you have already called pubmed_search 3 times, you MUST stop searching and provide your answer.

## Tool Output
- After you issue a tool call, we will execute it and return results wrapped in <tool_output> tags.
- For pubmed_search, results appear as: <tool_output><snippet id="PMID">content</snippet>...</tool_output>

## Answer and Citation Format
- Once you collect all necessary information, generate the final answer with <answer></answer> tags.
- In your answer, wrap supported text in <cite id="PMID">...</cite> using the exact PMID from returned snippets.
- You MUST cite PMIDs in your answer and include year/venue information for each cited paper.

## WORKFLOW EXAMPLE

Question: What are the latest findings on BRCA1 mutations and PARP inhibitor treatment?

<think>I need to search for recent papers on BRCA1 mutations and PARP inhibitors to understand the current research landscape.</think>
<call_tool name="pubmed_search" limit="5">BRCA1 mutation PARP inhibitor breast cancer treatment 2023</call_tool>
<tool_output><snippet id="38123456">Title: PARP inhibitor efficacy in BRCA1-mutated breast cancer...Authors: Smith J, et al. | Year: 2023 | Journal: J Clin Oncol
Abstract: Our study demonstrates that PARP inhibitors show significant efficacy in BRCA1-mutated breast cancer patients...</snippet>
<snippet id="37654321">Title: Novel combination strategies with PARP inhibitors...</snippet></tool_output>

<think>I found relevant papers. Let me search for more specific information about response rates and resistance mechanisms.</think>
<call_tool name="pubmed_search" limit="5">BRCA1 PARP inhibitor resistance mechanisms</call_tool>
<tool_output><snippet id="39012345">Title: Mechanisms of PARP inhibitor resistance...
Abstract: Resistance to PARP inhibitors can develop through multiple mechanisms including BRCA1 reversion mutations...</snippet></tool_output>

<think>Now I have enough information to provide a comprehensive answer with proper citations.</think>
<answer>
Based on recent literature, PARP inhibitors have shown significant efficacy in treating BRCA1-mutated breast cancer. 

<cite id="38123456">PARP inhibitors demonstrate significant clinical benefit in patients with BRCA1 mutations, with response rates exceeding 60% in recent trials (Smith et al., 2023, J Clin Oncol).</cite>

However, resistance remains a challenge. <cite id="39012345">Multiple resistance mechanisms have been identified, including BRCA1 reversion mutations that restore homologous recombination repair.</cite>
</answer>

## REQUIREMENTS
- Think and search iteratively until you have sufficient information
- You MUST use pubmed_search at least once
- You MUST NOT call pubmed_search more than 3 times total
- Cite all claims using exact PMIDs from search results
- Include year and journal information when citing papers
- After 3 pubmed_search calls, immediately provide your final answer
"""


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    tool_name: str
    parameters: Dict[str, Any]
    query: str
    result: Any
    timestamp: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Trajectory:
    """完整的 interleaved 轨迹"""
    question: str
    interleaved_text: str  # 完整的 interleaved 文本 (think + call_tool + tool_output + answer)
    tool_calls: List[ToolCallRecord]  # 所有工具调用记录
    final_answer: str  # 最终答案
    total_tool_calls: int
    tools_used: List[str]
    pmids_cited: List[str]  # 引用的 PMIDs
    
    def to_dict(self) -> Dict:
        return {
            "question": self.question,
            "interleaved_text": self.interleaved_text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "final_answer": self.final_answer,
            "total_tool_calls": self.total_tool_calls,
            "tools_used": self.tools_used,
            "pmids_cited": self.pmids_cited
        }


class MCPToolExecutor:
    """MCP 工具执行器"""
    
    def __init__(self, host: str = MCP_HOST, port: str = MCP_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/mcp"
        self._client = None
        
    async def _get_client(self):
        if self._client is None:
            from fastmcp import Client
            self._client = Client(self.base_url, timeout=120)
        return self._client
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Tuple[Dict[str, Any], str]:
        """执行 MCP 工具调用，返回 (原始结果, 格式化的 tool_output)"""
        client = await self._get_client()
        
        # 映射工具名到 MCP 工具名
        mcp_tool_mapping = {
            "pubmed_search": "pubmed_search",
            "browse_webpage": "crawl4ai_fetch_webpage_content",
            "google_search": "serper_google_webpage_search"
        }
        
        mcp_tool_name = mcp_tool_mapping.get(tool_name, tool_name)
        
        # 构建 MCP 参数
        mcp_params = self._build_mcp_params(tool_name, parameters, query)
        
        try:
            async with client:
                result = await client.call_tool(mcp_tool_name, mcp_params)
                
                if hasattr(result, "content") and result.content:
                    if hasattr(result.content[0], "text"):
                        raw_result = json.loads(result.content[0].text)
                    else:
                        raw_result = {"data": str(result.content[0])}
                else:
                    raw_result = {"error": "No content in response"}
                    
                # 格式化为 tool_output
                formatted_output = self._format_tool_output(tool_name, raw_result)
                return raw_result, formatted_output
                
        except Exception as e:
            error_result = {"error": str(e)}
            return error_result, f"<tool_output>Error: {str(e)}</tool_output>"
    
    def _build_mcp_params(self, tool_name: str, parameters: Dict[str, Any], query: str) -> Dict[str, Any]:
        """构建 MCP 参数"""
        if tool_name == "pubmed_search":
            return {
                "query": query,
                "limit": parameters.get("limit", 10),
                "offset": parameters.get("offset", 0)
            }
        elif tool_name == "browse_webpage":
            return {"url": query}
        elif tool_name == "google_search":
            return {
                "query": query,
                "num_results": parameters.get("num_results", 10)
            }
        return {"query": query, **parameters}
    
    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        """将原始工具结果格式化为 <tool_output> 格式"""
        if "error" in raw_result:
            return f"<tool_output>Error: {raw_result['error']}</tool_output>"
        
        if tool_name == "pubmed_search":
            snippets = []
            data = raw_result.get("data", [])
            for paper in data[:10]:  # 最多10篇
                pmid = paper.get("paperId", "unknown")
                title = paper.get("title", "No title")
                abstract = paper.get("abstract", "No abstract")[:500]  # 截断摘要
                year = paper.get("year", "N/A")
                venue = paper.get("venue", "N/A")
                authors = paper.get("authors", [])
                author_str = ", ".join([a.get("name", "") for a in authors[:3]])
                if len(authors) > 3:
                    author_str += " et al."
                
                snippet = f"""<snippet id="{pmid}">Title: {title}
Authors: {author_str} | Year: {year} | Journal: {venue}
Abstract: {abstract}</snippet>"""
                snippets.append(snippet)
            
            total = raw_result.get("total", len(data))
            header = f"Found {total} results. Showing top {len(snippets)}:\n"
            return f"<tool_output>\n{header}" + "\n".join(snippets) + "\n</tool_output>"
        
        elif tool_name == "browse_webpage":
            content = str(raw_result)[:2000]
            return f"<tool_output><webpage>{content}</webpage></tool_output>"
        
        elif tool_name == "google_search":
            results = raw_result.get("organic", raw_result.get("data", []))
            snippets = []
            for i, r in enumerate(results[:5]):
                title = r.get("title", "")
                snippet_text = r.get("snippet", r.get("description", ""))
                link = r.get("link", r.get("url", ""))
                snippets.append(f'<snippet id="G{i+1}">Title: {title}\n{snippet_text}\nURL: {link}</snippet>')
            return f"<tool_output>\n" + "\n".join(snippets) + "\n</tool_output>"
        
        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False)[:2000]}</tool_output>"


class GPT5TrajectoryGenerator:
    """使用 GPT-5 生成 interleaved 工具调用轨迹"""
    
    def __init__(
        self,
        model: str = "openai/gpt-4o",
        max_turns: int = 10,
        api_key: str = None
    ):
        self.model = model
        self.max_turns = max_turns
        self.api_key = api_key or OPENROUTER_API_KEY
        self.tool_executor = MCPToolExecutor()
        
    async def generate_trajectory(self, question: str) -> Trajectory:
        """为给定问题生成完整的 interleaved 轨迹"""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
        
        tool_calls = []
        tools_used = set()
        total_tool_calls = 0
        interleaved_parts = []  # 收集所有 interleaved 部分
        final_answer = ""
        
        for turn in range(self.max_turns):
            # 调用 LLM
            response = await self._call_llm(messages)
            
            if not response:
                print(f"  ⚠ LLM 无响应，停止生成")
                break
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                print(f"  ⚠ 响应内容为空，停止生成")
                break
            
            # 检查是否包含 <answer> 标签（最终答案）
            if "<answer>" in content:
                interleaved_parts.append(content)
                # 提取最终答案
                answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                if answer_match:
                    final_answer = answer_match.group(1).strip()
                else:
                    # 如果没有闭合标签，取 <answer> 之后的所有内容
                    final_answer = content.split("<answer>")[-1].strip()
                print(f"  ✓ 获取到最终答案")
                break
            
            # 检查是否包含工具调用
            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )
            
            if tool_call_matches:
                # 先添加当前内容（包含 think 和 call_tool）
                interleaved_parts.append(content)
                
                # 执行所有工具调用
                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches:
                    # 解析参数
                    parameters = {}
                    if params_str:
                        param_matches = re.findall(r'(\w+)="([^"]*)"', params_str)
                        for k, v in param_matches:
                            try:
                                parameters[k] = int(v)
                            except:
                                parameters[k] = v
                    
                    query = query.strip()
                    tools_used.add(tool_name)
                    total_tool_calls += 1
                    
                    print(f"  执行工具: {tool_name}({query[:50]}...)")
                    
                    # 执行工具
                    raw_result, formatted_output = await self.tool_executor.execute_tool(
                        tool_name, parameters, query
                    )
                    
                    tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        parameters=parameters,
                        query=query,
                        result=self._truncate_result(raw_result),
                        timestamp=datetime.now().isoformat()
                    ))
                    
                    all_tool_outputs.append(formatted_output)
                
                # 添加工具输出
                tool_output_text = "\n".join(all_tool_outputs)
                interleaved_parts.append(tool_output_text)
                
                # 将工具输出添加到消息中继续对话
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": tool_output_text})
                
            else:
                # 没有工具调用也没有 answer，可能是纯思考，添加并继续
                interleaved_parts.append(content)
                messages.append({"role": "assistant", "content": content})
                # 提示继续
                messages.append({"role": "user", "content": "Please continue with tool calls or provide your final answer."})
        
        # 组合完整的 interleaved 文本
        interleaved_text = "\n".join(interleaved_parts)
        
        # 提取所有引用的 PMIDs
        pmids_cited = list(set(re.findall(r'<cite\s+id="(\d+)"', interleaved_text)))
        
        return Trajectory(
            question=question,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            final_answer=final_answer,
            total_tool_calls=total_tool_calls,
            tools_used=list(tools_used),
            pmids_cited=pmids_cited
        )
    
    async def _call_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用 OpenRouter LLM API"""
        request_data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    content=json.dumps(request_data, ensure_ascii=False).encode('utf-8'),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"LLM 调用失败: {e}")
                return None
    
    def _truncate_result(self, result: Any, max_length: int = 3000) -> Any:
        """截断过长的结果"""
        if isinstance(result, dict):
            # 对于 pubmed 结果，只保留关键字段
            if "data" in result:
                truncated_data = []
                for paper in result.get("data", [])[:5]:
                    if isinstance(paper, dict):
                        truncated_data.append({
                            "paperId": paper.get("paperId"),
                            "title": paper.get("title"),
                            "abstract": paper.get("abstract", "")[:300],
                            "year": paper.get("year"),
                            "venue": paper.get("venue"),
                        })
                return {"total": result.get("total"), "data": truncated_data}
            
            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                return {"truncated": True, "preview": result_str[:max_length]}
        return result


async def generate_content_rubrics_from_trajectory(
    question: str,
    trajectory: Trajectory,
    model: str = None
) -> List[Dict]:
    """根据轨迹结果生成内容相关的 rubrics"""
    from topic_generator import call_llm, extract_json
    
    # 提取轨迹中的关键信息
    tool_results = []
    for tc in trajectory.tool_calls:
        if tc.tool_name == "pubmed_search" and tc.result:
            result = tc.result
            if isinstance(result, dict) and "data" in result:
                for paper in result["data"][:5]:
                    if isinstance(paper, dict):
                        tool_results.append({
                            "pmid": paper.get("paperId", ""),
                            "title": paper.get("title", ""),
                            "abstract": paper.get("abstract", "")[:400],
                            "year": paper.get("year", ""),
                            "venue": paper.get("venue", "")
                        })
    
    prompt = f"""你是一个医学研究评估专家。基于以下问题和 GPT 模型通过工具调用获取的论文信息，生成 4-8 条内容评分项。

**用户问题**: {question}

**模型最终回答**: 
{trajectory.final_answer[:1500]}...

**检索到的论文**:
{json.dumps(tool_results, ensure_ascii=False, indent=2)[:3000]}

**要求**:
1. 每条 rubric 描述模型回答中应该提到的一个具体知识点
2. 这些知识点必须能从检索到的论文中找到依据
3. rubric 应该具体、可验证
4. 生成 4-8 条

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
    
    try:
        response = await call_llm(prompt, temperature=0.5, model=model)
        result = extract_json(response)
        
        rubrics = []
        for item in result.get("content_rubrics", []):
            rubrics.append({
                "category": "content",
                "title": item["title"],
                "description": item["description"],
                "weight": 3
            })
        return rubrics[:8]
    except Exception as e:
        print(f"生成内容 rubrics 失败: {e}")
        # 返回基于轨迹的默认 rubrics
        default_rubrics = []
        for i, paper in enumerate(tool_results[:4]):
            default_rubrics.append({
                "category": "content",
                "title": f"引用论文 {paper.get('pmid', i+1)}",
                "description": f"提到 {paper.get('title', '该论文')[:50]} 的主要发现",
                "weight": 3
            })
        return default_rubrics


if __name__ == "__main__":
    # 简单测试
    async def test():
        generator = GPT5TrajectoryGenerator(model="openai/gpt-4o")
        
        question = "比较 BRCA1 突变乳腺癌中 PARP 抑制剂和免疫治疗的最新研究进展"
        print(f"问题: {question}\n")
        print("正在生成轨迹...")
        
        trajectory = await generator.generate_trajectory(question)
        
        print(f"\n生成完成！")
        print(f"工具调用次数: {trajectory.total_tool_calls}")
        print(f"使用的工具: {trajectory.tools_used}")
        print(f"引用的 PMIDs: {trajectory.pmids_cited}")
        
        print("\n=== Interleaved 轨迹 ===")
        print(trajectory.interleaved_text[:3000] + "...")
        
        print("\n=== 最终答案 ===")
        print(trajectory.final_answer[:1000] + "...")
        
        # 生成 content rubrics
        print("\n正在生成内容 rubrics...")
        content_rubrics = await generate_content_rubrics_from_trajectory(question, trajectory)
        print(f"生成了 {len(content_rubrics)} 条内容 rubrics:")
        for r in content_rubrics:
            print(f"  - {r['title']}: {r['description'][:50]}...")
    
    asyncio.run(test())
