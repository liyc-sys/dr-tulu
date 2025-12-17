# 快速开始：并发生成 200 条 PubMed 数据

## ✅ 前置检查

```bash
# 1. 检查 MCP 服务器
curl http://localhost:8003/health
# 应返回: OK

# 2. 检查 Crawl4AI Docker
docker ps | grep crawl4ai
# 应看到容器运行中

# 3. 确认环境变量
echo $OPENROUTER_API_KEY
echo $CRAWL4AI_API_URL
echo $SERPER_API_KEY
```

## 🚀 生成流程

### 步骤 1: 测试单条（1分钟）

```bash
cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct

uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 1 \
    --model openai/gpt-5.2 \
    --concurrency 1
```

**预期结果**：生成 1 条数据，耗时约 30-60 秒

### 步骤 2: 测试小批量（3-5分钟）

```bash
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 10 \
    --model openai/gpt-5.2 \
    --concurrency 5
```

**预期结果**：生成 10 条数据，耗时约 3-5 分钟

### 步骤 3: 正式生成数据

#### 方案 A: 带 rubrics（300条，适合评估）

```bash
# 前台运行
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 300 \
    --model openai/gpt-5.2 \
    --concurrency 8

# 后台运行（推荐）
nohup uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 300 \
    --model openai/gpt-5.2 \
    --concurrency 8 \
    > ~/generation_300_rubrics.log 2>&1 &
```

**预期结果**：
- 总耗时：~40-50 分钟
- 成功率：> 90%
- 包含：tool_rubrics + content_rubrics

#### 方案 B: 不带 rubrics（1000条，适合训练）⭐ NEW

```bash
# 前台运行
uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 1000 \
    --model openai/gpt-5.2 \
    --concurrency 10 \
    --no-rubrics

# 后台运行（推荐）
nohup uv run python /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator/generate_trajectory_dataset.py \
    --num-questions 1000 \
    --model openai/gpt-5.2 \
    --concurrency 10 \
    --no-rubrics \
    > ~/generation_1000_no_rubrics.log 2>&1 &

# 记录进程 ID
echo $! > ~/generation.pid

# 实时查看进度
tail -f ~/generation_1000_no_rubrics.log

# 查看进程状态
ps -p $(cat ~/generation.pid)

# 如需停止
kill $(cat ~/generation.pid)
```

**预期结果**：
- 总耗时：~80-100 分钟（比带 rubrics 快 ~30-40%）
- 成功率：> 90%
- 无 rubrics，仅包含问题和轨迹
- 输出文件位置：`/workspace/math_science_data/lyc/1205/dr-tulu/pubmed_training_data/`

## 📊 实时监控

### 终端 1: 运行任务
```bash
cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct
uv run python .../generate_trajectory_dataset.py --num-questions 200 --model openai/gpt-5.2 --concurrency 8
```

### 终端 2: 监控 MCP 连接数
```bash
watch -n 2 'netstat -an | grep 8003 | grep ESTABLISHED | wc -l'
# 应该看到 1-8 个连接（取决于并发数）
```

### 终端 3: 监控系统资源
```bash
watch -n 2 'free -h && echo "---" && ps aux | grep generate_trajectory_dataset | head -5'
```

## 📁 输出文件

### 增量保存模式（默认）⭐

**两个阶段的增量保存**：

#### 阶段 1: 问题生成
```
questions_20231216_143022_incremental.jsonl  # 实时保存生成的问题（可提前检查质量）
```
- 每生成一批问题（按主题）立即追加到文件
- 可以在轨迹生成前查看问题质量
- 包含：question, topic, question_type

#### 阶段 2: 轨迹生成
```
pubmed_trajectory_20231216_143022_incremental.jsonl  # 实时增量 JSONL（生成1条追加1条）
pubmed_trajectory_20231216_143022.csv                # CSV 格式（完成后生成）
trajectory_stats_20231216_143022.json                # 统计信息（完成后生成）
```

**优势**：
- ✅ 即使程序中途退出，已生成的数据完整保存
- ✅ 可以随时打开 `.jsonl` 文件查看进度
- ✅ 按 Ctrl+C 中断后，数据不丢失
- ✅ **问题单独保存，方便提前审查质量**

### 禁用增量保存

如需使用传统模式（完成后一次性保存），添加 `--no-incremental`：

```bash
uv run python .../generate_trajectory_dataset.py \
    --num-questions 200 \
    --model openai/gpt-5.2 \
    --concurrency 8 \
    --no-incremental
```

### 查看统计信息
```bash
cd /workspace/math_science_data/lyc/1205/dr-tulu/pubmed_training_data
cat trajectory_stats_*.json | jq '.'
```

### 查看数据样本
```bash
head -n 1 pubmed_trajectory_*.jsonl | jq '.'
```

## ⚠️ 常见问题

### 问题1: 成功率低于 80%

**原因**：MCP 服务器或 API 过载

**解决**：
```bash
# 降低并发数到 3-5
--concurrency 5
```

### 问题2: 工具调用超时

**原因**：Crawl4AI Docker 未运行

**解决**：
```bash
# 检查 Docker
docker ps | grep crawl4ai

# 如果没有，启动它
docker run -d -p 11235:11235 \
  -e http_proxy="http://httpproxy.glm.ai:8888" \
  -e https_proxy="http://httpproxy.glm.ai:8888" \
  -e no_proxy="127.0.0.1,localhost,platform.glm.ai" \
  unclecode/crawl4ai:latest
```

### 问题3: 内存不足

**解决**：
```bash
# 降低并发数
--concurrency 3
```

## 🎯 最佳配置

| 场景 | 并发数 | 预计时间 | 命令 |
|------|-------|---------|------|
| **快速测试** | 1 | 1 分钟 | `--num-questions 1 --concurrency 1` |
| **验证稳定性** | 5 | 3 分钟 | `--num-questions 10 --concurrency 5` |
| **小批量** | 5 | 10 分钟 | `--num-questions 50 --concurrency 5` |
| **标准批量** | 8 | 15 分钟 | `--num-questions 100 --concurrency 8` |
| **大批量** | 8-10 | 25-30 分钟 | `--num-questions 200 --concurrency 8` |

## 💡 提示

1. **首次运行**：建议从小批量（10条）开始，验证环境稳定后再大批量生成
2. **长时间任务**：使用 `nohup` 后台运行，避免网络中断导致任务失败
3. **保存进度**：即使中途中断（Ctrl+C），已完成的数据也会自动保存
4. **资源监控**：大批量生成时，建议监控 MCP 服务器和系统资源
5. **错误恢复**：如果某次运行失败率较高，降低并发数重试

## 📞 需要帮助？

查看详细文档：
- `CONCURRENT_USAGE.md` - 完整使用指南
- `TOOL_CALL_LOGIC.md` - 工具调用逻辑
- `README.md` - 项目说明

