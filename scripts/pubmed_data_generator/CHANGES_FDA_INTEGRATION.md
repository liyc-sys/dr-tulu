# FDA 工具集成 - 修改总结

## 修改日期
2025-01-20

## 修改概述

在 `answer_curebench_with_tools.py` 中添加了 FDA Drug Label Search 工具的支持，允许模型在回答 CureBench 医学选择题时查询 FDA 官方药品说明书信息。

## 修改文件列表

### 1. 核心文件修改

#### `answer_curebench_with_tools.py`

**修改内容：**

1. **添加工具映射** (第 132-137 行)
   ```python
   TOOL_MAPPING = {
       "pubmed_search": "pubmed_search",
       "browse_webpage": "crawl4ai_docker_fetch_webpage_content",
       "google_search": "serper_google_webpage_search",
       "fda_drug_search": "fda_drug_label_search",  # 新增
   }
   ```

2. **更新 System Prompt** (第 29-48 行)
   - 添加了 FDA 工具的使用说明
   - 添加了 focus 参数说明和示例
   - 更新了工具调用上限说明（4个工具）

3. **新增自定义工具执行方法** (第 197-264 行)
   - `_execute_tool_with_mapping()`: 使用自定义映射执行工具
   - 特殊处理 FDA 工具的参数格式（keyword + focus）
   - 直接调用 MCP Client，不依赖 trajectory_generator 的 MCPToolExecutor

4. **新增工具输出格式化** (第 266-322 行)
   - `_format_tool_output()`: 格式化各工具的输出
   - 为 FDA 工具添加专门的格式化逻辑
   - 提取并展示 extracted_info 和 search_strategy

5. **修改工具调用逻辑** (第 342 行)
   - 将 `self.tool_executor.execute_tool()` 改为 `self._execute_tool_with_mapping()`
   - 使用自定义映射和参数处理

### 2. 文档更新

#### `CUREBENCH_README.md`

**添加内容：**
- 工具列表中添加 FDA 工具说明
- 添加"工具说明"章节，详细说明每个工具的用法
- 添加 FDA 工具使用示例
- 在注意事项中添加 FDA 工具的依赖说明

### 3. 新增文件

#### `FDA_TOOL_INTEGRATION.md`
- 详细的 FDA 工具集成文档
- 使用方法和示例
- 技术实现细节
- 未来扩展指南

#### `test_fda_curebench.py`
- FDA 工具映射的测试脚本
- 验证工具调用和输出格式
- 使用示例代码

#### `CHANGES_FDA_INTEGRATION.md` (本文件)
- 修改总结和说明

## 关键技术点

### 1. 自定义映射 vs trajectory_generator 的映射

**为什么不修改 trajectory_generator？**
- `trajectory_generator` 是通用的轨迹生成模块，被多个脚本共享
- `answer_curebench_with_tools.py` 有特定需求（CureBench 评测场景）
- 通过在 CureBenchAnswerer 中实现自定义映射，可以独立扩展工具集

**实现方式：**
```python
# 类级别的工具映射
TOOL_MAPPING = {
    "logical_name": "mcp_tool_name",
    ...
}

# 自定义执行方法
async def _execute_tool_with_mapping(self, tool_name, parameters, query):
    mcp_tool_name = self.TOOL_MAPPING.get(tool_name, tool_name)
    # 特殊参数处理
    # MCP 调用
    # 输出格式化
```

### 2. FDA 工具的特殊处理

**参数映射：**
```python
# 输入格式（模型生成）
<call_tool name="fda_drug_search" focus="adverse reactions">aspirin</call_tool>

# MCP 参数（代码转换）
{
    "keyword": "aspirin",
    "focus": "adverse reactions",
    "limit": 3,
    "use_llm_extraction": True
}
```

**输出格式化：**
- 提取 `extracted_info` 列表
- 显示 `search_strategy`（BRAND_NAME / GENERIC_NAME / FINDALL_NAME）
- 格式化为易读的文本

### 3. System Prompt 设计

**引导模型正确使用 FDA 工具：**
1. 明确说明工具用途和格式
2. 提供具体使用示例
3. 强调 focus 参数的重要性
4. 在示例中展示何时使用 FDA 工具 vs PubMed

## 使用方法

### 前置条件

1. **MCP 服务器运行**
   ```bash
   cd /Users/liyc/Desktop/dr-tulu/agent
   export OPENROUTER_API_KEY="your-key-here"
   uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
   ```

2. **本地模型运行**
   ```bash
   CUDA_VISIBLE_DEVICES=6 vllm serve /path/to/model --port 8006 --max-model-len 40960
   ```

### 运行评测

```bash
# 在项目根目录
python3 scripts/pubmed_data_generator/answer_curebench_with_tools.py \
    --local-model-url http://localhost:8006/v1 \
    --model-name 8B_DPO_run1_epoch0 \
    --instance-id port8006 \
    --concurrency 3 \
    --limit 10
```

### 测试 FDA 工具

```bash
python3 scripts/pubmed_data_generator/test_fda_curebench.py
```

## 验证方法

### 1. 检查工具映射

```python
from answer_curebench_with_tools import CureBenchAnswerer
answerer = CureBenchAnswerer()
print(answerer.TOOL_MAPPING)
# 应该看到: {'pubmed_search': ..., 'fda_drug_search': 'fda_drug_label_search', ...}
```

### 2. 运行测试脚本

```bash
python3 scripts/pubmed_data_generator/test_fda_curebench.py
```

应该看到：
- 工具映射表
- FDA 工具调用成功
- 格式化的输出（包含 extracted_info）

### 3. 检查实际评测日志

运行评测时，如果模型调用 FDA 工具，应该看到：
```
执行工具: fda_drug_search(aspirin)
```

输出应该包含：
```xml
<tool_output>
FDA Drug Label Search Results for 'aspirin' (Focus: adverse reactions)
Search Strategy: BRAND_NAME

Extracted Information:
- ...
- ...
</tool_output>
```

## 已知限制

1. **MCP 服务器依赖**
   - 必须运行在 `127.0.0.1:8003`
   - 需要设置 `OPENROUTER_API_KEY` 环境变量

2. **工具调用上限**
   - 总共最多 5 次工具调用（所有工具累计）
   - 需要模型合理规划工具使用

3. **FDA 数据覆盖**
   - 依赖 FDA 数据库的覆盖范围
   - 某些药物可能没有 FDA 标签数据

## 未来改进建议

1. **添加更多医疗工具**
   - ClinicalTrials.gov 临床试验信息
   - 药物专利信息
   - 药物相互作用数据库

2. **优化工具选择**
   - 根据问题类型自动推荐最佳工具
   - 实现工具链（多工具协同）

3. **提升 FDA 工具效果**
   - 优化 focus 参数的自动识别
   - 改进 LLM 提取的准确性
   - 添加缓存机制

## 相关文档

- `FDA_TOOL_INTEGRATION.md` - 详细集成文档
- `CUREBENCH_README.md` - CureBench 评测工具使用指南
- `FDA_TOOL_USAGE.md` - FDA 工具原始使用文档

## 联系方式

如有问题，请参考：
- 项目根目录的 `FDA_TOOL_USAGE.md`
- Agent 目录的 FDA API 实现 (`agent/dr_agent/mcp_backend/apis/fda_apis.py`)
