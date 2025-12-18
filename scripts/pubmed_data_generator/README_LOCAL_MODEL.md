# 本地Qwen3-8B模型轨迹生成 - 快速开始

本目录包含使用本地Qwen3-8B模型从已有问题文件生成轨迹的完整实现。

## 新增文件

1. **`generate_trajectory_from_questions.py`** - 主脚本
   - 从JSONL文件读取问题
   - 调用本地Qwen3-8B模型生成轨迹
   - 复用现有MCP server和prompt
   - 不生成rubrics

2. **`run_local_model_generation.sh`** - 快速运行脚本
   - 简化命令行参数
   - 适合快速测试和生产使用

3. **`test_local_generation.py`** - 测试脚本
   - 测试本地模型连接
   - 使用示例问题验证功能

4. **`LOCAL_MODEL_USAGE.md`** - 详细文档
   - 完整使用说明
   - 参数说明
   - 常见问题解答

5. **`README_LOCAL_MODEL.md`** - 本文件

## 快速开始

### 步骤1: 部署本地模型

使用vLLM部署Qwen3-8B（服务器上）：

```bash
# 安装vLLM（如果未安装）
pip install vllm

# 启动模型服务
vllm serve Qwen/Qwen3-8B \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1
```

### 步骤2: 确认MCP服务器运行

```bash
# 检查MCP服务器状态
curl http://127.0.0.1:8003/mcp/health
```

### 步骤3: 运行轨迹生成

**方式A：使用Shell脚本（最简单）**

```bash
cd scripts/pubmed_data_generator

# 使用默认参数（本地环境）
bash run_local_model_generation.sh

# 自定义参数
bash run_local_model_generation.sh \
    /path/to/questions.jsonl \
    http://localhost:8000/v1 \
    Qwen3-8B \
    8
```

**方式B：使用Python脚本（更灵活）**

```bash
cd scripts/pubmed_data_generator

python generate_trajectory_from_questions.py \
    --questions-file ../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 8
```

**服务器上运行（与本地代码内容一致）**

```bash
# 假设在服务器 /workspace/math_science_data/lyc/1205/dr-tulu
cd scripts/pubmed_data_generator

uv run python generate_trajectory_from_questions.py \
    --questions-file ../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl \
    --local-model-url http://localhost:8000/v1 \
    --model-name Qwen3-8B \
    --concurrency 8 \
    --output ../../pubmed_training_data
```

## 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--questions-file` | ✅ | - | 问题JSONL文件路径 |
| `--local-model-url` | ❌ | `http://localhost:8000/v1` | 本地模型API地址 |
| `--model-name` | ❌ | `Qwen3-8B` | 模型名称 |
| `--concurrency` | ❌ | `5` | 并发数 |
| `--output` | ❌ | `../../pubmed_training_data` | 输出目录 |
| `--limit` | ❌ | `None` | 限制处理的问题数（测试用） |

## 输出文件

生成的文件保存在`pubmed_training_data/`目录：

- **轨迹数据**：`pubmed_trajectory_YYYYMMDD_HHMMSS_Qwen3-8B_incremental.jsonl`
- **统计信息**：`trajectory_stats_YYYYMMDD_HHMMSS_Qwen3-8B.json`

## 测试

运行测试脚本验证功能：

```bash
cd scripts/pubmed_data_generator
python test_local_generation.py
```

这会：
1. 测试本地模型连接
2. 使用2个示例问题生成轨迹
3. 显示生成结果

## 技术特点

✅ **复用现有组件**
- MCP工具执行器（`MCPToolExecutor`）
- 系统提示词（`SYSTEM_PROMPT`）
- 轨迹格式（interleaved text）

✅ **与原始脚本兼容**
- 生成的轨迹格式完全一致
- 可以与原始数据混合使用

✅ **生产级特性**
- 并发处理
- 增量保存
- 自动重试（3次，指数退避）
- 错误处理和日志

❌ **不生成rubrics**
- 专注于轨迹生成
- 更快的生成速度
- 更低的成本

## 与原始脚本对比

| 特性 | `generate_trajectory_dataset.py` | `generate_trajectory_from_questions.py` |
|------|----------------------------------|----------------------------------------|
| 问题来源 | 动态生成 | 从文件读取 |
| 模型 | OpenRouter API (GPT-5) | 本地Qwen3-8B |
| 轨迹生成 | ✅ | ✅ |
| Rubrics生成 | ✅ (可选) | ❌ |
| MCP工具 | ✅ | ✅ (复用) |
| Prompt | ✅ | ✅ (复用) |

## 常见问题

### Q: 如何验证本地模型是否正常？

```bash
# 查看可用模型
curl http://localhost:8000/v1/models

# 测试生成
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-8B",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

### Q: 生成失败怎么办？

1. 检查MCP服务器：`curl http://127.0.0.1:8003/mcp/health`
2. 检查本地模型：使用上面的curl命令测试
3. 查看错误日志
4. 降低并发数：`--concurrency 2`
5. 已生成的样本会自动保存，无需重新开始

### Q: 如何限制只生成部分问题？

使用`--limit`参数：

```bash
python generate_trajectory_from_questions.py \
    --questions-file questions.jsonl \
    --limit 10  # 只处理前10个问题
```

### Q: 可以使用其他本地模型吗？

可以！只要模型提供OpenAI兼容的API接口，修改`--model-name`和`--local-model-url`即可。

## 性能建议

- **并发数**：根据模型推理速度和内存调整，建议5-10
- **内存优化**：如遇内存问题，降低并发数或使用`--limit`
- **网络延迟**：如果MCP服务器在远程，降低并发数

## 相关文档

- 详细使用指南：[LOCAL_MODEL_USAGE.md](./LOCAL_MODEL_USAGE.md)
- 原始脚本文档：[README.md](./README.md)
- 并发使用说明：[CONCURRENT_USAGE.md](./CONCURRENT_USAGE.md)

## 示例工作流

```bash
# 1. 启动本地模型（服务器）
vllm serve Qwen/Qwen3-8B --port 8000

# 2. 确认MCP服务器运行
curl http://127.0.0.1:8003/mcp/health

# 3. 测试功能（可选）
python test_local_generation.py

# 4. 生成轨迹
bash run_local_model_generation.sh \
    ../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl \
    http://localhost:8000/v1 \
    Qwen3-8B \
    8

# 5. 查看结果
ls -lh ../../pubmed_training_data/pubmed_trajectory_*_Qwen3-8B_*.jsonl
```

## 贡献者

基于原始的`generate_trajectory_dataset.py`修改而来，保持了相同的架构和工具链。

## 许可

与dr-tulu项目保持一致。

