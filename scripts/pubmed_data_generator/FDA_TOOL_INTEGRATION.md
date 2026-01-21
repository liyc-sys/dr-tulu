# FDA 工具集成到 CureBench 评测

## 概述

已将 FDA Drug Label Search 工具集成到 `answer_curebench_with_tools.py` 中，允许本地模型在回答 CureBench 医学选择题时使用 FDA 药品说明书检索功能。

## 新增功能

### 1. 工具映射

在 `CureBenchAnswerer` 类中添加了自定义工具映射：

```python
TOOL_MAPPING = {
    "pubmed_search": "pubmed_search",
    "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
    "google_search": "serper_google_webpage_search",
    "fda_drug_search": "fda_drug_label_search",  # 新增
}
```

### 2. 工具使用方式

模型可以通过以下格式调用 FDA 工具：

```xml
<call_tool name="fda_drug_search" focus="adverse reactions">aspirin</call_tool>
<call_tool name="fda_drug_search" focus="indications and usage">metformin</call_tool>
<call_tool name="fda_drug_search" focus="dosage">ibuprofen</call_tool>
```

**参数说明：**
- `focus`: 关注的方面（必需）
  - "adverse reactions" - 不良反应
  - "indications" / "indications and usage" - 适应症和用法
  - "dosage" / "dosage and administration" - 剂量和用药方法
  - "warnings" / "warnings and precautions" - 警告和注意事项
  - "contraindications" - 禁忌症
  - 其他任何与药物相关的关键词

- 工具名后的文本：药物名称（可以是品牌名或通用名）

### 3. System Prompt 更新

更新了 `CUREBENCH_SYSTEM_PROMPT`，添加了 FDA 工具的使用说明和示例，指导模型在处理药物相关问题时优先使用 FDA 工具。

## 使用方法

### 运行评测（带 FDA 工具）

```bash
# 测试 10 个问题
python3 scripts/pubmed_data_generator/answer_curebench_with_tools.py \
    --data-file 训练和benchmark数据0120/curebench_valset_pharse1.jsonl \
    --local-model-url http://localhost:8006/v1 \
    --model-name 8B_DPO_run1_epoch0 \
    --instance-id port8006 \
    --concurrency 3 \
    --limit 10
```

### 测试 FDA 工具映射

```bash
# 需要先启动 MCP 服务器
cd /Users/liyc/Desktop/dr-tulu/agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp

# 运行测试
python3 scripts/pubmed_data_generator/test_fda_curebench.py
```

## 工具输出格式

FDA 工具返回格式化的输出，包含：

```xml
<tool_output>
FDA Drug Label Search Results for 'aspirin' (Focus: adverse reactions)
Search Strategy: BRAND_NAME

Extracted Information:
- Gastrointestinal bleeding and ulceration
- Increased risk of cardiovascular thrombotic events
- Hypersensitivity reactions including anaphylaxis
- Hepatotoxicity with chronic use
</tool_output>
```

## 典型使用场景

### 场景 1: 药物不良反应

**问题**: What should patients do if they experience severe allergic reactions while taking PERTZYE?

**模型行为**:
1. 识别这是关于药物不良反应的问题
2. 调用 `<call_tool name="fda_drug_search" focus="adverse reactions">PERTZYE</call_tool>`
3. 根据 FDA 标签信息回答

### 场景 2: 药物禁忌症

**问题**: Which of the following conditions is a contraindication for the use of Gadavist?

**模型行为**:
1. 识别这是关于药物禁忌症的问题
2. 调用 `<call_tool name="fda_drug_search" focus="contraindications">Gadavist</call_tool>`
3. 根据 FDA 标签信息选择答案

### 场景 3: 用药指导

**问题**: What is the recommended action if a patient's serum potassium level reaches 6.0 mEq/L while on Inspra therapy?

**模型行为**:
1. 识别这是关于用药剂量调整的问题
2. 调用 `<call_tool name="fda_drug_search" focus="dosage and administration">Inspra</call_tool>`
3. 根据 FDA 标签中的剂量调整指南回答

## 注意事项

1. **工具调用上限**: 总共最多 5 次工具调用（包括 pubmed_search、browse_webpage、google_search、fda_drug_search）
2. **Focus 参数重要性**: focus 参数决定了从 FDA 标签中提取哪方面的信息，应根据问题类型选择合适的 focus
3. **药物名称**: 支持品牌名和通用名，工具会自动尝试三级搜索策略（品牌名 → 通用名 → 全文搜索）
4. **MCP 服务器依赖**: 需要 MCP 服务器运行在 `127.0.0.1:8003`，并且环境变量中需要设置 `OPENROUTER_API_KEY`（用于 LLM 提取）

## 技术细节

### 工具执行流程

1. 模型生成包含 `<call_tool name="fda_drug_search" focus="...">drug_name</call_tool>` 的响应
2. `CureBenchAnswerer` 解析工具调用，提取 `tool_name`、`focus` 参数和 `query`（药物名）
3. `_execute_tool_with_mapping` 方法：
   - 查找工具映射：`fda_drug_search` → `fda_drug_label_search`
   - 构建 MCP 参数：
     ```python
     {
         "keyword": "drug_name",
         "focus": "adverse reactions",
         "limit": 3,
         "use_llm_extraction": True
     }
     ```
   - 调用 MCP 工具
4. `_format_tool_output` 格式化 FDA 工具的返回结果
5. 将 `<tool_output>` 返回给模型继续生成

### 自定义映射实现

不同于 `trajectory_generator.py` 中硬编码的映射，`answer_curebench_with_tools.py` 实现了：

1. **类级别的工具映射表** (`TOOL_MAPPING`)
2. **自定义工具执行方法** (`_execute_tool_with_mapping`)
3. **特殊参数处理**（FDA 工具需要 `keyword` + `focus`，而不是简单的 `query`）

这种设计允许在不修改 `trajectory_generator` 的情况下，为特定场景添加新工具。

## 未来扩展

可以按照同样的方式添加其他 MCP 工具：

1. 在 `TOOL_MAPPING` 中添加映射
2. 在 `CUREBENCH_SYSTEM_PROMPT` 中添加工具说明
3. 在 `_execute_tool_with_mapping` 中添加参数处理逻辑（如果需要）
4. 在 `_format_tool_output` 中添加输出格式化逻辑（如果需要）

例如：
- `medbrowsecomp_search` - 临床试验信息
- `get_drug_patents` - 药物专利信息
- `semantic_scholar_search` - 学术论文检索
