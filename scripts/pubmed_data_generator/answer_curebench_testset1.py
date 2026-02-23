"""
使用本地模型 + MCP 工具回答 CureBench Testset 问题
基于 answer_curebench_with_tools1.py（带详细工具使用指南的 prompt）
"""
import asyncio
import json
import os
import sys
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
    SYSTEM_PROMPT,
    ToolCallRecord,
)
import httpx
import re


# 来自 answer_curebench_with_tools1.py 的 SYSTEM_PROMPT
CUREBENCH_SYSTEM_PROMPT = """You are a medical expert assistant. Answer multiple-choice medical questions.

## Available Tools

1. **fda_drug_search** - Search FDA drug labels for medication information (PRIMARY TOOL - USE FIRST)
   - Format: <call_tool name="fda_drug_search" focus="aspect">drug_name</call_tool>
   - The focus parameter can be: adverse reactions, indications and usage, dosage and administration, warnings and precautions, contraindications, drug interactions, pregnancy, lactation, or any other relevant aspect
   - Example: <call_tool name="fda_drug_search" focus="adverse reactions">metformin</call_tool>

2. browse_webpage - Fetch and read webpage content (use if FDA tool is insufficient)
   - Format: <call_tool name="browse_webpage">URL</call_tool>
   - Example: <call_tool name="browse_webpage">https://dailymed.nlm.nih.gov/...</call_tool>

3. google_search - Search the web for medical information (use as last resort)
   - Format: <call_tool name="google_search">query</call_tool>
   - Example: <call_tool name="google_search">drug name side effects</call_tool>

## Tool Usage Skills and Workflow

### Tool Priority Order (CRITICAL)

**ALWAYS follow this priority**:
1. **FIRST**: Try `fda_drug_search` for any drug-related question
2. **SECOND**: Use `browse_webpage` only if FDA search is insufficient
3. **LAST**: Use `google_search` as a last resort when other tools cannot help

### When to Use Each Tool

1. **fda_drug_search (PRIMARY TOOL)**:
   - **USE FIRST** for any question involving medications, drugs, pharmaceuticals
   - Side effects and adverse reactions
   - Drug indications and approved uses
   - Contraindications and warnings
   - Drug interactions
   - Dosage information
   - Pregnancy/lactation safety

2. **browse_webpage (SECONDARY)**:
   - Use ONLY if `fda_drug_search` doesn't provide sufficient information
   - Access FDA drug label pages directly
   - Read detailed medical websites

3. **google_search (LAST RESORT)**:
   - Use ONLY when FDA and browse_webpage cannot help
   - Recent medical news or updates
   - General medical information not drug-specific

### Recommended Workflow

1. **Analyze the question**: Identify if it's drug-related
2. **Start with FDA**: If the question mentions any drug, medication, or pharmaceutical → use `fda_drug_search` FIRST
3. **Choose correct focus parameter**:
   - Side effects → `focus="adverse reactions"`
   - Drug uses → `focus="indications and usage"`
   - Contraindications → `focus="contraindications"`
   - Drug interactions → `focus="drug interactions"`
   - Pregnancy safety → `focus="pregnancy"`
   - Dosing → `focus="dosage and administration"`
4. **Use exact drug names**: Generic or brand name as mentioned in the question
5. **Analyze results**: Extract specific facts from FDA labels
6. **Only escalate if needed**: If FDA doesn't provide enough info, then use browse_webpage or google_search
7. **Provide final answer**: Use the <answer> format with clear reasoning

### Tool-Specific Best Practices

**fda_drug_search** (USE THIS FIRST):
- ✅ Always try this tool first for drug questions
- ✅ Choose the most specific focus parameter
- ✅ Use exact drug names (generic or brand)
- ✅ Extract specific facts from the returned information
- ✅ Compare findings across multiple options if needed

**browse_webpage** (use only if FDA is insufficient):
- Access FDA label pages: `https://dailymed.nlm.nih.gov/...`
- Read medical reference websites
- Get more detailed information

**google_search** (last resort only):
- Use only when FDA and browse_webpage cannot help
- For general medical knowledge questions
- For recent updates not in FDA labels

### Example Workflows

**Example 1: Drug side effects (TYPICAL CASE)**
Question: "Which medication is most likely to cause hyperkalemia?"
1. ✅ **START WITH FDA**: <call_tool name="fda_drug_search" focus="adverse reactions">drug_option_A</call_tool>
2. Check if "hyperkalemia" is listed
3. Repeat for other options if needed
4. Choose based on FDA label evidence

**Example 2: Drug contraindications**
Question: "Which drug is contraindicated in pregnancy?"
1. ✅ **START WITH FDA**: <call_tool name="fda_drug_search" focus="pregnancy">drug_option_A</call_tool>
2. Check pregnancy category and contraindications
3. Compare options systematically
4. Choose the drug with pregnancy contraindication

**Example 3: When FDA is insufficient (RARE)**
Question: "What is the latest treatment guideline for X?"
1. Try FDA first: <call_tool name="fda_drug_search" focus="indications and usage">relevant_drug</call_tool>
2. If insufficient → <call_tool name="google_search">X treatment guidelines 2024</call_tool>
3. Analyze results and provide answer

## Format Rules

1. Tool calls must be properly closed: <call_tool name="...">query</call_tool>
2. Only one tool call per response
3. Stop immediately after </call_tool> and wait for <tool_output>
4. Never write <tool_output> yourself

## Format Rules

### During Tool Calls
Each tool call MUST follow this exact format:

<think>
Goal: [What you're trying to find]
Plan: [Your step-by-step approach]
Next query: [Why you're making this specific tool call]
</think>
<call_tool name="tool_name" param="value">query</call_tool>

### Final Answer
When you have gathered enough information, provide your final answer:

<answer>
[Your reasoning process explaining how you arrived at the answer, including what evidence you found from the tools]

The answer is X.
</answer>

Where X is A, B, C, or D.
"""

