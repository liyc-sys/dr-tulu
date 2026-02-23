"""
使用 OpenRouter API + MCP 工具回答 MedBrowseComp 问题
基于 answer_medbrowsecomp_with_tools2.py，将 LLM 调用改为 OpenRouter API

模型: seed1.8 (通过 --model-name 指定)
"""
import asyncio
import json
import os
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import MCP_HOST, MCP_PORT, OPENROUTER_API_KEY
from trajectory_generator import (
    MCPToolExecutor,
    ToolCallRecord,
)
import httpx
import re


# MedBrowseComp System Prompt (与 with_tools2 一致)
MEDBROWSECOMP_SYSTEM_PROMPT = """You are an expert medical research assistant. Answer questions about clinical trials, drug patents, approvals, and exclusivity information.

## Special Case: Stock Price Questions

If a question asks about stock prices:
- You may attempt to search for the information using available tools (e.g., google_search, browse_webpage)
- However, if after your search attempts you cannot find the stock price information, respond with: `Not_Listed`
- Do NOT fabricate or guess stock prices

## Role & Operational Constraints

When solving problems using tools, adhere to the following strict protocols:

1. **State Awareness & Efficiency**:
   - Before calling a tool, REVIEW the conversation history to avoid redundancy
   - NEVER call a tool with the same parameters twice
   - If a previous call failed or yielded no results, CHANGE your strategy (e.g., use a different search query, try a different tool, or add a reason parameter)
   - Before each tool call, explicitly state in your thinking: "I have checked history and am not repeating previous actions"
   - **CRITICAL**: If you receive a "DUPLICATE QUERY DETECTED" warning, you MUST try a different approach immediately

2. **Data Validity & Critical Thinking**:
   - Always verify the *recency* and *completeness* of tool outputs
   - If the user asks for current data (e.g., "latest approval up to Dec 2024") and the tool returns outdated data (e.g., from 2010), DO NOT accept it as final truth
   - Cross-verify critical information using alternative tools if needed (e.g., use google_search or browse_webpage to verify dates)
   - Remember: FDA Orange Book tools return data filtered from year 2000+ and sorted to show latest records

3. **Anti-Hallucination & Accuracy**:
   - When extracting specific values (dates, names, company names), perform a CHARACTER-LEVEL check against the tool output
   - Do not paraphrase proprietary names or alter dates (e.g., do not confuse "Jun" with "Jul", or "2025" with "2035")
   - If the tool says "No exclusivity found," strictly report "DATE: NA" — do not invent a date
   - Copy exact strings from tool outputs for names, dates, and other critical values
   - Before outputting your final answer, explicitly verify: "I am verifying the extracted value [Value] against the source to ensure character-level accuracy"

4. **Reasoning Process Requirements**:
   - In your <think> block, you must:
     * State: "I have checked conversation history and am not repeating actions"
     * Show your step-by-step reasoning for each tool call
     * Explicitly verify extracted data: "Verifying [field] = [value] from tool output"
     * Acknowledge any data limitations or missing information
   - Your reasoning should demonstrate critical thinking, not just parroting tool outputs

## Tool Usage Priority

**IMPORTANT - Always follow this order:**
1. **FIRST CHOICE**: Use `medbrowsecomp_search` for most queries (it auto-routes to the correct underlying tool)
2. **ALTERNATIVE**: Use specific tools (`get_trial_info`, `get_drug_patents`, etc.) when you need precise control

**Why use medbrowsecomp_search first:**
- Automatic routing based on query content
- Better error handling and fallback
- Supports the `reason` parameter to guide routing
- More flexible input parsing

## Available Tools

1. **medbrowsecomp_search** - Unified medical search (RECOMMENDED - USE THIS FIRST)
   - Format: <call_tool name="medbrowsecomp_search" reason="purpose">query</call_tool>
   - Input: Query string (NCT ID or ingredient query)
   - Optional parameter: reason (can be: "patent", "approval", "exclusivity")
   - **Routing rules:**
     * If query contains NCT ID (e.g., "NCT01639001") → auto-routes to get_trial_info (reason parameter is ignored)
     * If query contains "ingredient" keyword → uses reason parameter to route to drug tools
   - **CRITICAL for drug queries:** The query MUST contain the word "ingredient" to trigger drug lookup routing
   - Example (NCT lookup): <call_tool name="medbrowsecomp_search">NCT01639001</call_tool>
   - Example (patent lookup): <call_tool name="medbrowsecomp_search" reason="patent">ingredient crizotinib</call_tool>
   - Example (approval lookup): <call_tool name="medbrowsecomp_search" reason="approval">ingredient crizotinib</call_tool>
   - Example (exclusivity lookup): <call_tool name="medbrowsecomp_search" reason="exclusivity">ingredient crizotinib</call_tool>

2. **get_trial_info** - Get ClinicalTrials.gov trial information by NCT number
   - Format: <call_tool name="get_trial_info">NCT_ID</call_tool>
   - Input: NCT ID (11 characters starting with "NCT" followed by 8 digits)
   - Returns: Trial sponsor, recruitment status, drug ingredients (intervention names), sources
   - Example: <call_tool name="get_trial_info">NCT01639001</call_tool>

2. **get_drug_patents** - Get FDA Orange Book drug patents
   - Format: <call_tool name="get_drug_patents">ingredient_name</call_tool>
   - Input: Drug ingredient name (generic name, case-insensitive)
   - Returns: Patent numbers, jurisdictions, expiry dates, notes
   - Example: <call_tool name="get_drug_patents">crizotinib</call_tool>

3. **get_drug_approvals** - Get FDA Orange Book drug approvals
   - Format: <call_tool name="get_drug_approvals">ingredient_name</call_tool>
   - Input: Drug ingredient name (generic name, case-insensitive)
   - Returns: Product names, approval dates, companies, approval status (filtered from year 2000+, sorted by date, limited to latest)
   - Example: <call_tool name="get_drug_approvals">crizotinib</call_tool>

4. **get_drug_exclusivities** - Get FDA Orange Book drug exclusivity periods
   - Format: <call_tool name="get_drug_exclusivities">ingredient_name</call_tool>
   - Input: Drug ingredient name (generic name, case-insensitive)
   - Returns: Exclusivity types, start dates, end dates, notes (sorted by end_date, limited to latest)
   - Example: <call_tool name="get_drug_exclusivities">crizotinib</call_tool>

## Tool Usage Skills and Workflow

### Tool Selection Guide

**When to use each tool:**

**RECOMMENDED APPROACH:**
- For most queries, use `medbrowsecomp_search` with appropriate `reason` parameter
- Only use specific tools when you need very precise control or medbrowsecomp_search fails

1. **medbrowsecomp_search (USE THIS FIRST)** - Use for:
   - Any NCT trial lookup → Auto-routes to get_trial_info (just include NCT ID in query)
   - Drug patent lookup → Use `reason="patent"` with query containing "ingredient" keyword
   - Drug approval lookup → Use `reason="approval"` with query containing "ingredient" keyword
   - Drug exclusivity lookup → Use `reason="exclusivity"` with query containing "ingredient" keyword
   - ⚠️ For drug queries, query MUST contain "ingredient" keyword (e.g., "ingredient crizotinib")
   - ✅ Better error messages and unified interface

2. **get_trial_info** - Use when you need:
   - Clinical trial sponsor information
   - Trial recruitment status
   - **Drug ingredients used in a specific trial** (this is the KEY use case)
   - Source URLs for verification
   - ✅ Always use this FIRST when the question mentions an NCT ID and asks about ingredients

3. **get_drug_patents** - Use when you need:
   - Patent expiration dates for a drug
   - Patent numbers and jurisdictions
   - Patent-related notes
   - ⚠️ Input: Use the exact ingredient name (generic name like "crizotinib", not brand name)

4. **get_drug_approvals** - Use when you need:
   - FDA approval dates
   - Pharmaceutical company/applicant information
   - Product names and approval status
   - ⚠️ Returns only approvals from year 2000 onwards, sorted by date
   - ⚠️ Limited to top 1 latest approval

5. **get_drug_exclusivities** - Use when you need:
   - Exclusivity periods and end dates
   - Exclusivity types (e.g., NCE, ODE, Pediatric)
   - Start and end dates of exclusivity
   - ⚠️ Returns top 1 latest exclusivity sorted by end_date


### Recommended Workflow

**Multi-Step Questions Workflow** (Most Common Pattern):

Many questions follow this structure:
1. First, identify an ingredient from a clinical trial
2. Then, look up information (patent/approval/exclusivity) for that ingredient

**Example Question Pattern:**
"For clinical trial NCT01639001, among the more effective regimen ingredients, identify which ingredient starts with the letter C. Then, when is its patent expiration date?"

**Step-by-step approach:**

**Step 1: Extract the NCT ID from the question**
- Look for the pattern "NCT" followed by 8 digits
- Example: NCT01639001

**Step 2: Get trial ingredients (RECOMMENDED: use medbrowsecomp_search)**
```
<call_tool name="medbrowsecomp_search">NCT01639001</call_tool>
```
Or alternatively:
```
<call_tool name="get_trial_info">NCT01639001</call_tool>
```
Wait for result. You will get a list of ingredients like: ["Crizotinib", "Pemetrexed", ...]

**Step 3: Identify the target ingredient**
- Apply any filters mentioned in the question (e.g., "starts with letter C")
- Extract the exact ingredient name (e.g., "Crizotinib")

**Step 4: Call the appropriate drug information tool (RECOMMENDED: use medbrowsecomp_search with reason)**
- For patent information → use `medbrowsecomp_search` with `reason="patent"`
- For approval information → use `medbrowsecomp_search` with `reason="approval"`
- For exclusivity information → use `medbrowsecomp_search` with `reason="exclusivity"`

Example (RECOMMENDED):
```
<call_tool name="medbrowsecomp_search" reason="patent">crizotinib</call_tool>
```

Alternative (specific tool):
```
<call_tool name="get_drug_patents">crizotinib</call_tool>
```

**Step 5: Extract and format the answer**
- Parse the returned data
- Extract the specific information requested (e.g., expiry_date, approval_date, company name)
- **CRITICAL**: Perform character-level verification - copy exact values from tool output
- **CRITICAL**: In your <think> block, explicitly verify: "Verifying [field] = '[exact_value]' from tool output"
- Check for data completeness and recency (especially for "latest" queries)
- Format according to the question's requirements (e.g., "DATE: MM-DD-YYYY", "COMPANY: name", "INGREDIENT: name")

### Tool-Specific Best Practices

**medbrowsecomp_search (RECOMMENDED)**:
- ✅ Use this tool FIRST for most queries
- ✅ For NCT IDs: Just pass the NCT ID, no need for reason parameter
- ✅ For drug queries: Add `reason` parameter to guide routing
  - `reason="patent"` for patent information
  - `reason="approval"` for approval/company information
  - `reason="exclusivity"` for exclusivity periods
- ✅ Better error handling than specific tools
- ⚠️ If it fails with "无法识别查询类型", fall back to specific tools

**get_trial_info**:
- ✅ Use EXACTLY 11 characters: "NCT" + 8 digits (e.g., NCT01639001)
- ✅ The "ingredients" field contains the intervention drug names from the trial
- ✅ Use this tool FIRST when you need to identify drugs used in a trial
- ❌ Do not add extra text or questions in the query field
- ❌ Correct: <call_tool name="get_trial_info">NCT01639001</call_tool>
- ❌ Incorrect: <call_tool name="get_trial_info">What are the ingredients in NCT01639001?</call_tool>

**get_drug_patents**:
- ✅ Use the ingredient name only (generic name like "crizotinib")
- ✅ Case-insensitive: "Crizotinib", "crizotinib", "CRIZOTINIB" all work
- ✅ Returns patent expiry_date in the format provided by FDA Orange Book
- ⚠️ The expiry_date might be in different formats (e.g., "Jun 26, 2035" or "2035")
- ❌ Do not use brand names; use generic ingredient names

**get_drug_approvals**:
- ✅ Use the ingredient name only (generic name)
- ✅ Returns approval_date and marketing_authorisation_holder (company name)
- ✅ **IMPORTANT**: Returns only approvals from year 2000 onwards
- ✅ **IMPORTANT**: Sorted by approval_date and limited to top 1 (latest approval)
- ✅ The field "marketing_authorisation_holder" contains the company name
- ⚠️ If you need "the latest FDA approval date", this is the right tool
- ⚠️ If you need "which company has the latest FDA approval", check the "marketing_authorisation_holder" field
- ⚠️ **DATA VALIDATION**: If question asks for "latest approval up to Dec 2024" and you get approval from 2010, verify this is truly the latest by checking if newer approvals exist (use google_search or browse_webpage to cross-check)

**get_drug_exclusivities**:
- ✅ Use the ingredient name only (generic name)
- ✅ Returns exclusivity end_date (expiration of exclusivity period)
- ✅ **IMPORTANT**: Sorted by end_date and limited to top 1 (latest exclusivity)
- ⚠️ If no exclusivity exists, the result will indicate this
- ⚠️ Different types of exclusivity: NCE (New Chemical Entity), ODE (Orphan Drug), Pediatric, etc.

### Example Workflows

**Example 1: Find ingredient and its patent expiry date**

Question: "For clinical trial NCT01639001, among the more effective regimen ingredients, identify which ingredient starts with the letter C. Then, when is its patent expiration date?"

Workflow (RECOMMENDED):
1. Extract NCT ID: NCT01639001
2. Call: <call_tool name="medbrowsecomp_search">NCT01639001</call_tool>
3. Wait for result → ingredients: ["Crizotinib", "Pemetrexed", ...]
4. Filter by first letter "C" → Crizotinib
5. Call: <call_tool name="medbrowsecomp_search" reason="patent">ingredient crizotinib</call_tool>
6. Extract expiry_date from result
7. Format answer: "Jun 26, 2035" or "2035" (as specified in question format)

**Example 2: Find ingredient and the company with latest approval**

Question: "For clinical trial NCT01307605, identify which ingredient starts with the letter L. Then, find which company has the latest FDA approval date for this ingredient."

Workflow (RECOMMENDED with verification):
1. Extract NCT ID: NCT01307605
2. Check history: "I have checked conversation history and am not repeating previous actions"
3. Call: <call_tool name="medbrowsecomp_search">NCT01307605</call_tool>
4. Wait for result → Filter by letter "L" → e.g., "Lirilumab"
5. Call: <call_tool name="medbrowsecomp_search" reason="approval">ingredient lirilumab</call_tool>
6. Extract marketing_authorisation_holder from result (this is automatically the latest since results are sorted)
7. **VERIFY in <think>**: "Verifying company name = 'BRISTOL MYERS SQUIBB' from tool output. Performing character-level check. Question asks for latest approval up to Dec 2024. Tool returned approval from [year]. Confirming this is within the valid time range."
8. Format answer: "COMPANY: BRISTOL MYERS SQUIBB" (exact copy from tool output)

**Example 3: Find ingredient and exclusivity date**

Question: "For clinical trial NCT03150875, identify which ingredient starts with the letter D. Then, when is its exclusivity date according to the FDA?"

Workflow (RECOMMENDED with null-handling):
1. Extract NCT ID: NCT03150875
2. Check history: "I have checked conversation history and am not repeating previous actions"
3. Call: <call_tool name="medbrowsecomp_search">NCT03150875</call_tool>
4. Wait for result → Filter by letter "D" → e.g., "Durvalumab"
5. Call: <call_tool name="medbrowsecomp_search" reason="exclusivity">ingredient durvalumab</call_tool>
6. Check tool output carefully:
   - If tool says "No exclusivity found" or count=0: **VERIFY in <think>**: "Tool returned no exclusivity data. As per instructions, I must return 'DATE: NA' and NOT invent a date."
   - If exclusivity exists: Extract end_date and **VERIFY in <think>**: "Verifying end_date = '[exact_date]' from tool output. Performing character-level check."
7. Format answer:
   - If no exclusivity: "DATE: NA" (do NOT invent a date)
   - If exclusivity exists: "DATE: MM-DD-YYYY" (exact copy from tool output, no reformatting)

**Example 4: Simple ingredient identification**

Question: "For clinical trial NCT01469000, among the more effective regimen ingredients, find which is the ingredient with the first letter start with P."

Workflow (RECOMMENDED):
1. Extract NCT ID: NCT01469000
2. Call: <call_tool name="medbrowsecomp_search">NCT01469000</call_tool>
3. Wait for result → ingredients: ["Pemetrexed Disodium", "Cisplatin", ...]
4. Filter by first letter "P" → "Pemetrexed Disodium"
5. Format answer: "INGREDIENT: PEMETREXED DISODIUM" (or as specified)

### Common Pitfalls to Avoid

❌ **WRONG**: Calling drug tools without first getting the ingredient from the trial
- Don't guess ingredient names
- Always call get_trial_info (or medbrowsecomp_search) first to get the actual ingredients

❌ **WRONG**: Using brand names in drug tools
- Use generic ingredient names (e.g., "crizotinib" not "Xalkori")
- The trial info returns generic names, use those directly

❌ **WRONG**: Adding natural language in tool query fields
- Correct: <call_tool name="get_trial_info">NCT01639001</call_tool>
- Incorrect: <call_tool name="get_trial_info">Get info for NCT01639001</call_tool>

❌ **WRONG**: Assuming approval/exclusivity data exists
- Always check if the result contains the data
- For missing exclusivity, return "DATE: NA" as specified

❌ **WRONG**: Using the wrong field name
- For company name → use "marketing_authorisation_holder" (not "company" or "applicant")
- For patent expiry → use "expiry_date" (not "expiration_date")

❌ **WRONG**: Repeating the same tool call after failure
- If a tool call fails or returns no data, CHANGE your strategy
- Try: different tool (e.g., switch from specific tool to medbrowsecomp_search), add reason parameter, or verify with google_search
- Never call the same tool with identical parameters twice
- **If you see "DUPLICATE QUERY DETECTED", you MUST change your approach**

❌ **WRONG**: Accepting outdated data without verification
- If you see approval dates from early 2000s but the question asks for "latest approval up to 2024", question whether this is truly the latest
- FDA tools show top 1 latest approval from 2000+, but data may be incomplete
- Consider cross-checking with google_search or browse_webpage if data seems outdated

❌ **WRONG**: Paraphrasing or altering extracted values
- Copy dates EXACTLY as shown: "Jun 26, 2035" not "June 26, 2035" or "2035-06-26"
- Copy company names EXACTLY: "HOFFMANN LA ROCHE INC" not "Hoffmann-La Roche" or "Roche"
- Do character-level verification before outputting final answer

❌ **WRONG**: Inventing data when tool returns nothing
- If tool says "No exclusivity found" → answer must be "DATE: NA"
- If tool returns empty results → do not fabricate information
- Acknowledge data limitations in your reasoning

### Answer Format Requirements

Your final answer MUST follow the question's specified format:

- Ingredient identification: "INGREDIENT: NAME" (all caps as specified)
- Date format: "DATE: MM-DD-YYYY" or "MM-DD-YYYY" or "YYYY" (as specified in question)
- Company format: "COMPANY: name" (as specified)
- Unknown/NA: "DATE: NA" if exclusivity doesn't exist

## Format Rules

### During Tool Calls
Each tool call MUST follow this exact format:

<think>
Goal: [What you're trying to find]
Plan: [Your step-by-step approach]
Next query: [Why you're making this specific tool call]
</think>
<call_tool name="tool_name" param="value">query</call_tool>

**CRITICAL**:
- Always include <think> before EVERY <call_tool>
- Stop IMMEDIATELY after </call_tool> and wait for <tool_output>
- Never write <tool_output> yourself
- Only one tool call per response

### Final Answer
When you have enough information, provide your final answer:

<answer>
[Your reasoning process explaining how you arrived at the answer, including verification of extracted data]

[Your final answer following the EXACT format specified in the question, e.g., "INGREDIENT: NAME", "DATE: MM-DD-YYYY", "COMPANY: name", or for multiple choice: "Correct answer: X) answer text"]
</answer>

**Critical**: The <answer> tag should contain your reasoning followed by the final answer. Do NOT use nested <think> or <result> tags inside <answer>.
"""


