# 工具调用逻辑说明文档

本文档解释 `trajectory_generator.py` 中的工具调用相关逻辑，供后续开发者或 AI 理解。

## 1. 整体架构

```
用户问题 → GPT-5 生成响应 → 检测工具调用 → 执行 MCP 工具 → 返回结果给模型 → 循环直到获得答案
```

### 核心组件

| 组件 | 作用 |
|------|------|
| `SYSTEM_PROMPT` | 指导模型的行为规范和输出格式 |
| `MCPToolExecutor` | 执行实际的 MCP 工具调用 |
| `GPT5TrajectoryGenerator` | 主控制器，管理对话循环和轨迹生成 |

## 2. 期望的交互格式

### 模型应该输出的格式

```xml
<think>我的思考过程...</think>
<call_tool name="pubmed_search" limit="5">keyword1 keyword2 keyword3</call_tool>
```

然后**停止**，等待系统提供 `<tool_output>`。

### 系统提供的工具输出

```xml
<tool_output>
<snippet id="12345678">Title: Paper Title
Authors: Author1, Author2 | Year: 2023 | Journal: Nature
Abstract: Paper abstract content...</snippet>
</tool_output>
```

### 最终答案格式

```xml
<answer>
基于文献检索结果...
<cite id="12345678">引用内容 (Author et al., 2023, Nature).</cite>
</answer>
```

## 3. 核心问题与解决方案

### 问题 1: 模型生成未闭合的标签

**现象**：模型可能生成多个未闭合的 `<call_tool>` 标签：

```xml
<call_tool name="pubmed_search">query1
<call_tool name="pubmed_search">query2
<call_tool name="pubmed_search">query3
<answer>...
```

**解决方案**（第 345-359 行）：

```python
# 先尝试匹配闭合的标签
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
        # 只取第一个未闭合的调用
        first_match = unclosed_matches[0]
        tool_name = first_match[0]
        params_str = first_match[1]
        query = first_match[2].strip().split('\n')[0].strip()  # 取第一行作为 query
        tool_call_matches = [(tool_name, params_str, query)]
```

### 问题 2: 模型生成假的 tool_output（幻觉）

**现象**：模型在 `</call_tool>` 后自己编造 `<tool_output>` 内容：

```xml
<call_tool name="pubmed_search">query</call_tool><tool_output>
<snippet id="fake123">假的论文内容...</snippet>
</tool_output>
```

**解决方案**：

1. **Prompt 层面**：在 `SYSTEM_PROMPT` 中明确禁止
2. **Stop 序列**（第 439-445 行）：让模型在特定模式后停止
   ```python
   "stop": [
       "</call_tool>\n",   # 闭合标签后换行
       "</call_tool><",    # 闭合标签后直接跟其他标签
       "<tool_output>",    # 任何 tool_output
       "\n\n<call_tool",   # 防止多个 call_tool
   ],
   ```
3. **后处理清理**（`_remove_hallucinated_tool_output` 方法）：
   ```python
   def _remove_hallucinated_tool_output(self, content: str) -> str:
       # 移除 </call_tool> 后面的假 <tool_output>
       pattern = r'(</call_tool>)\s*<tool_output>.*?(?:</tool_output>|$)'
       cleaned = re.sub(pattern, r'\1', content, flags=re.DOTALL)
       
       # 移除任何残留的 <tool_output>
       if '<tool_output>' in cleaned:
           idx = cleaned.find('<tool_output>')
           cleaned = cleaned[:idx].rstrip()
       return cleaned
   ```

### 问题 3: 模型一次生成多个工具调用

**解决方案**：只执行第一个工具调用（第 370 行）：

```python
for tool_name, params_str, query in tool_call_matches[:1]:  # 只取第一个
```

## 4. `_clean_model_output` 方法详解

这个方法负责清理模型的原始输出，确保格式正确：

```python
def _clean_model_output(self, content: str, first_tool_call: tuple) -> str:
    tool_name, params_str, query = first_tool_call
    
    # 1. 构建正确格式的 call_tool 标签
    if params_str:
        call_tool_tag = f'<call_tool name="{tool_name}" {params_str}>{query}</call_tool>'
    else:
        call_tool_tag = f'<call_tool name="{tool_name}">{query}</call_tool>'
    
    # 2. 找到第一个 <call_tool 的位置
    first_call_idx = content.find('<call_tool')
    prefix = content[:first_call_idx]  # 保留 <think>...</think> 等前缀
    
    # 3. 检查是否有闭合标签
    close_tag_idx = content.find('</call_tool>', first_call_idx)
    if close_tag_idx != -1:
        # 有闭合标签，取到闭合标签为止
        clean_content = content[:close_tag_idx + len('</call_tool>')]
    else:
        # 没有闭合标签，手动构建正确格式
        clean_content = prefix + call_tool_tag
    
    # 4. 移除任何 tool_output
    clean_content = self._remove_hallucinated_tool_output(clean_content)
    
    return clean_content
```

