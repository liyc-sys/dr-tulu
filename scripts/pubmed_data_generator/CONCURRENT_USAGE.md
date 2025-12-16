# 并发数据生成使用指南

## 概述

`generate_trajectory_dataset.py` 现在支持并发生成，可以显著提高大批量数据生成的速度。

## 基本用法

### 1. 小规模测试（1-5条，串行）

```bash
cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct

uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 1 \
    --model openai/gpt-5.2 \
    --concurrency 1
```

### 2. 中等规模生成（20-50条，并发 5）

```bash
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 50 \
    --model openai/gpt-5.2 \
    --concurrency 5
```

### 3. 大批量生成（200条，并发 8）

```bash
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 200 \
    --model openai/gpt-5.2 \
    --concurrency 8
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--model` | `openai/gpt-4o` | 主模型（轨迹生成） |
| `--mini-model` | `openai/gpt-5-mini` | 次要模型（问题/rubrics 生成） |
| `--num-questions` | 5 | 生成问题数量 |
| `--language` | `zh` | 语言（zh/en） |
| `--concurrency` | 5 | **并发数（重要！）** |
| `--output` | `../../pubmed_training_data` | 输出目录 |
| `--no-incremental` | 否 | **禁用增量保存（默认启用）** |

## 并发数选择建议

| 场景 | 推荐并发数 | 原因 |
|------|-----------|------|
| **测试** | 1-2 | 便于调试，查看详细日志 |
| **小规模（<50条）** | 3-5 | 平衡速度和稳定性 |
| **中规模（50-100条）** | 5-8 | 较好的并发效率 |
| **大规模（100-300条）** | 8-10 | 最大化吞吐量 |

### 注意事项

1. **MCP 服务器负载**：
   - 并发过高可能导致 MCP 服务器超载
   - 如果看到大量工具调用失败，降低并发数

2. **API 限流**：
   - OpenRouter API 有速率限制
   - gpt-5.2: 通常支持较高并发
   - 如遇到 429 错误，降低并发数或添加延迟

3. **内存使用**：
   - 每个并发任务会占用一定内存
   - 200条 × 并发8 = 约 2-4GB 内存

## 功能特性

### 1. 增量保存（默认启用）⭐ NEW

**两个阶段的增量保存**，无需等待全部完成：

```bash
# 启用增量保存（默认）
uv run python .../generate_trajectory_dataset.py \
    --num-questions 200 \
    --concurrency 8

# 禁用增量保存（仅在最后保存）
uv run python .../generate_trajectory_dataset.py \
    --num-questions 200 \
    --concurrency 8 \
    --no-incremental
```

**阶段 1: 问题生成（按主题批量保存）**
```
💾 问题增量保存已启用: questions_20251216_143022_incremental.jsonl
主题 [1/15]: Cardiovascular Diseases
  ✓ 生成了 14 个问题
...
```
- 每生成一批问题（按主题）立即追加到文件
- 可以在轨迹生成前检查问题质量
- 格式：每行一个 JSON 对象（包含 question, topic, question_type）

**阶段 2: 轨迹生成（逐条保存）**
```
💾 增量保存已启用: pubmed_trajectory_20251216_143022_incremental.jsonl
📊 进度: 1/200 (0.5%) | 成功: 1 | 失败: 0 | 成功率: 100.0%
📊 进度: 2/200 (1.0%) | 成功: 2 | 失败: 0 | 成功率: 100.0%
...
```
- 每生成 1 条轨迹数据立即保存

**优势**：
- ✅ **最安全**：即使程序异常退出，已生成的数据不会丢失
- ✅ **可实时查看**：随时打开 `.jsonl` 文件查看进度
- ✅ **可中断恢复**：Ctrl+C 后已保存的数据完整可用
- ✅ **节省内存**：不需要在内存中累积所有样本
- ✅ **问题质量审查**：可以在轨迹生成前查看问题文件，决定是否继续

### 2. 自动重试

每个任务失败后会自动重试最多 3 次，指数退避：
- 第 1 次失败：等待 2 秒
- 第 2 次失败：等待 4 秒
- 第 3 次失败：标记为失败

### 3. 进度显示

实时显示：
```
📊 进度: 45/200 (22.5%) | 成功: 42 | 失败: 3 | 成功率: 93.3%
```

### 4. 异常恢复

- **Ctrl+C 中断**：已生成的样本已通过增量保存写入文件
- **程序崩溃**：已生成的样本已通过增量保存写入文件
- **无需恢复机制**：增量保存确保数据实时持久化

