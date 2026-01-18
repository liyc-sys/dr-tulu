# FDA Drug Label Search Tool - 使用指南

## 概述

FDA Drug Label Search Tool 是一个用于从 FDA 药物标签数据库检索药物信息的 MCP 工具。它使用三级搜索策略，并可选择使用 LLM 提取相关信息。

## 功能特点

### 1. 三级搜索策略
- **品牌名搜索** (BRAND_NAME): 最精确的搜索
- **通用名搜索** (GENERIC_NAME): 次选搜索策略
- **全文搜索** (FINDALL_NAME): 回退搜索策略

### 2. LLM 智能提取
- 使用 OpenRouter API (bytedance-seed/seed-1.6 模型)
- 根据指定的关注点提取相关信息
- 自动重试机制，提高稳定性

### 3. 灵活的使用方式
- 直接调用 API
- 通过 MCP Tool Interface
- 在训练脚本中使用

## 文件结构

```
agent/dr_agent/mcp_backend/
├── apis/
│   └── fda_apis.py                    # FDA API 实现
└── main.py                             # MCP Server (已添加 fda_drug_label_search 工具)

agent/dr_agent/tool_interface/
├── mcp_tools.py                        # 工具类 (已添加 FDADrugLabelSearchTool)
└── __init__.py                         # 导出 (已添加 FDADrugLabelSearchTool)

rl/open-instruct/open_instruct/search_utils/
└── mcp_tools.py                        # 工具注册表 (已添加 fda_drug_search)
```

## 使用方法

### 方法 1: 直接调用 FDA API

```python
from agent.dr_agent.mcp_backend.apis.fda_apis import search_fda_drug_label

# 搜索药物信息（使用 LLM 提取）
result = search_fda_drug_label(
    keyword="aspirin",
    focus="adverse reactions",  # 关注点
    limit=3,                    # 返回结果数量
    use_llm_extraction=True     # 使用 LLM 提取
)

print(f"搜索策略: {result['search_strategy']}")
print(f"提取的信息: {result['extracted_info']}")
```

### 方法 2: 通过 MCP Server 使用

#### 启动 MCP Server

```bash
cd /path/to/dr-tulu/agent

# 设置环境变量
export OPENROUTER_API_KEY="your-api-key-here"

# 启动 MCP Server
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

#### 调用工具

```python
from fastmcp import Client

async def search_fda():
    client = Client("http://localhost:8003/mcp", timeout=180)
    
    async with client:
        result = await client.call_tool(
            "fda_drug_label_search",
            {
                "keyword": "metformin",
                "focus": "indications and usage",
                "limit": 3,
                "use_llm_extraction": True
            }
        )
        
        # 处理结果
        data = result.content[0].text
        print(data)
