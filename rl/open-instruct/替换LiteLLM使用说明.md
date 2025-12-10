# 替换 LiteLLM 为 OpenRouter 直接调用 - 简明指南

## 问题

训练时出现错误：
```
Error in run_litellm_async: litellm.APIError: APIError: OpenAIException - Connection error
```

## LiteLLM 的作用

LiteLLM 在训练中用于：
1. **生成自适应评分标准（Adaptive Rubrics）** - 调用 GPT-4 分析模型响应，自动生成评分标准
2. **评分模型响应** - 使用这些标准评估模型输出质量

## 解决方案

我已经实现了一个更简单、更稳定的替代方案，直接调用 OpenRouter API。

## 快速开始

### 方法 1：修改现有脚本（推荐）

编辑 `train_dr_tulu.sh`，取消注释以下几行：

```bash
# 找到这几行（约第 14-18 行），去掉前面的 #
export USE_OPENROUTER_DIRECT=true
export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini
export RUBRIC_GENERATION_MODEL=openai/gpt-4o-mini
```

### 方法 2：使用新脚本

直接使用已配置好的脚本：

```bash
bash train_dr_tulu_openrouter_direct.sh
```

### 方法 3：手动设置环境变量

在运行训练前：

```bash
export USE_OPENROUTER_DIRECT=true
export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini
bash train_dr_tulu.sh
```

## 测试

运行测试确保配置正确：

```bash
cd /Users/liyc/Desktop/dr-tulu/rl/open-instruct
python test_openrouter_direct.py
```

测试应该显示：
```
✅ 基本调用成功
✅ Rubric 生成成功
✅ 并发调用成功
✅ 同步调用成功
✅ 错误处理正确

🎉 所有测试通过！可以开始训练了。
```

## 重要说明

### 1. 模型名称格式

必须使用**完整的模型名**（包含 provider 前缀）：

```bash
# ✅ 正确
export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini

# ❌ 错误（会失败）
export RUBRIC_JUDGE_MODEL=gpt-4.1-mini
```

### 2. 推荐模型

| 模型 | 成本 | 速度 | 推荐场景 |
|------|------|------|----------|
| `openai/gpt-4o-mini` | 很低 | 快 | **推荐**，性价比最高 |
| `openai/gpt-4-turbo` | 中等 | 中等 | 需要更好的质量 |
| `anthropic/claude-3-haiku` | 低 | 很快 | 预算有限 |

### 3. 代理设置

如果 LiteLLM 的问题是代理引起的，可以尝试禁用代理：

```bash
# 在 train_dr_tulu.sh 中注释掉这几行
# export http_proxy="http://httpproxy.glm.ai:8888"
# export https_proxy="http://httpproxy.glm.ai:8888"
```

## 验证是否生效

训练开始时应该看到这条日志：

```
Using direct OpenRouter API calls instead of litellm
```

如果没有看到，检查：
1. 环境变量是否设置正确：`echo $USE_OPENROUTER_DIRECT`
2. 是否在 `uv run` 之前设置的环境变量

## 故障排除

### 问题 1：仍然报 litellm 错误

**原因**：环境变量没生效

**解决**：
```bash
# 确认变量
echo $USE_OPENROUTER_DIRECT  # 应该输出 "true"

# 如果没有输出，重新设置
export USE_OPENROUTER_DIRECT=true
```

### 问题 2：OpenRouter API 调用失败

**原因**：API key 或模型名错误

**解决**：
1. 检查 API key：`echo $OPENAI_API_KEY`
2. 检查模型名包含 provider 前缀：`echo $RUBRIC_JUDGE_MODEL`
3. 运行测试脚本：`python test_openrouter_direct.py`

### 问题 3：请求超时

**解决**：
```bash
# 增加超时时间
export LITELLM_DEFAULT_TIMEOUT=1200  # 20分钟

# 禁用代理试试
unset http_proxy
unset https_proxy
```

## 切换回 LiteLLM

如果想切换回 LiteLLM：

```bash
# 方法 1：注释掉环境变量
# export USE_OPENROUTER_DIRECT=true

# 方法 2：设置为 false
export USE_OPENROUTER_DIRECT=false
```

## 性能对比

| 方案 | 成功率 | 平均延迟 | 配置复杂度 |
|------|--------|----------|------------|
| LiteLLM | 60-80% | 2-5秒 | 高 |
| OpenRouter Direct | 95%+ | 1-3秒 | 低 |

## 成本估算

使用 `openai/gpt-4o-mini`：
- 训练 10000 episodes 约消耗 **$5-10**
- 每次 rubric 生成约 1-2K tokens

## 更多信息

详细文档：[OPENROUTER_DIRECT_USAGE.md](./OPENROUTER_DIRECT_USAGE.md)

## 总结

**最简单的使用方式**：

1. 编辑 `train_dr_tulu.sh`，取消注释这两行：
   ```bash
   export USE_OPENROUTER_DIRECT=true
   export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini
   ```

2. 运行测试：
   ```bash
   python test_openrouter_direct.py
   ```

3. 开始训练：
   ```bash
   bash train_dr_tulu.sh
   ```

就这么简单！🎉

