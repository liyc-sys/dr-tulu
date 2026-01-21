# CureBench 评测工具

使用本地模型 + MCP 工具回答 CureBench 医学选择题。

## 功能

- 读取 CureBench JSONL 数据集
- 用本地模型（如 Qwen3-8B）结合 MCP 工具回答问题
  - **pubmed_search**: PubMed 文献检索
  - **browse_webpage**: 网页内容抓取
  - **google_search**: 通用网页搜索
  - **fda_drug_search**: FDA 药品说明书检索（新增）
- 自动提取模型答案，计算准确率
- 增量保存结果，支持中断续传
- 支持并发处理，提高效率

## 快速开始

### 1. 确保环境就绪

- 本地模型已启动（如 `http://localhost:8000/v1`）
- MCP 服务器已启动（默认 `127.0.0.1:8003`）
- 已安装依赖：`httpx`, `fastmcp`

### 2. 快速测试（前10个问题）

```bash
./run_curebench_test.sh
```

### 3. 运行完整评测

```bash
# 从项目根运行；--data-file / --output 不写则用默认（按脚本位置解析，任意工作目录均可）
python3 scripts/pubmed_data_generator/answer_curebench_with_tools.py \
    --data-file 训练和benchmark数据0120/curebench_valset_pharse1.jsonl \
    --output pubmed_training_data \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 3
```

用相对路径时，`--data-file`、`--output` 相对当前工作目录；**不传则使用默认路径（按脚本所在目录推算项目根，在服务器任意目录下都可运行）**。

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data-file` | 项目根/训练和benchmark数据0120/curebench_valset_pharse1.jsonl | CureBench 数据文件路径（按脚本位置推算） |
| `--local-model-url` | http://localhost:8000/v1 | 本地模型 API 地址（OpenAI 兼容） |
| `--model-name` | Qwen3-8B | 模型名称 |
| `--instance-id` | None | 实例标识（多端口时使用，如 port8000） |
| `--output` | 项目根/pubmed_training_data | 输出目录（按脚本位置推算） |
| `--concurrency` | 5 | 并发数 |
| `--limit` | None | 限制问题数量（测试用） |

## 输出文件

运行后会在输出目录生成两个文件：

1. **结果文件**：`curebench_results_YYYYMMDD_HHMMSS_modelname.jsonl`
   - 每行一个问题的完整结果
   - 包含：问题、选项、模型答案、正确答案、推理过程、工具调用轨迹等

2. **统计文件**：`curebench_stats_YYYYMMDD_HHMMSS_modelname.json`
   - 整体准确率
   - 按问题类型分组的准确率
   - 工具使用统计

## 结果格式示例

```json
{
  "question_id": "vIGwm8qguXYi",
  "question": "What should patients do if they experience severe allergic reactions...",
  "question_type": "open_ended_multi_choice",
  "options": {
    "A": "Wait for the symptoms to resolve on their own.",
    "B": "Inform their healthcare provider immediately...",
    "C": "Stop chemotherapy treatment permanently.",
    "D": "Take over-the-counter antihistamines."
  },
  "correct_answer": "B",
  "model_answer": "B",
  "model_reasoning": "Based on medical guidelines and PubMed literature...",
  "interleaved_text": "<think>...</think>\n<call_tool>...</call_tool>\n<tool_output>...</tool_output>\n<answer>...</answer>",
  "tool_calls": [...],
  "is_correct": true,
  "generation_time": "2024-01-20T10:30:45"
}
```

## 统计示例

```json
{
  "total_questions": 460,
  "correct": 368,
  "accuracy": 80.0,
  "by_question_type": {
    "multi_choice": {
      "total": 230,
      "correct": 190,
      "accuracy": 82.6
    },
    "open_ended_multi_choice": {
      "total": 230,
      "correct": 178,
      "accuracy": 77.4
    }
  },
  "tool_usage": {
    "total_tool_calls": 920,
    "avg_tool_calls_per_question": 2.0
  }
}
```

## 工具说明

### 可用工具

1. **pubmed_search**: PubMed 文献检索
   - 格式: `<call_tool name="pubmed_search" limit="5">keywords</call_tool>`
   - 用途: 检索医学文献和研究论文

2. **browse_webpage**: 网页内容抓取
   - 格式: `<call_tool name="browse_webpage">URL</call_tool>`
   - 用途: 获取网页完整内容

3. **google_search**: 通用网页搜索
   - 格式: `<call_tool name="google_search">query</call_tool>`
   - 用途: 搜索相关网页信息

4. **fda_drug_search**: FDA 药品说明书检索（新增）
   - 格式: `<call_tool name="fda_drug_search" focus="aspect">drug_name</call_tool>`
   - 用途: 从 FDA 官方药品标签中检索特定信息
   - focus 参数示例:
     - `"adverse reactions"` - 不良反应
     - `"indications and usage"` - 适应症和用法
     - `"dosage"` - 剂量
     - `"warnings"` - 警告
     - `"contraindications"` - 禁忌症

### 工具使用示例

```xml
<!-- 检索药物不良反应 -->
<call_tool name="fda_drug_search" focus="adverse reactions">aspirin</call_tool>

<!-- 检索药物适应症 -->
<call_tool name="fda_drug_search" focus="indications and usage">metformin</call_tool>

<!-- 检索用药剂量 -->
<call_tool name="fda_drug_search" focus="dosage and administration">ibuprofen</call_tool>
```

## 注意事项

1. **并发控制**：建议并发数不超过5，避免本地模型负载过高
2. **工具限制**：每个问题最多调用5次工具（包括所有工具类型）
3. **增量保存**：每完成一个问题就保存，Ctrl+C 中断后不会丢失已完成的结果
4. **重试机制**：失败问题会自动重试3次
5. **答案格式**：模型必须输出 `<answer><choice>X</choice></answer>` 格式
6. **FDA 工具**：需要 MCP 服务器启用 FDA 工具，并设置 `OPENROUTER_API_KEY` 环境变量

## 多实例运行

如果要用多个端口同时运行（提高吞吐量）：

```bash
# 实例1 (端口8000，处理前100个)
python3 answer_curebench_with_tools.py \
    --local-model-url http://localhost:8000/v1 \
    --instance-id port8000 \
    --limit 100

# 实例2 (端口8001，处理101-200)
python3 answer_curebench_with_tools.py \
    --local-model-url http://localhost:8001/v1 \
    --instance-id port8001 \
    --limit 100
```

## 故障排查

### 问题：本地模型无响应
- 检查模型服务是否启动：`curl http://localhost:8000/v1/models`
- 查看模型日志

### 问题：MCP 工具调用失败
- 检查 MCP 服务器：`curl http://127.0.0.1:8003/mcp`
- 确认环境变量：`MCP_TRANSPORT_HOST`, `MCP_TRANSPORT_PORT`

### 问题：模型不输出正确格式
- 检查 system prompt 是否正确传递
- 降低温度参数（当前 0.1）
- 检查模型输出日志
