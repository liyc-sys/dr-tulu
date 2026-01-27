"""
使用本地模型 + MCP 工具回答 PubMed 问题
读取 PubMed JSONL 数据，调用本地模型生成带工具调用的答案
"""
import asyncio
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import OUTPUT_DIR, MCP_HOST, MCP_PORT
from trajectory_generator import (
    MCPToolExecutor,
    ToolCallRecord,
)
import httpx


# System Prompt - 只包含格式要求和工具介绍
PUBMED_SYSTEM_PROMPT = """You are a medical research assistant. Answer questions using available tools.

**IMPORTANT: All your responses, including <think>, <answer>, and citations, must be in English.**

## Available Tools

1. **pubmed_search** - Search PubMed medical literature database
   - Format: <call_tool name="pubmed_search" limit="N">keywords</call_tool>
   - Input: Medical/scientific keywords
   - Returns: Paper titles, authors, abstracts, PMIDs, publication year, journal name
   - Example: <call_tool name="pubmed_search" limit="5">CRISPR BCL11A sickle cell</call_tool>

2. **google_search** - Search the web using Google
   - Format: <call_tool name="google_search">query</call_tool>
   - Input: Search query string
   - Returns: Web search results with titles, snippets, and URLs
   - Example: <call_tool name="google_search">COVID-19 vaccine efficacy 2024</call_tool>

3. **browse_webpage** - Fetch and read webpage content
   - Format: <call_tool name="browse_webpage">URL</call_tool>
   - Input: Full URL of the webpage
   - Returns: Webpage content in markdown format
   - Example: <call_tool name="browse_webpage">https://pubmed.ncbi.nlm.nih.gov/12345678/</call_tool>

## SKILLS: How to Use Tools Effectively

### Priority: Always Try pubmed_search FIRST
For medical/scientific questions, **pubmed_search should be your first choice** because:
- It provides peer-reviewed, authoritative medical literature
- Returns structured data with PMIDs for proper citation
- Includes full abstracts with detailed findings

### pubmed_search Best Practices

**1. Decompose Complex Questions:**
If a question covers multiple topics (e.g., comparing treatments for CF, ALS, and HD), issue **separate search queries** for each topic. Do not try to answer everything in one search.
- Example: For "Compare gene therapy approaches in CF, ALS, and Huntington's disease"
  - First search: `cystic fibrosis gene therapy`
  - Second search: `ALS gene therapy`
  - Third search: `Huntington disease gene therapy`

**2. Start Broad with Core Keywords:**
- **Use 2-4 core keywords** (e.g., "Disease + DrugClass" or "Disease + Treatment + Outcome")
- PubMed uses AND logic, so more keywords = fewer results
- Avoid long, complex queries or hyper-specific constraints initially
- Only add specificity if you get too many irrelevant results

**Good Examples:**
- `BRCA1 breast cancer PARP inhibitor` (3 keywords - focused)
- `diabetes metformin cardiovascular` (3 keywords - broad enough)
- `COVID-19 mRNA vaccine efficacy` (4 keywords - topical)

**Bad Examples (Avoid):**
- `CRISPR Cas9 BCL11A enhancer sickle cell disease beta thalassemia clinical trial` (TOO MANY keywords - will return 0 results)
- `cancer treatment` (TOO BROAD - millions of results)
- `what is the best treatment for diabetes` (Natural language - use keywords instead)

**3. Adapt to Zero Results:**
If a search returns `Found 0 results`, you MUST simplify immediately:
- Remove adjectives, specific drug names, or outcome measures
- Use broader disease categories or drug classes
- Try synonyms: "myocardial infarction" → "heart attack", "neoplasm" → "cancer"
- **Do NOT repeat the same search logic with slight phrasing changes**

**Example Recovery:**
- Failed: `pembrolizumab advanced NSCLC first-line PFS OS` → 0 results
- Simplified: `pembrolizumab NSCLC survival` → results found

**4. No Fabrication (CRITICAL):**
If no relevant results are found after broader attempts, you MUST explicitly state that no evidence was found. **Never generate citations for search results that do not exist.**

### When to Use Other Tools

**Use google_search when:**
- Looking for recent news, guidelines, or regulatory information
- PubMed search returns 0 results after multiple refinement attempts
- Need non-academic sources (clinical guidelines, FDA approvals, drug labels)

**Use browse_webpage when:**
- You have a specific URL to examine (e.g., from google_search results)
- Need full text of a specific PubMed article: `https://pubmed.ncbi.nlm.nih.gov/{PMID}/`
- Checking clinical trial registries (clinicaltrials.gov) or official sources

## CRITICAL FORMAT RULES

### Tag Format (MUST FOLLOW EXACTLY)
1. **Always close your tags**: `<call_tool name="...">query</call_tool>` - the `</call_tool>` is REQUIRED
2. **One tool call at a time**: Issue ONE <call_tool>...</call_tool>, then STOP
3. **Never write multiple call_tool tags** in the same response

### FORBIDDEN Actions (Will make response INVALID)
- Writing `<tool_output>` - only system provides this
- Multiple `<call_tool>` in one response
- Unclosed tags like `<call_tool name="pubmed_search">query` without `</call_tool>`
- Fabricating PMIDs, paper titles, or results
- Using more than 6 keywords in pubmed_search
- Calling tools (any combination) more than 5 times total

### After <call_tool> (CRITICAL)
- **You MUST STOP your response IMMEDIATELY after `</call_tool>` - do NOT write anything else**
- **Do NOT write another <think> or <call_tool> in the same response**
- **Do NOT write <answer> in the same response as <call_tool>**
- Wait for the system to provide `<tool_output>`
- Your response should end exactly at `</call_tool>` - nothing after it

## CRITICAL LIMITS (MUST FOLLOW)
- **You can call tools AT MOST 5 times in total (including pubmed_search, browse_webpage, google_search)**
- **After 5 tool calls, you MUST provide your final answer immediately**
- **Do NOT exceed this limit under any circumstances**
- pubmed_search: Use 3-6 keywords maximum per search
- Plan your tool usage carefully to maximize information from each call

## Output Tags (ONLY these are allowed)
- `<think>reasoning</think>`
- `<call_tool name="...">query</call_tool>` (properly closed!)
- `<answer>final answer with citations</answer>`

## Citation Format
Use `<cite id="PMID">text</cite>` with PMIDs from actual search results.

## Output Format

Your final answer must use this format:

<answer>
<think>Your reasoning process</think>
<result>Your final answer based on the retrieved information</result>
</answer>
"""