@dataclass
class MedBrowseCompResult:
    """MedBrowseComp 问题的回答结果"""
    question_id: str
    question: str
    task_name: str
    correct_answer: str
    model_answer: str
    model_reasoning: str
    interleaved_text: str
    tool_calls: List[ToolCallRecord]
    is_correct: bool
    generation_time: str
    duplicate_queries_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "task_name": self.task_name,
            "correct_answer": self.correct_answer,
            "model_answer": self.model_answer,
            "model_reasoning": self.model_reasoning,
            "interleaved_text": self.interleaved_text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_correct": self.is_correct,
            "generation_time": self.generation_time,
            "duplicate_queries_count": self.duplicate_queries_count
        }


class MedBrowseCompOpenRouterAnswerer:
    """使用 OpenRouter API + MCP 工具回答 MedBrowseComp 问题"""

    # 工具映射：逻辑名 -> MCP 工具名
    TOOL_MAPPING = {
        "medbrowsecomp_search": "medbrowsecomp_search",
        "get_trial_info": "get_trial_info",
        "get_drug_patents": "get_drug_patents",
        "get_drug_approvals": "get_drug_approvals",
        "get_drug_exclusivities": "get_drug_exclusivities",
        "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
        "google_search": "serper_google_webpage_search",
    }

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "seed1.8",
        max_turns: int = 15,
        temperature: float = 0.1,
    ):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model_name = model_name
        self.max_turns = max_turns
        self.temperature = temperature
        self.base_url = "https://openrouter.ai/api/v1"
        self.tool_executor = MCPToolExecutor(host=MCP_HOST, port=MCP_PORT)

    def _make_query_key(self, tool_name: str, query: str, parameters: Dict[str, Any]) -> str:
        """生成用于检测重复的唯一 key"""
        normalized_query = query.strip().lower()
        key_parts = [tool_name, normalized_query]
        if "reason" in parameters:
            key_parts.append(f"reason={parameters['reason']}")
        return "|".join(key_parts)

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
        mcp_tool_name = self.TOOL_MAPPING.get(tool_name, tool_name)

        if tool_name == "get_trial_info":
            mcp_params = {"nct_id": query}
        elif tool_name in ["get_drug_patents", "get_drug_approvals", "get_drug_exclusivities"]:
            mcp_params = {"ingredients": query}
        elif tool_name == "medbrowsecomp_search":
            mcp_params = {"query": query}
            if "reason" in parameters:
                mcp_params["reason"] = parameters["reason"]
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
            mcp_params = {"query": query, **parameters}

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

        if tool_name == "get_trial_info":
            success = raw_result.get("success", False)
            if not success:
                return f"<tool_output>Trial information not found</tool_output>"

            nct_id = raw_result.get("nct_id", "")
            ingredients = raw_result.get("ingredients", [])
            sponsor = raw_result.get("sponsor", "")
            recruitment_status = raw_result.get("recruitment_status", "")
            sources = raw_result.get("sources", [])

            output = f"<tool_output>\nClinical Trial: {nct_id}\n"
            output += f"Sponsor: {sponsor}\n"
            output += f"Recruitment Status: {recruitment_status}\n"
            output += f"Ingredients (Interventions): {', '.join(ingredients) if ingredients else 'None'}\n"
            if sources:
                output += f"Sources: {', '.join(sources)}\n"
            output += "</tool_output>"
            return output

        elif tool_name == "get_drug_patents":
            success = raw_result.get("success", False)
            patents = raw_result.get("patents", [])
            count = raw_result.get("count", 0)

            if not success or count == 0:
                return f"<tool_output>No patent information found</tool_output>"

            output = f"<tool_output>\nFound {count} patent(s):\n"
            for i, patent in enumerate(patents, 1):
                output += f"\nPatent {i}:\n"
                output += f"  Number: {patent.get('number', 'N/A')}\n"
                output += f"  Jurisdiction: {patent.get('jurisdiction', 'N/A')}\n"
                output += f"  Expiry Date: {patent.get('expiry_date', 'N/A')}\n"
                if patent.get('notes'):
                    output += f"  Notes: {patent['notes']}\n"
            output += "</tool_output>"
            return output

        elif tool_name == "get_drug_approvals":
            success = raw_result.get("success", False)
            approvals = raw_result.get("approvals", [])
            count = raw_result.get("count", 0)

            if not success or count == 0:
                return f"<tool_output>No approval information found</tool_output>"

            output = f"<tool_output>\nFound {count} approval(s) (from year 2000+, showing latest):\n"
            for i, approval in enumerate(approvals, 1):
                output += f"\nApproval {i}:\n"
                output += f"  Product Name: {approval.get('product_name', 'N/A')}\n"
                output += f"  Active Ingredient: {approval.get('active_ingredient', 'N/A')}\n"
                output += f"  Approval Date: {approval.get('approval_date', 'N/A')}\n"
                output += f"  Company: {approval.get('marketing_authorisation_holder', 'N/A')}\n"
                output += f"  Status: {approval.get('status', 'N/A')}\n"
                output += f"  Region: {approval.get('region', 'N/A')}\n"
            output += "</tool_output>"
            return output

        elif tool_name == "get_drug_exclusivities":
            success = raw_result.get("success", False)
            exclusivities = raw_result.get("exclusivities", [])
            count = raw_result.get("count", 0)

            if not success or count == 0:
                return f"<tool_output>No exclusivity information found</tool_output>"

            output = f"<tool_output>\nFound {count} exclusivity period(s) (showing latest by end date):\n"
            for i, excl in enumerate(exclusivities, 1):
                output += f"\nExclusivity {i}:\n"
                output += f"  Type: {excl.get('type', 'N/A')}\n"
                output += f"  Start Date: {excl.get('start_date', 'N/A')}\n"
                output += f"  End Date: {excl.get('end_date', 'N/A')}\n"
                output += f"  Region: {excl.get('region', 'N/A')}\n"
                if excl.get('notes'):
                    output += f"  Notes: {excl['notes']}\n"
            output += "</tool_output>"
            return output

        elif tool_name == "medbrowsecomp_search":
            metadata = raw_result.get("_search_metadata", {})
            actual_function = metadata.get("function_called", "")

            if actual_function:
                return self._format_tool_output(actual_function, raw_result)
            else:
                return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False, indent=2)}</tool_output>"

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

        return f"<tool_output>{json.dumps(raw_result, ensure_ascii=False, indent=2)}</tool_output>"

    def _generate_duplicate_warning(self, tool_name: str, query: str, parameters: Dict[str, Any]) -> str:
        """生成重复查询警告消息"""
        reason_str = f" with reason='{parameters.get('reason', '')}'" if 'reason' in parameters else ""
        return f"""<tool_output>
⚠️ DUPLICATE QUERY DETECTED ⚠️

You have already called the tool '{tool_name}' with the same query: "{query}"{reason_str}

This is a REPEATED action. Please:
1. Review the previous tool output in the conversation history
2. If the previous result was insufficient, try a DIFFERENT approach:
   - Use a different tool (e.g., google_search instead of medbrowsecomp_search)
   - Use a different query formulation
   - Add or change the 'reason' parameter
   - Try browsing a specific webpage directly
3. If you have enough information, provide your final answer using <answer> tags

DO NOT repeat the same tool call again.
</tool_output>"""

    async def answer_question(self, question_data: Dict) -> MedBrowseCompResult:
        """为单个 MedBrowseComp 问题生成答案"""

        question_id = str(question_data.get("row_id", ""))
        question = question_data.get("prompt", "")
        task_name = question_data.get("task_name", "")
        correct_answer = question_data.get("gold", "")

        messages = [
            {"role": "system", "content": MEDBROWSECOMP_SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]

        tool_calls = []
        total_tool_calls = 0
        interleaved_parts = []
        model_answer = ""
        model_reasoning = ""

        # 记录已执行的查询，用于检测重复
        executed_queries: Set[str] = set()
        duplicate_queries_count = 0

        for turn in range(self.max_turns):
            response = await self._call_openrouter_llm(messages)

            if not response:
                print(f"  ⚠ LLM 无响应，停止生成")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                print(f"  ⚠ 响应内容为空，停止生成")
                break

            tool_call_matches = re.findall(
                r'<call_tool\s+name="([^"]+)"(?:\s+([^>]*))?>([^<]*)</call_tool>',
                content
            )

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
                clean_content = self._clean_model_output(content, tool_call_matches[0])
                interleaved_parts.append(clean_content)

                all_tool_outputs = []
                for tool_name, params_str, query in tool_call_matches[:1]:
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

                    # 检测重复查询
                    query_key = self._make_query_key(tool_name, query, parameters)

                    if query_key in executed_queries:
                        duplicate_queries_count += 1
                        print(f"  ⚠️ 检测到重复查询: {tool_name}({query}) - 返回警告")
                        formatted_output = self._generate_duplicate_warning(tool_name, query, parameters)

                        tool_calls.append(ToolCallRecord(
                            tool_name=tool_name,
                            parameters={**parameters, "_duplicate": True},
                            query=query,
                            result={"duplicate": True, "warning": "Duplicate query detected"},
                            timestamp=datetime.now().isoformat()
                        ))
                    else:
                        executed_queries.add(query_key)
                        print(f"  执行工具: {tool_name}({query})")

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

                tool_output_text = "\n".join(all_tool_outputs)
                interleaved_parts.append(tool_output_text)

                messages.append({"role": "assistant", "content": clean_content})
                messages.append({"role": "user", "content": tool_output_text})

            else:
                if "<answer>" in content:
                    interleaved_parts.append(content)

                    result_match = re.search(r'<result>(.*?)</result>', content, re.DOTALL | re.IGNORECASE)
                    if result_match:
                        model_answer = result_match.group(1).strip()

                    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
                    if think_match:
                        model_reasoning = think_match.group(1).strip()
                    else:
                        answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                        if answer_match:
                            model_reasoning = answer_match.group(1).strip()

                    print(f"  ✓ 模型答案: {model_answer}")
                    break
                else:
                    interleaved_parts.append(content)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please provide your final answer using the <answer> tag with <result> inside."})

        if not model_answer and interleaved_parts:
            last_content = interleaved_parts[-1]
            model_answer = last_content.strip()
            print(f"  ⚠ 使用最后内容作为答案: {model_answer[:100]}...")

        interleaved_text = "\n".join(interleaved_parts)

        is_correct = self._check_answer_correctness(model_answer, correct_answer)

        return MedBrowseCompResult(
            question_id=question_id,
            question=question,
            task_name=task_name,
            correct_answer=correct_answer,
            model_answer=model_answer,
            model_reasoning=model_reasoning,
            interleaved_text=interleaved_text,
            tool_calls=tool_calls,
            is_correct=is_correct,
            generation_time=datetime.now().isoformat(),
            duplicate_queries_count=duplicate_queries_count
        )

    def _check_answer_correctness(self, model_answer: str, correct_answer: str) -> bool:
        """检查答案是否正确"""
        if not model_answer or not correct_answer:
            return False

        model_ans_norm = model_answer.strip().upper()
        correct_ans_norm = correct_answer.strip().upper()

        if model_ans_norm == correct_ans_norm:
            return True

        if correct_ans_norm in model_ans_norm or model_ans_norm in correct_ans_norm:
            return True

        return False

    async def _call_openrouter_llm(self, messages: List[Dict]) -> Optional[Dict]:
        """调用 OpenRouter API"""
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "stop": ["</call_tool>\n", "</call_tool><", "<tool_output>"],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-org/dr-tulu",
            "X-Title": "DR-Tulu MedBrowseComp Eval"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    content=json.dumps(request_data, ensure_ascii=False).encode('utf-8'),
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"OpenRouter API 调用失败: {e}")
                return None

    def _truncate_result(self, result: Any, max_length: int = 3000) -> Any:
        """截断过长的结果"""
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False)
            if len(result_str) > max_length:
                return {"truncated": True, "preview": result_str[:max_length]}
        return result