### 5. 输出文件

**增量保存模式（默认）**：
1. `questions_YYYYMMDD_HHMMSS_incremental.jsonl` - **问题增量保存**（按主题批量追加）
2. `pubmed_trajectory_YYYYMMDD_HHMMSS_incremental.jsonl` - **轨迹增量保存**（生成 1 条追加 1 条）
3. `pubmed_trajectory_YYYYMMDD_HHMMSS.csv` - CSV 格式（完成后生成）
4. `trajectory_stats_YYYYMMDD_HHMMSS.json` - 统计信息（完成后生成）

**查看问题质量**：
```bash
# 实时查看生成的问题
tail -f questions_*_incremental.jsonl | jq '.question'

# 查看问题和主题
cat questions_*_incremental.jsonl | jq '{question: .question, topic: .topic}'

# 统计每个主题的问题数
cat questions_*_incremental.jsonl | jq -r '.topic' | sort | uniq -c
```

**传统保存模式（`--no-incremental`）**：
1. `pubmed_trajectory_YYYYMMDD_HHMMSS.jsonl` - JSONL 格式（完成后一次性写入）
2. `pubmed_trajectory_YYYYMMDD_HHMMSS.csv` - CSV 格式（完成后生成）
3. `trajectory_stats_YYYYMMDD_HHMMSS.json` - 统计信息（完成后生成）

## 性能估算

基于实测数据（gpt-5.2 + MCP 服务器）：

| 数量 | 并发数 | 预计时间 | 说明 |
|------|-------|---------|------|
| 1 条 | 1 | ~30秒 | 单条测试 |
| 10 条 | 3 | ~3分钟 | 快速验证 |
| 50 条 | 5 | ~10分钟 | 中等规模 |
| 100 条 | 8 | ~15分钟 | 较大规模 |
| 200 条 | 8-10 | ~25-30分钟 | 大批量 |

*实际时间会因网络、API 响应速度、问题复杂度而异*

## 故障排查

### 问题 1: 大量任务失败

**症状**：成功率 < 70%

**可能原因**：
- MCP 服务器超载
- API 限流
- 网络不稳定

**解决方案**：
```bash
# 降低并发数
--concurrency 3  # 从 8 降到 3
```

### 问题 2: MCP 服务器无响应

**症状**：所有工具调用超时

**解决方案**：
```bash
# 1. 检查 MCP 服务器
curl http://localhost:8003/health

# 2. 重启 MCP 服务器
fuser -k 8003/tcp
cd /workspace/math_science_data/lyc/1205/dr-tulu/agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

### 问题 3: 内存不足

**症状**：OOM 错误

**解决方案**：
```bash
# 降低并发数
--concurrency 3
```

## 最佳实践

### 生成 200 条数据的推荐流程

```bash
# 1. 先测试 1 条，验证环境
uv run python .../generate_trajectory_dataset.py \
    --num-questions 1 \
    --model openai/gpt-5.2 \
    --concurrency 1

# 2. 测试 10 条，验证稳定性
uv run python .../generate_trajectory_dataset.py \
    --num-questions 10 \
    --model openai/gpt-5.2 \
    --concurrency 5

# 3. 正式生成 200 条
uv run python .../generate_trajectory_dataset.py \
    --num-questions 200 \
    --model openai/gpt-5.2 \
    --concurrency 8
```

### 使用 nohup 后台运行（推荐用于大批量）

```bash
nohup uv run python .../generate_trajectory_dataset.py \
    --num-questions 200 \
    --model openai/gpt-5.2 \
    --concurrency 8 \
    > generation.log 2>&1 &

# 查看进度
tail -f generation.log

# 查看进程
ps aux | grep generate_trajectory_dataset
```

## 监控和日志

### 实时监控

```bash
# 终端 1: 运行生成
uv run python .../generate_trajectory_dataset.py --num-questions 200 --concurrency 8

# 终端 2: 监控 MCP 服务器
watch -n 1 'netstat -an | grep 8003 | wc -l'

# 终端 3: 监控内存
watch -n 2 'free -h'
```

### 日志分析

生成完成后，检查统计文件：
```bash
cat ../../pubmed_training_data/trajectory_stats_*.json | jq .
```

## 成本估算

基于 OpenRouter 定价（示例）：

- gpt-5.2: ~$X / 1M tokens
- 每条数据约: Y tokens (问题 + 轨迹 + rubrics)
- 200 条总成本: ~$Z

*请查看 OpenRouter 实际定价*