```

### 方法 3: 在训练脚本中使用

在训练脚本中添加 FDA 工具：

```bash
--tools mcp \
--mcp_tool_names 'snippet_search,google_search,browse_webpage,fda_drug_search' \
--max_tool_calls 10
```

训练时模型可以这样调用工具：

```xml
<tool name="fda_drug_search">
<parameter name="focus">adverse reactions</parameter>
metformin
</tool>
```

## 参数说明

### `fda_drug_label_search` 工具参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `keyword` | str | ✅ | - | 药物名称或关键词 |
| `focus` | str | ✅ | - | 关注点（如 "adverse reactions", "indications", "dosage"） |
| `limit` | int | ❌ | 3 | 返回结果数量 |
| `use_llm_extraction` | bool | ❌ | True | 是否使用 LLM 提取相关信息 |

### 常用的 `focus` 参数值

- `"adverse reactions"` - 副作用
- `"indications and usage"` - 适应症和用法
- `"dosage and administration"` - 剂量和给药方法
- `"warnings and precautions"` - 警告和注意事项
- `"drug interactions"` - 药物相互作用
- `"contraindications"` - 禁忌症
- `"overdosage"` - 过量用药
- `"clinical pharmacology"` - 临床药理学

## 环境变量

### 必需的环境变量

```bash
# OpenRouter API Key (用于 LLM 提取功能)
export OPENROUTER_API_KEY="sk-or-v1-xxxxx"
```

### 可选的环境变量

```bash
# MCP Server 配置
export MCP_TRANSPORT="StreamableHttpTransport"
export MCP_TRANSPORT_PORT="8003"
export MCP_TRANSPORT_HOST="0.0.0.0"
```

## 返回数据格式

### API 直接调用返回格式

```python
{
    "keyword": "aspirin",                    # 搜索的药物名称
    "focus": "adverse reactions",            # 关注点
    "search_strategy": "BRAND_NAME",         # 使用的搜索策略
    "extracted_info": [                      # 提取的信息列表
        "Aspirin may cause stomach bleeding...",
        "Common side effects include..."
    ],
    "data": [...],                           # 原始/处理后的数据
    "error": None                            # 错误信息（如果有）
}
```

### MCP Tool Interface 返回格式

```python
DocumentToolOutput(
    tool_name="fda_drug_search",
    output="<snippet>...",                   # 格式化的输出
    called=True,
    error="",
    timeout=False,
    runtime=2.5,
    documents=[                              # Document 对象列表
        Document(
            title="aspirin - adverse reactions",
            snippet="...",
            url="https://api.fda.gov/drug/label.json",
            text="...",
            score=1.0
        )
    ]
)
```

## 测试

运行测试脚本：

```bash
cd /path/to/dr-tulu

# 设置 API Key
export OPENROUTER_API_KEY="your-api-key"

# 运行测试
python test_fda_tool.py
```

## 注意事项

1. **API Key**: 使用 LLM 提取功能需要设置 `OPENROUTER_API_KEY` 环境变量
2. **超时设置**: FDA API 和 LLM 调用可能需要较长时间，建议设置 180 秒超时
3. **速率限制**: FDA API 有速率限制，工具内置了重试机制
4. **数据质量**: LLM 提取的信息质量取决于：
   - 原始 FDA 数据的完整性
   - `focus` 参数的准确性
   - LLM 模型的能力

## 示例

### 示例 1: 搜索药物副作用

```python
result = search_fda_drug_label(
    keyword="ibuprofen",
    focus="adverse reactions and side effects",
    limit=2,
    use_llm_extraction=True
)
```

### 示例 2: 搜索药物相互作用

```python
result = search_fda_drug_label(
    keyword="warfarin",
    focus="drug interactions",
    limit=3,
    use_llm_extraction=True
)
```

### 示例 3: 搜索用药剂量

```python
result = search_fda_drug_label(
    keyword="metformin",
    focus="dosage and administration",
    limit=1,
    use_llm_extraction=True
)
```

## 故障排除

### 问题 1: "OPENROUTER_API_KEY 环境变量未设置"

**解决方法**:
```bash
export OPENROUTER_API_KEY="your-api-key"
```

### 问题 2: "No FDA data found for drug: xxx"

**可能原因**:
- 药物名称拼写错误
- FDA 数据库中没有该药物
- 网络连接问题

**解决方法**:
- 检查药物名称拼写
- 尝试使用通用名或品牌名
- 检查网络连接

### 问题 3: MCP Server 连接失败

**解决方法**:
```bash
# 检查 server 是否运行
netstat -tlnp | grep 8003

# 如果没有运行，启动 server
cd agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

## 性能优化建议

1. **批量查询**: 如果需要查询多个药物，考虑并发请求
2. **缓存结果**: 对于相同的查询，可以缓存结果避免重复调用
3. **调整 limit**: 根据需求调整 `limit` 参数，避免获取过多数据
4. **选择性使用 LLM**: 如果不需要精确提取，设置 `use_llm_extraction=False` 可以大幅提升速度

## 更多信息

- FDA Drug Label API 文档: https://open.fda.gov/apis/drug/label/
- OpenRouter API 文档: https://openrouter.ai/docs