## 5. 主循环流程（`generate_trajectory` 方法）

```
┌─────────────────────────────────────────────────────────────┐
│                     开始生成轨迹                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  调用 LLM，获取响应 content                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ content 包含     │
                    │ <answer>?       │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │ Yes                         │ No
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────────┐
    │ 提取最终答案     │           │ 检测 <call_tool>     │
    │ 结束循环        │           │ (闭合 或 未闭合)     │
    └─────────────────┘           └──────────┬──────────┘
                                             │
                                  ┌──────────┴──────────┐
                                  │ 有 call_tool?       │
                                  └──────────┬──────────┘
                                             │
                          ┌──────────────────┴──────────────────┐
                          │ Yes                                │ No
                          ▼                                    ▼
              ┌─────────────────────────┐         ┌────────────────────┐
              │ 1. _clean_model_output  │         │ 添加到轨迹          │
              │ 2. 执行第一个工具调用    │         │ 提示模型继续        │
              │ 3. 添加真实 tool_output │         │ 回到循环开始        │
              │ 4. 更新 messages       │         └────────────────────┘
              │ 5. 回到循环开始        │
              └─────────────────────────┘
```

## 6. MCP 工具执行（`MCPToolExecutor` 类）

### 支持的工具

| 工具名 | MCP 工具名 | 用途 |
|--------|-----------|------|
| `pubmed_search` | `pubmed_search` | 搜索 PubMed 文献 |
| `browse_webpage` | `crawl4ai_fetch_webpage_content` | 抓取网页内容 |
| `google_search` | `serper_google_webpage_search` | Google 搜索 |

### 工具输出格式化

`_format_tool_output` 方法将原始 MCP 结果格式化为 `<tool_output>` 格式：

```python
# pubmed_search 的输出格式
<tool_output>
Found 10 results. Showing top 5:
<snippet id="PMID">Title: Paper Title
Authors: Author1, Author2 et al. | Year: 2023 | Journal: Nature
Abstract: Full abstract content...</snippet>
...
</tool_output>
```

## 7. SYSTEM_PROMPT 关键约束

1. **搜索词数量**：3-6 个关键词（过多会导致 0 结果）
2. **标签格式**：必须正确闭合 `</call_tool>`
3. **一次一个调用**：禁止在一个响应中输出多个 `<call_tool>`
4. **禁止生成 tool_output**：只有系统能提供
5. **调用次数限制**：`pubmed_search` 最多 3 次

## 8. 数据结构

### ToolCallRecord

```python
@dataclass
class ToolCallRecord:
    tool_name: str      # 工具名称
    parameters: Dict    # 参数 (如 limit, offset)
    query: str          # 查询内容
    result: Any         # MCP 返回的结果
    timestamp: str      # 时间戳
```

### Trajectory

```python
@dataclass
class Trajectory:
    question: str           # 用户问题
    interleaved_text: str   # 完整的交互轨迹 (think + call_tool + tool_output + answer)
    tool_calls: List[ToolCallRecord]  # 所有工具调用记录
    final_answer: str       # 最终答案
    total_tool_calls: int   # 工具调用总次数
    tools_used: List[str]   # 使用的工具列表
    pmids_cited: List[str]  # 引用的 PMIDs
```

## 9. 常见问题排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| `tool_calls` 为空数组 | 模型未正确生成 `<call_tool>` 或标签未闭合 | 检查正则匹配逻辑 |
| PubMed 返回 0 结果 | 搜索词过长/过于具体 | 在 prompt 中限制关键词数量 |
| 轨迹中有假的 tool_output | 模型幻觉 | 检查 stop 序列和清理逻辑 |
| 模型不使用工具直接回答 | Prompt 不够强调工具使用 | 加强 SYSTEM_PROMPT |

## 10. 测试命令

```bash
# 在 open-instruct 环境中运行
cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 2 \
    --model openai/gpt-5.2
```