class MedBrowseCompRunner:
    """运行 MedBrowseComp 评测 (OpenRouter 版)"""

    def __init__(
        self,
        data_file: str,
        api_key: str = None,
        model_name: str = "seed1.8",
        output_dir: str = None,
        instance_id: str = None
    ):
        self.data_file = data_file
        self.model_name = model_name
        self.instance_id = instance_id

        self.answerer = MedBrowseCompOpenRouterAnswerer(
            api_key=api_key,
            model_name=model_name,
        )

        self.results: List[MedBrowseCompResult] = []

        # 默认输出目录：脚本所在目录的 ../../pubmed_training_data
        if output_dir is None:
            _script_path = Path(__file__).resolve()
            _root = (_script_path.parent / ".." / "..").resolve()
            output_dir = str(_root / "pubmed_training_data")
        self.output_dir = output_dir

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_suffix = model_name.replace("/", "_").replace(":", "_")

        if instance_id:
            file_suffix = f"{model_suffix}_{instance_id}"
        else:
            file_suffix = model_suffix

        self.output_file = os.path.join(
            self.output_dir,
            f"medbrowsecomp_results_{timestamp}_{file_suffix}.jsonl"
        )
        self.stats_file = os.path.join(
            self.output_dir,
            f"medbrowsecomp_stats_{timestamp}_{file_suffix}.json"
        )
        self.timestamp = timestamp

    def load_questions(self) -> List[Dict]:
        """从 CSV 加载问题"""
        print(f"从文件加载问题: {self.data_file}")
        questions = []

        with open(self.data_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                questions.append({
                    "row_id": i,
                    "gold": row.get("gold", ""),
                    "prompt": row.get("prompt", ""),
                    "task_name": row.get("task_name", "")
                })

        print(f"✓ 加载了 {len(questions)} 个问题")
        return questions

    async def run_with_retry(
        self,
        q_data: Dict,
        sample_index: int,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> Optional[MedBrowseCompResult]:
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
        print("MedBrowseComp 评测 - OpenRouter API (重复检测版)")
        print("=" * 60)
        print(f"模型: {self.answerer.model_name}")
        print(f"API: OpenRouter")
        print(f"并发数: {concurrency}")

        questions = self.load_questions()

        if not questions:
            print("✗ 没有加载到任何问题")
            return

        if limit is not None:
            questions = questions[:limit]
            print(f"⚠️ 限制处理前 {limit} 个问题")

        print("\n" + "=" * 60)
        print("开始回答问题（并发模式）")
        print("=" * 60)

        semaphore = asyncio.Semaphore(concurrency)

        tasks = []
        for i, q_data in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] Task: {q_data.get('task_name', '')} | Question: {q_data.get('prompt', '')[:80]}...")
            task = self.run_with_retry(q_data, i, semaphore)
            tasks.append(task)

        completed = 0
        correct = 0
        total = len(tasks)
        total_duplicates = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1

            if result:
                self.results.append(result)
                if result.is_correct:
                    correct += 1
                total_duplicates += result.duplicate_queries_count

                self.append_result_to_file(result)

                dup_info = f" (重复:{result.duplicate_queries_count})" if result.duplicate_queries_count > 0 else ""
                print(f"  {'✓' if result.is_correct else '✗'} 模型答案: {result.model_answer[:100]} | 正确答案: {result.correct_answer[:100]}{dup_info}")

            accuracy = (correct / len(self.results) * 100) if self.results else 0
            print(f"\n📊 进度: {completed}/{total} ({completed/total*100:.1f}%) | "
                  f"正确: {correct}/{len(self.results)} | "
                  f"准确率: {accuracy:.1f}% | "
                  f"总重复: {total_duplicates}")

        self.save_stats()

        print(f"\n{'='*60}")
        print(f"评测完成！")
        print(f"总问题数: {len(self.results)}")
        print(f"正确数: {correct}")
        print(f"准确率: {accuracy:.2f}%")
        print(f"检测到的重复查询总数: {total_duplicates}")
        print(f"结果保存到: {self.output_file}")
        print(f"统计保存到: {self.stats_file}")
        print(f"{'='*60}")

    def append_result_to_file(self, result: MedBrowseCompResult):
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

        correct_count = sum(1 for r in self.results if r.is_correct)
        accuracy = correct_count / len(self.results) * 100

        by_task = {}
        for r in self.results:
            task = r.task_name
            if task not in by_task:
                by_task[task] = {"total": 0, "correct": 0}
            by_task[task]["total"] += 1
            if r.is_correct:
                by_task[task]["correct"] += 1

        for task in by_task:
            by_task[task]["accuracy"] = by_task[task]["correct"] / by_task[task]["total"] * 100

        total_tool_calls = sum(len(r.tool_calls) for r in self.results)
        avg_tool_calls = total_tool_calls / len(self.results) if self.results else 0
        total_duplicates = sum(r.duplicate_queries_count for r in self.results)
        samples_with_duplicates = sum(1 for r in self.results if r.duplicate_queries_count > 0)

        stats = {
            "total_questions": len(self.results),
            "correct": correct_count,
            "accuracy": accuracy,
            "by_task_type": by_task,
            "tool_usage": {
                "total_tool_calls": total_tool_calls,
                "avg_tool_calls_per_question": avg_tool_calls
            },
            "duplicate_detection": {
                "total_duplicate_queries": total_duplicates,
                "samples_with_duplicates": samples_with_duplicates,
                "duplicate_rate": samples_with_duplicates / len(self.results) * 100 if self.results else 0
            },
            "model": self.answerer.model_name,
            "api": "openrouter",
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

    parser = argparse.ArgumentParser(description="使用 OpenRouter API + MCP 工具回答 MedBrowseComp 问题")

    _script_path = Path(__file__).resolve()
    _root = (_script_path.parent / ".." / "..").resolve()
    _default_data = str(_root / "训练和benchmark数据0120" / "MedBrowseComp_605_part2.csv")
    _default_output = str(_root / "pubmed_training_data")

    parser.add_argument("--data-file", type=str, default=_default_data,
                        help="MedBrowseComp CSV 文件路径")
    parser.add_argument("--model-name", type=str, default="seed1.8", help="OpenRouter 模型名称")
    parser.add_argument("--api-key", type=str, default=None,
                        help="OpenRouter API Key（默认从环境变量 OPENROUTER_API_KEY 读取）")
    parser.add_argument("--instance-id", type=str, default=None, help="实例标识")
    parser.add_argument("--output", type=str, default=_default_output, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的问题数量（用于测试）")

    args = parser.parse_args()

    print(f"模型: {args.model_name}")
    print(f"API: OpenRouter")
    print(f"数据文件: {args.data_file}")
    print(f"并发数: {args.concurrency}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")

    runner = MedBrowseCompRunner(
        data_file=args.data_file,
        api_key=args.api_key,
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
