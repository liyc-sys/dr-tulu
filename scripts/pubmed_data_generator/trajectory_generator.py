"""
轨迹生成器：调用 GPT-5 连接 MCP 工具，生成工具调用轨迹
"""
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
import httpx

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MCP_HOST, MCP_PORT


# MCP 工具定义（OpenAI function calling 格式）
MCP_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "pubmed_search",
            "description": "Search for medical and scientific papers using PubMed API. Returns papers with PMID, title, abstract, year, venue, authors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string for PubMed"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Starting position for pagination (default: 0)",
                        "default": 0
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_webpage",
            "description": "Fetch and extract content from a webpage URL. Use this to read full text of papers or articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the webpage to fetch"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "General web search using Google. Use for finding non-academic information or supplementary resources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    }
]


@dataclass
class ToolCall:
    """单次工具调用"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    timestamp: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass 
class TrajectoryStep:
    """轨迹步骤"""
    step_index: int
    role: str  # assistant / tool
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    
    def to_dict(self) -> Dict:
        d = {
            "step_index": self.step_index,
            "role": self.role,
            "content": self.content
        }
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return d


@dataclass
class Trajectory:
    """完整的工具调用轨迹"""
    question: str
    steps: List[TrajectoryStep]
    final_answer: str
    total_tool_calls: int
    tools_used: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "question": self.question,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "total_tool_calls": self.total_tool_calls,
            "tools_used": self.tools_used
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
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行 MCP 工具调用"""
        client = await self._get_client()
        
        # 映射工具名到 MCP 工具名
        mcp_tool_mapping = {
            "pubmed_search": "pubmed_search",
            "browse_webpage": "crawl4ai_fetch_webpage_content",
            "google_search": "serper_google_webpage_search"
        }
        
        mcp_tool_name = mcp_tool_mapping.get(tool_name, tool_name)
        
        # 参数映射
        mcp_params = self._map_parameters(tool_name, arguments)
        
        try:
            async with client:
                result = await client.call_tool(mcp_tool_name, mcp_params)
                
                if hasattr(result, "content") and result.content:
                    if hasattr(result.content[0], "text"):
                        return json.loads(result.content[0].text)
                    else:
                        return {"data": str(result.content[0])}
                return {"error": "No content in response"}
        except Exception as e:
            return {"error": str(e)}
    
    def _map_parameters(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """映射参数到 MCP 工具格式"""
        if tool_name == "browse_webpage":
            return {"url": arguments.get("url", "")}
        elif tool_name == "google_search":
            return {
                "query": arguments.get("query", ""),
                "num_results": arguments.get("num_results", 10)
            }
        elif tool_name == "pubmed_search":
            return {
                "query": arguments.get("query", ""),
                "limit": arguments.get("limit", 10),
                "offset": arguments.get("offset", 0)
            }
        return arguments


class GPT5TrajectoryGenerator:
    """使用 GPT-5 生成工具调用轨迹"""
    
    def __init__(
        self,
        model: str = "openai/gpt-4o",  # 或 "openai/o1" 等
        max_turns: int = 10,
        api_key: str = None
    ):
        self.model = model
        self.max_turns = max_turns
        self.api_key = api_key or OPENROUTER_API_KEY
        self.tool_executor = MCPToolExecutor()
        
    async def generate_trajectory(self, question: str) -> Trajectory:
        """为给定问题生成完整的工具调用轨迹"""
        
        system_prompt = """你是一个医学研究助手，擅长使用工具来回答医学相关问题。

你可以使用以下工具：
1. pubmed_search - 搜索 PubMed 医学文献数据库，获取论文的 PMID、标题、摘要、年份、期刊等信息
2. browse_webpage - 访问网页获取完整内容
3. google_search - 通用网页搜索

回答要求：
1. 必须使用 pubmed_search 搜索相关文献
2. 在回答中引用具体的 PMID
3. 提供论文的年份和期刊信息
4. 从摘要中提取关键证据句

请根据用户问题，合理调用工具获取信息，然后给出完整回答。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]
        
        steps = []
        step_index = 0
        tools_used = set()
        total_tool_calls = 0
        final_answer = ""
        
        for turn in range(self.max_turns):
            # 调用 LLM
            response = await self._call_llm(messages)
            
            if not response:
                break
            
            message = response.get("choices", [{}])[0].get("message", {})
            
            # 检查是否有工具调用
            tool_calls = message.get("tool_calls", [])
            
            if tool_calls:
                # 记录 assistant 的工具调用请求
                tc_records = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    try:
                        arguments = json.loads(func.get("arguments", "{}"))
                    except:
                        arguments = {}
                    
                    tools_used.add(tool_name)
                    total_tool_calls += 1
                    
                    # 执行工具
                    print(f"  执行工具: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]}...)")
                    result = await self.tool_executor.execute_tool(tool_name, arguments)
                    
                    tc_records.append(ToolCall(
                        tool_name=tool_name,
                        arguments=arguments,
                        result=self._truncate_result(result),
                        timestamp=datetime.now().isoformat()
                    ))
                    
                    # 添加工具结果到消息
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(self._truncate_result(result), ensure_ascii=False)
                    })
                
                steps.append(TrajectoryStep(
                    step_index=step_index,
                    role="assistant",
                    content=message.get("content"),
                    tool_calls=tc_records
                ))
                step_index += 1
                
            else:
                # 没有工具调用，是最终回答
                final_answer = message.get("content", "")
                steps.append(TrajectoryStep(
                    step_index=step_index,
                    role="assistant",
                    content=final_answer,
                    tool_calls=None
                ))
                break
        
        return Trajectory(
            question=question,
            steps=steps,
            final_answer=final_answer,
            total_tool_calls=total_tool_calls,
            tools_used=list(tools_used)
        )
    
    async def _call_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用 OpenRouter LLM API"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": MCP_TOOLS_SCHEMA,
                        "tool_choice": "auto",
                        "temperature": 0.3,
                    },
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"LLM 调用失败: {e}")
                return None
    
    def _truncate_result(self, result: Any, max_length: int = 5000) -> Any:
        """截断过长的结果"""
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                # 尝试只保留关键字段
                if "data" in result:
                    data = result["data"]
                    if isinstance(data, list) and len(data) > 0:
                        # 保留前几条，截断摘要
                        truncated_data = []
                        for item in data[:5]:
                            if isinstance(item, dict):
                                truncated_item = {k: v for k, v in item.items()}
                                if "abstract" in truncated_item and truncated_item["abstract"]:
                                    truncated_item["abstract"] = truncated_item["abstract"][:500] + "..."
                                truncated_data.append(truncated_item)
                        return {"data": truncated_data, "total": result.get("total", len(data))}
            return result
        return result


async def generate_content_rubrics_from_trajectory(
    question: str,
    trajectory: Trajectory
) -> List[Dict]:
    """根据轨迹结果生成内容相关的 rubrics"""
    from topic_generator import call_llm, extract_json
    
    # 提取轨迹中的关键信息
    tool_results = []
    for step in trajectory.steps:
        if step.tool_calls:
            for tc in step.tool_calls:
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
        response = await call_llm(prompt, temperature=0.5)
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
    async def test():
        print("=" * 60)
        print("测试 GPT-5 轨迹生成")
        print("=" * 60)
        
        generator = GPT5TrajectoryGenerator(model="openai/gpt-4o")
        
        question = "BRCA1 突变乳腺癌患者使用 PARP 抑制剂的疗效如何？请引用最新研究。"
        print(f"\n问题: {question}\n")
        
        print("正在生成轨迹...")
        trajectory = await generator.generate_trajectory(question)
        
        print(f"\n轨迹统计:")
        print(f"  - 步骤数: {len(trajectory.steps)}")
        print(f"  - 工具调用次数: {trajectory.total_tool_calls}")
        print(f"  - 使用的工具: {trajectory.tools_used}")
        
        print(f"\n最终回答 (前500字):")
        print(trajectory.final_answer[:500] + "...")
        
        print("\n完整轨迹 JSON:")
        print(json.dumps(trajectory.to_dict(), indent=2, ensure_ascii=False)[:2000] + "...")
        
        # 生成 content rubrics
        print("\n正在生成内容 rubrics...")
        content_rubrics = await generate_content_rubrics_from_trajectory(question, trajectory)
        print(f"生成了 {len(content_rubrics)} 条内容 rubrics:")
        for r in content_rubrics:
            print(f"  - {r['title']}: {r['description'][:50]}...")
    
    asyncio.run(test())

