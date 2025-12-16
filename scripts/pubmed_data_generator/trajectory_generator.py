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
SYSTEM_PROMPT = """You are a medical research assistant. Answer questions using PubMed literature search.

## Available Tools

1. pubmed_search 
- Format: <call_tool name="pubmed_search" limit="N">keywords</call_tool>
- **IMPORTANT: Use 3-6 keywords maximum. Long queries often return 0 results.**
- Good: <call_tool name="pubmed_search" limit="5">CRISPR BCL11A sickle cell</call_tool>
- Bad (TOO LONG): <call_tool name="pubmed_search">CTX001 exa-cel BCL11A enhancer CRISPR Cas9 sickle cell beta thalassemia trial</call_tool>

2. browse_webpage: <call_tool name="browse_webpage">URL</call_tool>
3. google_search: <call_tool name="google_search">query</call_tool>

## CRITICAL FORMAT RULES

### Tag Format (MUST FOLLOW EXACTLY)
1. **Always close your tags**: `<call_tool name="...">query</call_tool>` - the `</call_tool>` is REQUIRED
2. **One tool call at a time**: Issue ONE <call_tool>...</call_tool>, then STOP
3. **Never write multiple call_tool tags** in the same response

### FORBIDDEN Actions (Will make response INVALID)
- ❌ Writing `<tool_output>` - only system provides this
- ❌ Multiple `<call_tool>` in one response  
- ❌ Unclosed tags like `<call_tool name="pubmed_search">query` without `</call_tool>`
- ❌ Fabricating PMIDs, paper titles, or results
- ❌ Using more than 6 keywords in pubmed_search
- ❌ Calling pubmed_search more than 3 times total

### After <call_tool> (CRITICAL)
- **You MUST STOP your response IMMEDIATELY after `</call_tool>` - do NOT write anything else**
- **Do NOT write another <think> or <call_tool> in the same response**
- **Do NOT write <answer> in the same response as <call_tool>**
- Wait for the system to provide `<tool_output>`
- Your response should end exactly at `</call_tool>` - nothing after it

## CRITICAL LIMITS (MUST FOLLOW)
- **⚠️ pubmed_search can be called AT MOST 3 times in total**
- **After 3 pubmed_search calls, you MUST provide your final answer immediately**
- **Do NOT exceed this limit under any circumstances**
- Keywords per search: 3-6 words maximum
- Plan your searches carefully to maximize information from each call

## Output Tags (ONLY these are allowed)
- `<think>reasoning</think>`
- `<call_tool name="...">query</call_tool>` (properly closed!)
- `<answer>final answer with citations</answer>`

## Citation Format
Use `<cite id="PMID">text</cite>` with PMIDs from actual search results.

## CORRECT Example

<think>I need to search for papers on NLR and PD-1 in lung cancer. This will be my first search (out of maximum 3).</think>
<call_tool name="pubmed_search" limit="5">NLR PD-1 lung cancer prognosis</call_tool>

[STOP HERE - your response ends after </call_tool>]

After receiving tool output, if you need more information:
<think>I found some relevant papers. I need more specific information, so I'll do my second search (2/3).</think>
<call_tool name="pubmed_search" limit="5">different keywords</call_tool>

## WRONG Examples (DO NOT DO THIS)

### Wrong 1: Multiple calls in one response
<call_tool name="pubmed_search" limit="5">query1</call_tool>
<think>Now search for query2...</think>
<call_tool name="pubmed_search" limit="5">query2</call_tool>

❌ WRONG: Multiple calls in one response. Only ONE call per response!

### Wrong 2: Continue after </call_tool>
<call_tool name="pubmed_search" limit="5">query</call_tool>
<think>Now I will analyze...</think>

❌ WRONG: Writing after </call_tool>. Stop immediately after the closing tag!

### Wrong 3: call_tool and answer together
<call_tool name="pubmed_search" limit="5">query</call_tool>
<answer>Based on my knowledge...</answer>

❌ WRONG: Mixing call_tool and answer. Wait for tool output first!
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
            "browse_webpage": "crawl4ai_docker_fetch_webpage_content",  # 使用 Docker 版本
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
            return {
                "url": query,
                "use_ai2_config": True,  # 使用 AI2 配置，从环境变量读取 Docker API 设置
            }
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
                abstract = paper.get("abstract", "No abstract")  # 完整摘要
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

    def _remove_hallucinated_tool_output(self, content: str) -> str:
        """移除模型可能生成的假 tool_output 内容"""
        # 如果内容中有 </call_tool> 后跟着 <tool_output>，截断它
        pattern = r'(</call_tool>)\s*<tool_output>.*?(?:</tool_output>|$)'
        cleaned = re.sub(pattern, r'\1', content, flags=re.DOTALL)
        
        # 如果还有未闭合的 <tool_output>，也删除
        if '<tool_output>' in cleaned:
            idx = cleaned.find('<tool_output>')
            cleaned = cleaned[:idx].rstrip()
        
        return cleaned
    
    def _clean_model_output(self, content: str, first_tool_call: tuple) -> str:
        """清理模型输出，只保留到第一个有效的 call_tool 为止"""
        tool_name, params_str, query = first_tool_call
        
        # 构建第一个 call_tool 的正确格式
        if params_str:
            call_tool_tag = f'<call_tool name="{tool_name}" {params_str}>{query}</call_tool>'
        else:
            call_tool_tag = f'<call_tool name="{tool_name}">{query}</call_tool>'
        
        # 找到第一个 <call_tool 的位置
        first_call_idx = content.find('<call_tool')
        if first_call_idx == -1:
            return content
        
        # 获取 call_tool 之前的内容（如 <think>...</think>）
        prefix = content[:first_call_idx]
        
        # 检查是否有闭合标签
        close_tag_idx = content.find('</call_tool>', first_call_idx)
        if close_tag_idx != -1:
            # 有闭合标签，取到闭合标签为止
            clean_content = content[:close_tag_idx + len('</call_tool>')]
        else:
            # 没有闭合标签，手动构建正确格式
            clean_content = prefix + call_tool_tag
        
        # 移除任何 tool_output
        clean_content = self._remove_hallucinated_tool_output(clean_content)
        
        return clean_content
        
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
            
            # 重要：先检查工具调用，再检查 answer
            # 这样如果模型在一次响应中同时生成了 call_tool 和 answer，
            # 我们可以先执行工具，然后在下一轮处理 answer
            
            # 检查是否包含工具调用（支持闭合和未闭合的标签）
            # 先尝试匹配闭合的标签
            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )
            
            # 如果没有闭合标签的匹配，尝试匹配未闭合的
            if not tool_call_matches:
                # 匹配未闭合的 <call_tool> 标签，query 可能以换行或 <call_tool 或 <answer 结束
                unclosed_matches = re.findall(
                    r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>(.*?)(?=<call_tool|<answer|$)',
                    content, re.DOTALL
                )
                if unclosed_matches:
                    # 只取第一个未闭合的调用
                    first_match = unclosed_matches[0]
                    tool_name = first_match[0]
                    params_str = first_match[1]
                    query = first_match[2].strip().split('\n')[0].strip()  # 取第一行作为 query
                    tool_call_matches = [(tool_name, params_str, query)]
                    print(f"  ⚠ 检测到未闭合的 <call_tool>，自动修复")
            
            if tool_call_matches:
                # 清理内容：移除假的 tool_output 和多余的未闭合 call_tool
                clean_content = self._clean_model_output(content, tool_call_matches[0])
                
                # 添加清理后的内容
                interleaved_parts.append(clean_content)
                
                # 只执行第一个工具调用（避免一次执行多个）
                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches[:1]:  # 只取第一个
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
                    
                    print(f"  执行工具: {tool_name}({query})")
                    
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
                # 注意：发送清理后的内容，不包含模型可能生成的假 tool_output
                messages.append({"role": "assistant", "content": clean_content})
                messages.append({"role": "user", "content": tool_output_text})
                
            else:
                # 没有工具调用，检查是否有 <answer>
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
            "temperature": 0.1,  # 更低的温度，让模型更确定性
            "max_tokens": 1024,  # 更低的 max_tokens，防止一次生成太多
            # stop 序列
            "stop": ["</call_tool>\n", "</call_tool><", "<tool_output>"],
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
                            "abstract": paper.get("abstract", ""),  # 完整摘要
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
                            "abstract": paper.get("abstract", ""),  # 完整摘要
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
