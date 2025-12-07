# Semantic Scholar API 修改说明

## 📍 修改位置

当运行 `train_dr_tulu_with_dora.sh` 时，Semantic Scholar 的工具调用逻辑位于：

```
/Users/liyc/Desktop/dr-tulu/agent/dr_agent/mcp_backend/apis/semantic_scholar_apis.py
```

## 🎯 修改目标

1. ✅ 免费调用使用官方地址（不花钱）
2. ✅ 付费调用使用代理地址（需要付费但更稳定）
3. ✅ 先尝试 3 次免费调用，失败后再使用付费调用

## 🔧 具体实现

### 1. API 地址配置

```python
# 免费调用使用官方地址
S2_GRAPH_API_URL_FREE = "https://api.semanticscholar.org/graph/v1"
S2_RECOMMENDATIONS_API_URL_FREE = "https://api.semanticscholar.org/recommendations/v1"

# 付费调用使用代理地址
S2_GRAPH_API_URL_PAID = "https://lifuai.com/api/v1/graph/v1"
S2_RECOMMENDATIONS_API_URL_PAID = "https://lifuai.com/api/v1/recommendations/v1"
```

### 2. 调用策略

**步骤 1: 免费调用（3 次重试）**
- 地址: `https://api.semanticscholar.org/graph/v1`
- API Key: 无（不带 API key）
- 重试次数: 3 次
- 重试间隔: 每次失败后等待 1 秒

**步骤 2: 付费调用（兜底）**
- 地址: `https://lifuai.com/api/v1/graph/v1`
- API Key: 使用环境变量 `S2_API_KEY`
- 只在免费调用全部失败后执行

### 3. 调用流程图

```
开始调用
    ↓
第 1 次免费调用 (官方地址)
    ↓
成功？
├─ 是 → 返回结果 ✓
└─ 否 → 等待 1 秒
    ↓
第 2 次免费调用 (官方地址)
    ↓
成功？
├─ 是 → 返回结果 ✓
└─ 否 → 等待 1 秒
    ↓
第 3 次免费调用 (官方地址)
    ↓
成功？
├─ 是 → 返回结果 ✓
└─ 否 → 切换到付费调用
    ↓
付费调用 (代理地址 + API key)
    ↓
成功？
├─ 是 → 返回结果 ✓
└─ 否 → 抛出异常 ✗
```

## 📊 运行日志示例

### 场景 1: 免费调用成功

```
✗ 免费调用失败 (尝试 1/3): 429 Too Many Requests
✓ 免费调用成功 (尝试 2/3) - 地址: https://api.semanticscholar.org/graph/v1/paper/search
```

### 场景 2: 免费失败，付费成功

```
✗ 免费调用失败 (尝试 1/3): 500 Internal Server Error
✗ 免费调用失败 (尝试 2/3): 500 Internal Server Error
✗ 免费调用失败 (尝试 3/3): 500 Internal Server Error
所有免费调用失败，切换到付费调用 - 地址: https://lifuai.com/api/v1/graph/v1/paper/search
✓ 付费调用成功
```

### 场景 3: 全部失败

```
✗ 免费调用失败 (尝试 1/3): Connection timeout
✗ 免费调用失败 (尝试 2/3): Connection timeout
✗ 免费调用失败 (尝试 3/3): Connection timeout
所有免费调用失败，切换到付费调用 - 地址: https://lifuai.com/api/v1/graph/v1/paper/search
✗ 付费调用也失败: Connection timeout
```

## ✅ 修改的函数列表

所有涉及 Semantic Scholar API 调用的函数都已更新：

| 函数名 | 用途 | 状态 |
|--------|------|------|
| `search_semantic_scholar_keywords()` | 关键词搜索论文 | ✅ 已更新 |
| `search_semantic_scholar_snippets()` | 搜索论文片段 | ✅ 已更新 |
| `search_semantic_scholar_bulk_api()` | 批量搜索论文 | ✅ 已更新 |
| `download_paper_details()` | 下载论文详情 | ✅ 已更新 |
| `download_paper_references()` | 下载论文引用 | ✅ 已更新 |
| `download_paper_citations()` | 下载论文被引 | ✅ 已更新 |
| `download_paper_details_batch()` | 批量下载论文详情 | ✅ 已更新 |

## 🧪 如何测试

运行测试脚本：

```bash
cd /Users/liyc/Desktop/dr-tulu
python test_semantic_scholar_api.py
```

测试脚本会：
1. 显示当前配置（免费/付费地址）
2. 执行一个真实的 Semantic Scholar API 调用
3. 显示详细的调用日志和结果

## 💰 成本节省效果

### 免费调用成功率估算

假设免费调用成功率为 30%，那么：

- **第 1 次成功**: 30% 的调用不花钱 ✓
- **第 2 次成功**: 额外 21% 的调用不花钱 ✓ (70% × 30%)
- **第 3 次成功**: 额外 14.7% 的调用不花钱 ✓ (70% × 70% × 30%)
- **总计**: **约 65.7%** 的调用可以免费完成！

### 如果免费成功率是 50%

- **总计**: **约 87.5%** 的调用可以免费完成！

## 🎛️ 可调参数

如果需要调整重试次数，修改以下参数：

```python
# 在 semantic_scholar_apis.py 第 38 行
FREE_RETRY_ATTEMPTS = 3  # 修改这个数字
```

建议值：
- `FREE_RETRY_ATTEMPTS = 2`: 更快速，但成功率较低
- `FREE_RETRY_ATTEMPTS = 3`: **默认值，平衡速度和成功率**
- `FREE_RETRY_ATTEMPTS = 5`: 更高成功率，但速度较慢

## 📝 使用说明

1. **正常运行训练脚本**
   ```bash
   cd /Users/liyc/Desktop/dr-tulu/rl/open-instruct
   ./train_dr_tulu_with_dora.sh
   ```

2. **查看 API 调用日志**
   
   在训练日志中搜索以下关键词：
   - `✓ 免费调用成功` - 免费调用成功
   - `✗ 免费调用失败` - 免费调用失败
   - `切换到付费调用` - 开始使用付费 API
   - `✓ 付费调用成功` - 付费调用成功

3. **监控成本**
   
   统计日志中的成功率：
   ```bash
   # 统计免费调用成功次数
   grep "✓ 免费调用成功" train_*.log | wc -l
   
   # 统计付费调用次数
   grep "切换到付费调用" train_*.log | wc -l
   ```

## 🔒 环境变量

确保设置了 API Key（用于付费调用）：

```bash
export S2_API_KEY="your-semantic-scholar-api-key"
```

或在 `.env` 文件中配置：

```env
S2_API_KEY=your-semantic-scholar-api-key
```

## ⚠️ 注意事项

1. **免费调用限制**
   - 官方免费 API 有速率限制
   - 如果频繁调用可能被限流
   - 这就是为什么需要付费 API 作为兜底

2. **重试间隔**
   - 每次失败后等待 1 秒再重试
   - 避免触发速率限制
   - 总重试时间约 2-3 秒

3. **缓存机制**
   - 代码中使用了 `@cached()` 装饰器
   - 相同查询会直接返回缓存结果
   - 不会重复调用 API

## 🚀 优化建议

如果想进一步优化成本：

1. **增加重试次数** (如改为 5 次)
2. **调整重试间隔** (如改为 2 秒)
3. **使用缓存** (已自动启用)
4. **批量查询** (使用 batch API)

---

**修改日期**: 2025-12-07  
**修改人**: AI Assistant  
**测试状态**: ✅ 代码已通过 linter 检查

