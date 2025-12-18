# 使用本地Qwen3-8B生成轨迹

本文档说明如何使用本地Qwen3-8B模型从已有问题文件生成轨迹数据。

## 功能特点

- ✅ 从已有JSONL问题文件读取问题
- ✅ 调用本地部署的Qwen3-8B模型生成轨迹
- ✅ 复用现有的MCP server和工具（pubmed_search, browse_webpage, google_search）
- ✅ 复用现有的system prompt和轨迹格式
- ✅ **不生成rubrics**（仅生成轨迹）
- ✅ 支持并发生成和增量保存
- ✅ 自动重试失败的样本

## 前置要求

### 1. 本地模型部署

首先需要部署本地Qwen3-8B模型，提供OpenAI兼容的API接口。推荐使用vLLM：

```bash
# 使用vLLM部署Qwen3-8B（示例）
vllm serve Qwen/Qwen3-8B \
    --host 0.0.0.0 \
    --port 8000 \
    --api-key YOUR_API_KEY  # 可选
```

或者使用其他工具（如llama.cpp, Ollama等），只要提供OpenAI兼容的`/v1/chat/completions`接口即可。

### 2. MCP服务器

确保MCP服务器正在运行（与原来的生成脚本使用相同的MCP服务）：

```bash
# 检查MCP服务器状态
curl http://127.0.0.1:8003/mcp/health
```

### 3. Python环境

确保已安装必要的依赖：

```bash
pip install httpx fastmcp
```

## 使用方法

### 方法1：使用Shell脚本（推荐）

```bash
cd scripts/pubmed_data_generator

# 使用默认参数
bash run_local_model_generation.sh

# 自定义参数
bash run_local_model_generation.sh \
    path/to/questions.jsonl \
    http://localhost:8000/v1 \
    Qwen3-8B \
    5
```

参数说明：
1. 问题文件路径（默认：最新的questions文件）
2. 本地模型API地址（默认：http://localhost:8000/v1）
3. 模型名称（默认：Qwen3-8B）
4. 并发数（默认：5）

### 方法2：直接运行Python脚本

```bash
cd scripts/pubmed_data_generator

python generate_trajectory_from_questions.py \
    --questions-file ../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 5 \
    --output ../../pubmed_training_data
```

### 方法3：在服务器上运行（与原代码内容一致）

```bash
# 假设服务器上的模型部署在 http://localhost:8000/v1
cd /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator

python generate_trajectory_from_questions.py \
    --questions-file /path/to/questions.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 8 \
    --output /workspace/math_science_data/lyc/1205/dr-tulu/pubmed_training_data
```

## 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--questions-file` | 问题JSONL文件路径（必填） | - | `questions_*.jsonl` |
| `--local-model-url` | 本地模型API地址 | `http://localhost:8000/v1` | `http://10.0.0.1:8000/v1` |
| `--model-name` | 模型名称标识 | `Qwen3-8B` | `Qwen3-8B-Instruct` |
| `--output` | 输出目录 | `../../pubmed_training_data` | `/path/to/output` |
| `--concurrency` | 并发数 | `5` | `8` |
| `--limit` | 限制处理的问题数（测试用） | `None`（全部） | `10` |
| `--no-incremental` | 禁用增量保存 | 启用 | - |

## 输出文件

生成的文件会保存在`pubmed_training_data/`目录下：

1. **轨迹文件**（增量保存）：`pubmed_trajectory_YYYYMMDD_HHMMSS_Qwen3-8B_incremental.jsonl`
   - 每行一个JSON对象，包含问题、轨迹、metadata等

2. **统计文件**：`trajectory_stats_YYYYMMDD_HHMMSS_Qwen3-8B.json`
   - 生成统计信息：样本数、主题分布、平均工具调用次数等

## 输出格式

每条轨迹数据的JSON格式：

```json
{
  "sample_id": "qwen3_traj_00001",
  "question": "问题内容...",
  "topic": "主题分类",
  "question_type": "问题类型",
  "trajectory": {
    "question": "问题内容...",
    "interleaved_text": "<think>...</think>\n<call_tool>...</call_tool>\n<tool_output>...</tool_output>...",
    "tool_calls": [...],
    "final_answer": "最终答案...",
    "total_tool_calls": 3,
    "tools_used": ["pubmed_search", "browse_webpage"],
    "pmids_cited": ["12345678", "87654321"]
  },
  "metadata": {
    "expected_search_terms": [...],
    "tools_used": [...],
    "total_tool_calls": 3,
    "generation_time": "2025-12-17T...",
    "model": "Qwen3-8B",
    "source_file": "questions_*.jsonl"
  }
}
```

## 性能调优

### 并发数调整

- **CPU密集型场景**：并发数可以设置为 CPU核心数的1-2倍
- **网络/MCP限制**：根据MCP服务器负载能力调整（建议3-10）
- **本地模型限制**：根据模型推理速度和内存限制调整

### 内存优化

如果遇到内存不足：
1. 降低并发数（`--concurrency 3`）
2. 限制处理数量（`--limit 100`）
3. 确保增量保存已启用（避免内存积累）

## 测试运行

建议先用少量数据测试：

```bash
python generate_trajectory_from_questions.py \
    --questions-file questions.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 2 \
    --limit 5
```

## 与原始生成脚本的对比

| 特性 | 原始脚本 | 本脚本 |
|------|----------|--------|
| 问题来源 | 动态生成 | 从文件读取 |
| 模型 | OpenRouter API (GPT-5) | 本地Qwen3-8B |
| 轨迹生成 | ✅ | ✅ |
| Rubrics生成 | ✅ | ❌ |
| MCP工具 | ✅ | ✅ (复用) |
| System Prompt | ✅ | ✅ (复用) |
| 并发 | ✅ | ✅ |
| 增量保存 | ✅ | ✅ |

## 常见问题

### Q: 如何知道本地模型是否正常工作？

```bash
# 测试本地模型API
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-8B",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
```

### Q: 生成失败怎么办？

脚本有自动重试机制（最多3次）。如果仍然失败：
1. 检查MCP服务器状态
2. 检查本地模型API是否正常
3. 查看错误日志
4. 降低并发数
5. 已生成的样本会自动保存，可以断点续传

### Q: 如何使用不同的本地模型？

修改`--model-name`和`--local-model-url`参数即可，只要模型提供OpenAI兼容的API接口。

## 示例：完整工作流程

```bash
# 1. 启动MCP服务器（如果未运行）
# （根据你的MCP配置启动）

# 2. 部署本地Qwen3-8B模型
vllm serve Qwen/Qwen3-8B --port 8000

# 3. 运行轨迹生成
cd scripts/pubmed_data_generator
python generate_trajectory_from_questions.py \
    --questions-file ../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 5

# 4. 查看生成结果
ls -lh ../../pubmed_training_data/pubmed_trajectory_*_Qwen3-8B_*.jsonl
cat ../../pubmed_training_data/trajectory_stats_*_Qwen3-8B.json
```

## 技术细节

- **轨迹格式**：与原始GPT-5生成的格式完全一致（interleaved text）
- **工具执行**：使用相同的MCPToolExecutor
- **Prompt**：使用相同的SYSTEM_PROMPT
- **重试机制**：指数退避（2s, 4s, 6s）
- **超时设置**：180秒（可在代码中调整）

## 许可和引用

本脚本基于原始的`generate_trajectory_dataset.py`修改而来，保持了相同的架构和工具链。