@dataclass
class PubMedResult:
    """PubMed 问题的回答结果"""
    sample_id: str
    question: str
    topic: str
    question_type: str
    model_answer: str
    model_reasoning: str
    interleaved_text: str
    tool_calls: List[ToolCallRecord]
    generation_time: str

    def to_dict(self) -> Dict:
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "topic": self.topic,
            "question_type": self.question_type,
            "model_answer": self.model_answer,
            "model_reasoning": self.model_reasoning,
            "interleaved_text": self.interleaved_text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "generation_time": self.generation_time
        }


class PubMedAnswerer:
    """使用本地模型 + MCP 工具回答 PubMed 问题"""

    # 工具映射：逻辑名 -> MCP 工具名
    TOOL_MAPPING = {
        "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
        "google_search": "serper_google_webpage_search",
        "pubmed_search": "pubmed_search",
    }

    def __init__(
        self,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        max_turns: int = 10
    ):
        self.local_model_url = local_model_url
        self.model_name = model_name
        self.max_turns = max_turns
        self.tool_executor = MCPToolExecutor(host=MCP_HOST, port=MCP_PORT)

    def _remove_hallucinated_tool_output(self, content: str) -> str:
        """移除模型可能生成的假 tool_output 内容"""
        pattern = r'(</call_tool>)\s*<tool_output>.*?(?:</tool_output>|$)'
        cleaned = re.sub(pattern, r'\1', content, flags=re.DOTALL)

        if '<tool_output>' in cleaned:
            idx = cleaned.find('<tool_output>')
            cleaned = cleaned[:idx].rstrip()

        return cleaned

    def _clean_model_output(self, content: str, first_tool_call: tuple) -> str:
        """清理模型输出，只保留到第一个有效的 call_tool 为止"""
        tool_name, params_str, query = first_tool_call

        if params_str:
            call_tool_tag = f'<call_tool name="{tool_name}" {params_str}>{query}</call_tool>'
        else:
            call_tool_tag = f'<call_tool name="{tool_name}">{query}</call_tool>'

        first_call_idx = content.find('<call_tool')
        if first_call_idx == -1:
            return content

        prefix = content[:first_call_idx]

        close_tag_idx = content.find('</call_tool>', first_call_idx)
        if close_tag_idx != -1:
            clean_content = content[:close_tag_idx + len('</call_tool>')]
        else:
            clean_content = prefix + call_tool_tag

        clean_content = self._remove_hallucinated_tool_output(clean_content)

        return clean_content

    async def _execute_tool_with_mapping(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        query: str
    ) -> tuple[Dict[str, Any], str]:
        """执行工具调用，使用自定义映射"""
        # 获取 MCP 工具名
        mcp_tool_name = self.TOOL_MAPPING.get(tool_name, tool_name)

        # 构建参数 - 根据不同工具类型
        if tool_name == "pubmed_search":
            mcp_params = {
                "query": query,
                "limit": parameters.get("limit", 10),
                "offset": parameters.get("offset", 0)
            }
        elif tool_name == "browse_webpage":
            mcp_params = {
                "url": query,
                "use_ai2_config": True,
            }
        elif tool_name == "google_search":
            mcp_params = {
                "query": query,
                "num_results": parameters.get("num_results", 10)
            }
        else:
            # 默认使用 query 参数
            mcp_params = {"query": query, **parameters}

        # 调用 MCP 工具
        from fastmcp import Client
        client = Client(f"http://{MCP_HOST}:{MCP_PORT}/mcp", timeout=120)

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

                # 格式化输出
                formatted_output = self._format_tool_output(tool_name, raw_result)
                return raw_result, formatted_output

        except Exception as e:
            error_result = {"error": str(e)}
            return error_result, f"<tool_output>Error: {str(e)}</tool_output>"

    def _format_tool_output(self, tool_name: str, raw_result: Dict[str, Any]) -> str:
        """格式化工具输出"""
        err = raw_result.get("error")
        if err is not None and err != "":
            return f"<tool_output>Error: {err}</tool_output>"

        if tool_name == "pubmed_search":
            snippets = []
            data = raw_result.get("data", [])
            for paper in data[:10]:  # 最多10篇
                pmid = paper.get("paperId", "unknown")
                title = paper.get("title", "No title")
                abstract = paper.get("abstract", "No abstract")
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
            md = raw_result.get("markdown") or ""
            if md:
                content = md[:8000]
            else:
                content = json.dumps(raw_result, ensure_ascii=False)[:2000]
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

        # 默认格式化
        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False, indent=2)}</tool_output>"

    async def answer_question(self, question_data: Dict) -> PubMedResult:
        """为单个 PubMed 问题生成答案"""

        sample_id = str(question_data.get("sample_id", ""))
        question = question_data.get("question", "")
        topic = question_data.get("topic", "")
        question_type = question_data.get("question_type", "")

        messages = [
            {"role": "system", "content": PUBMED_SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]

        tool_calls = []
        total_tool_calls = 0
        interleaved_parts = []
        model_answer = ""
        model_reasoning = ""

        for turn in range(self.max_turns):
            # 调用本地 LLM
            response = await self._call_local_llm(messages)

            if not response:
                print(f"  ⚠ LLM 无响应，停止生成")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                print(f"  ⚠ 响应内容为空，停止生成")
                break

            # 检查工具调用
            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )

            # 如果没有闭合标签的匹配，尝试匹配未闭合的
            if not tool_call_matches:
                unclosed_matches = re.findall(
                    r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>(.*?)(?=<call_tool|<answer|$)',
                    content, re.DOTALL
                )
                if unclosed_matches:
                    first_match = unclosed_matches[0]
                    tool_name = first_match[0]
                    params_str = first_match[1]
                    query = first_match[2].strip().split('\n')[0].strip()
                    tool_call_matches = [(tool_name, params_str, query)]
                    print(f"  ⚠ 检测到未闭合的 <call_tool>，自动修复")

            if tool_call_matches:
                # 清理内容
                clean_content = self._clean_model_output(content, tool_call_matches[0])
                interleaved_parts.append(clean_content)

                # 只执行第一个工具调用
                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches[:1]:
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
                    total_tool_calls += 1

                    print(f"  执行工具: {tool_name}({query})")

                    # 执行工具
                    raw_result, formatted_output = await self._execute_tool_with_mapping(
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

                messages.append({"role": "assistant", "content": clean_content})

                # 检查是否达到工具调用限制
                if total_tool_calls >= 5:
                    reminder = f"{tool_output_text}\n\n⚠️ You have reached the maximum limit of 5 tool calls. You MUST provide your final answer now using the <answer> tag."
                    messages.append({"role": "user", "content": reminder})
                    print(f"  ⚠️ 已达到工具调用上限 (5次)，提醒模型给出答案")
                else:
                    messages.append({"role": "user", "content": tool_output_text})

            else:
                # 检查是否有 <answer>
                if "<answer>" in content:
                    interleaved_parts.append(content)

                    # 提取 <result>
                    result_match = re.search(r'<result>(.*?)</result>', content, re.DOTALL | re.IGNORECASE)
                    if result_match:
                        model_answer = result_match.group(1).strip()

                    # 提取推理过程
                    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
                    if think_match:
                        model_reasoning = think_match.group(1).strip()
                    else:
                        # 如果没有 think，就用整个 answer 内容
                        answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                        if answer_match:
                            model_reasoning = answer_match.group(1).strip()

                    print(f"  ✓ 模型答案: {model_answer[:100]}...")
                    break
                else:
                    interleaved_parts.append(content)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please provide your final answer using the <answer> tag with <result> inside."})

        # 如果没有提取到答案，尝试从最后的内容中提取
        if not model_answer and interleaved_parts:
            last_content = interleaved_parts[-1]
            model_answer = last_content.strip()
            print(f"  ⚠ 使用最后内容作为答案: {model_answer[:100]}...")

        # 组合完整的 interleaved 文本
        interleaved_text = "\n".join(interleaved_parts)

        return PubMedResult(
            sample_id=sample_id,
            question=question,
            topic=topic,
            question_type=question_type,
            model_answer=model_answer,
            model_reasoning=model_reasoning,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            generation_time=datetime.now().isoformat()
        )

    async def _call_local_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用本地模型 API（OpenAI兼容格式）"""
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "stop": ["</call_tool>\n", "</call_tool><", "<tool_output>"],
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{self.local_model_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    content=json.dumps(request_data, ensure_ascii=False).encode('utf-8'),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"本地LLM调用失败: {e}")
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
                            "abstract": paper.get("abstract", ""),
                            "year": paper.get("year"),
                            "venue": paper.get("venue"),
                        })
                return {"total": result.get("total"), "data": truncated_data}

            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                return {"truncated": True, "preview": result_str[:max_length]}
        return result


class PubMedRunner:
    """运行 PubMed 评测"""

    def __init__(
        self,
        data_file: str,
        local_model_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        output_dir: str = OUTPUT_DIR,
        instance_id: str = None
    ):
        self.data_file = data_file
        self.model_name = model_name
        self.instance_id = instance_id

        # 提取基础模型名
        api_model_name = model_name.split("_port")[0] if "_port" in model_name else model_name

        self.answerer = PubMedAnswerer(
            local_model_url=local_model_url,
            model_name=api_model_name
        )

        self.results: List[PubMedResult] = []
        self.output_dir = output_dir

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_suffix = api_model_name.replace("/", "_").replace(":", "_")

        if instance_id:
            file_suffix = f"{model_suffix}_{instance_id}"
        else:
            file_suffix = model_suffix

        self.output_file = os.path.join(
            self.output_dir,
            f"pubmed_results_{timestamp}_{file_suffix}.jsonl"
        )
        self.stats_file = os.path.join(
            self.output_dir,
            f"pubmed_stats_{timestamp}_{file_suffix}.json"
        )
        self.timestamp = timestamp

    def load_questions(self) -> List[Dict]:
        """从 JSONL 加载问题"""
        print(f"从文件加载问题: {self.data_file}")
        questions = []

        with open(self.data_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        questions.append({
                            "sample_id": data.get("sample_id", ""),
                            "question": data.get("question", ""),
                            "topic": data.get("topic", ""),
                            "question_type": data.get("question_type", ""),
                        })
                    except json.JSONDecodeError as e:
                        print(f"  ⚠ JSON 解析错误: {e}")

        print(f"✓ 加载了 {len(questions)} 个问题")
        return questions

    async def run_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[PubMedResult]:
        """带重试机制的问答"""
        async with semaphore:
            for attempt in range(max_retries):
                try:
                    result = await self.answerer.answer_question(q_data)
                    return result
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"  ⚠️ [{sample_index}] 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                        print(f"  ⏳ 等待 {wait_time}s 后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"  ✗ [{sample_index}] 所有重试失败: {e}")
            return None

    async def run_evaluation(self, concurrency: int = 5, limit: int = None):
        """运行评测"""
        print("\n" + "=" * 60)
        print("PubMed 评测 - 使用本地模型 + MCP 工具")
        print("=" * 60)
        print(f"本地模型: {self.answerer.model_name}")
        print(f"API地址: {self.answerer.local_model_url}")
        print(f"并发数: {concurrency}")

        # 加载问题
        questions = self.load_questions()

        if not questions:
            print("✗ 没有加载到任何问题")
            return

        # 如果设置了limit，只处理前N个问题
        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")

        # 并发生成答案
        print("\n" + "=" * 60)
        print("开始回答问题（并发模式）")
        print("=" * 60)

        semaphore = asyncio.Semaphore(concurrency)

        tasks = []
        for i, q_data in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] Topic: {q_data.get('topic', '')} | Question: {q_data.get('question', '')[:80]}...")
            task = self.run_with_retry(q_data, i, semaphore)
            tasks.append(task)

        # 执行并显示进度
        completed = 0
        total = len(tasks)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1

            if result:
                self.results.append(result)

                # 增量保存
                self.append_result_to_file(result)

                print(f"  ✓ 模型答案: {result.model_answer[:100]}...")

            # 显示进度
            print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%)")

        # 保存统计
        self.save_stats()

        print(f"\n{'='*60}")
        print(f"评测完成！")
        print(f"总问题数: {len(self.results)}")
        print(f"结果保存到: {self.output_file}")
        print(f"统计保存到: {self.stats_file}")
        print(f"{'='*60}")

    def append_result_to_file(self, result: PubMedResult):
        """增量保存：追加单条结果到文件"""
        try:
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"  ⚠️ 增量保存失败: {e}")

    def save_stats(self):
        """保存统计信息"""
        if not self.results:
            print("⚠️ 没有结果可保存")
            return

        # 按 topic 统计
        by_topic = {}
        for r in self.results:
            topic = r.topic
            if topic not in by_topic:
                by_topic[topic] = {"total": 0}
            by_topic[topic]["total"] += 1

        # 按 question_type 统计
        by_type = {}
        for r in self.results:
            qtype = r.question_type
            if qtype not in by_type:
                by_type[qtype] = {"total": 0}
            by_type[qtype]["total"] += 1

        # 工具使用统计
        total_tool_calls = sum(len(r.tool_calls) for r in self.results)
        avg_tool_calls = total_tool_calls / len(self.results) if self.results else 0

        stats = {
            "total_questions": len(self.results),
            "by_topic": by_topic,
            "by_question_type": by_type,
            "tool_usage": {
                "total_tool_calls": total_tool_calls,
                "avg_tool_calls_per_question": avg_tool_calls
            },
            "model": self.answerer.model_name,
            "instance_id": self.instance_id,
            "data_file": self.data_file,
            "generation_time": datetime.now().isoformat()
        }

        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        print(f"✓ 统计已保存")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="使用本地模型 + MCP 工具回答 PubMed 问题")

    # 使用相对路径
    _script_path = Path(__file__).resolve()
    _root = (_script_path.parent / ".." / "..").resolve()
    _default_data = str(_root / "交付数据" / "matched_data_1.jsonl")
    _default_output = str(_root / "pubmed_training_data")

    parser.add_argument("--data-file", type=str, default=_default_data,
                        help="PubMed JSONL 文件路径")
    parser.add_argument("--local-model-url", type=str, default="http://localhost:8000/v1",
                        help="本地模型API地址（OpenAI兼容格式）")
    parser.add_argument("--model-name", type=str, default="Qwen3-8B", help="模型名称")
    parser.add_argument("--instance-id", type=str, default=None, help="实例标识（如port8000）")
    parser.add_argument("--output", type=str, default=_default_output, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的问题数量（用于测试）")

    args = parser.parse_args()

    print(f"本地模型: {args.model_name}")
    print(f"API地址: {args.local_model_url}")
    print(f"数据文件: {args.data_file}")
    print(f"并发数: {args.concurrency}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")

    runner = PubMedRunner(
        data_file=args.data_file,
        local_model_url=args.local_model_url,
        model_name=args.model_name,
        output_dir=args.output,
        instance_id=args.instance_id
    )

    try:
        await runner.run_evaluation(concurrency=args.concurrency, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，保存已完成的结果...")
        if runner.results:
            runner.save_stats()
        print("✓ 已保存部分结果")
    except Exception as e:
        print(f"\n\n✗ 评测过程出错: {e}")
        import traceback
        traceback.print_exc()
        if runner.results:
            print("\n保存已完成的结果...")
            runner.save_stats()

    print("\n" + "=" * 60)
    print("评测完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