# 导入核心运行逻辑
from answer_curebench_testset import CureBenchResult, CureBenchAnswerer as BaseAnswerer, CureBenchRunner as BaseRunner


class CureBenchAnswerer(BaseAnswerer):
    """使用 prompt1 的回答器"""
    pass  # 继承所有逻辑，只需要覆盖 SYSTEM_PROMPT


# 覆盖基类的 answer_question 方法使用新的 SYSTEM_PROMPT
async def answer_question_with_prompt1(self, question_data: Dict) -> CureBenchResult:
    question_id = question_data.get("id", "")
    question = question_data.get("question", "")
    question_type = question_data.get("question_type", "")
    options = question_data.get("options", {})
    correct_answer = question_data.get("correct_answer", "")
    
    formatted_question = self._format_question_with_options(question, options)
    
    messages = [
        {"role": "system", "content": CUREBENCH_SYSTEM_PROMPT},  # 使用本文件的 PROMPT
        {"role": "user", "content": formatted_question}
    ]
    
    tool_calls = []
    total_tool_calls = 0
    interleaved_parts = []
    model_answer = ""
    model_reasoning = ""
    
    for turn in range(self.max_turns):
        response = await self._call_local_llm(messages)
        
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
                
                choice_match = re.search(r'<choice>([A-D])</choice>', content, re.IGNORECASE)
                if choice_match:
                    model_answer = choice_match.group(1).upper()
                
                think_match = re.search(r'<answer>.*?<think>(.*?)</think>', content, re.DOTALL)
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
                messages.append({"role": "user", "content": "Please provide your final answer using the <answer> tag with <choice> inside."})
    
    if not model_answer and interleaved_parts:
        last_content = interleaved_parts[-1]
        letter_match = re.search(r'\b([A-D])\b', last_content)
        if letter_match:
            model_answer = letter_match.group(1)
            print(f"  ⚠ 从内容中提取答案: {model_answer}")
    
    interleaved_text = "\n".join(interleaved_parts)
    
    if correct_answer:
        is_correct = (model_answer == correct_answer)
    else:
        is_correct = None
    
    return CureBenchResult(
        question_id=question_id,
        question=question,
        question_type=question_type,
        options=options,
        correct_answer=correct_answer,
        model_answer=model_answer,
        model_reasoning=model_reasoning,
        interleaved_text=interleaved_text,
        tool_calls=tool_calls,
        is_correct=is_correct,
        generation_time=datetime.now().isoformat()
    )

# 绑定方法
CureBenchAnswerer.answer_question = answer_question_with_prompt1


class CureBenchRunner(BaseRunner):
    """使用 prompt1 的运行器"""
    def __init__(self, *args, **kwargs):
        kwargs['prompt_version'] = 'prompt1'
        super().__init__(*args, **kwargs)
        # 替换为使用 prompt1 的 answerer
        self.answerer = CureBenchAnswerer(
            local_model_url=self.answerer.local_model_url,
            model_name=self.answerer.model_name
        )


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="使用本地模型 + MCP 工具回答 CureBench Testset 问题 (Prompt1)")
    _root = (Path(__file__).resolve().parent / ".." / "..").resolve()
    _default_data = str(_root / "训练和benchmark数据0120" / "curebench_testset_phase1.jsonl")
    _default_output = str(_root / "curebench_testset_results")
    parser.add_argument("--data-file", type=str, default=_default_data)
    parser.add_argument("--local-model-url", type=str, default="http://localhost:8000/v1")
    parser.add_argument("--model-name", type=str, default="Qwen3-8B")
    parser.add_argument("--instance-id", type=str, default=None)
    parser.add_argument("--output", type=str, default=_default_output)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    
    args = parser.parse_args()
    
    print(f"本地模型: {args.model_name}")
    print(f"API地址: {args.local_model_url}")
    print(f"数据文件: {args.data_file}")
    print(f"Prompt版本: prompt1")
    print(f"并发数: {args.concurrency}")
    if args.limit:
        print(f"限制: 前 {args.limit} 个问题")
    
    runner = CureBenchRunner(
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


if __name__ == "__main__":
    asyncio.run(main())
