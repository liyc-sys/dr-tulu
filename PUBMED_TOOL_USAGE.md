# PubMed 搜索工具使用说明

## ✅ 已完成的配置

已经为你创建了完整的 `pubmed_search` 工具，包括：

### 1. MCP 后端工具 ✓
位置: `agent/dr_agent/mcp_backend/main.py`
- 函数名: `pubmed_search`
- 已经存在并可用

### 2. 工具包装类 ✓
位置: `agent/dr_agent/tool_interface/mcp_tools.py`
- 类名: `PubMedSearchTool`
- 已添加完整实现

### 3. 工具注册 ✓
位置: `rl/open-instruct/open_instruct/search_utils/mcp_tools.py`
- 已导入 `PubMedSearchTool`
- 已注册到 `MCP_TOOL_REGISTRY` 中，键名为 `"pubmed_search"`

## 📝 如何在训练中使用

### 方式 1: 单独使用 PubMed 搜索

修改 `train_dr_tulu.sh` 第 138 行：

```bash
--mcp_tool_names 'pubmed_search' \
```

### 方式 2: 与其他工具组合使用

```bash
# 组合 Google 搜索 + PubMed 搜索
--mcp_tool_names 'google_search,pubmed_search' \

# 组合 Google 搜索 + PubMed 搜索 + 网页浏览
--mcp_tool_names 'google_search,pubmed_search,browse_webpage' \

# 组合学术搜索工具
--mcp_tool_names 'snippet_search,pubmed_search' \
```

### 方式 3: 完整配置示例

在 `train_dr_tulu.sh` 中修改以下行：

```bash
# 第 138 行
--mcp_tool_names 'google_search,pubmed_search,browse_webpage' \
```

## 🧪 测试工具

### 1. 启动 MCP 服务器

```bash
cd /Users/liyc/Desktop/dr-tulu/agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

### 2. 运行测试脚本

在另一个终端：

```bash
cd /Users/liyc/Desktop/dr-tulu
python test_pubmed_tool.py
```

### 3. 预期输出

```
==============================================================
PubMed 搜索工具测试
==============================================================

初始化 PubMed 搜索工具...
✓ 工具创建成功

测试查询: machine learning in healthcare
------------------------------------------------------------

搜索结果:
- 调用成功: True
- 是否有错误: 无
- 运行时间: 2.34秒
- 找到文档数: 5

前 3 篇论文:

1. Machine Learning Applications in Healthcare...
   URL: https://pubmed.ncbi.nlm.nih.gov/12345678/
   评分(引用数): 156
   摘要: Authors: Smith, J. et al. | Year: 2023 | ...
```

## 🔧 工具特性

### 输入参数

- `query` (必填): 搜索查询字符串
- `limit` (可选): 返回结果数量，默认 10
- `offset` (可选): 分页起始位置，默认 0

### 输出格式

每个搜索结果包含：
- **标题**: 论文标题
- **摘要**: 包含元数据（作者、年份、期刊、引用数）+ 完整摘要
- **URL**: PubMed 链接
- **评分**: 引用数（来自 Semantic Scholar）

### 元数据增强

工具自动从 Semantic Scholar 获取额外信息：
- 引用数 (`citationCount`)
- 其他学术指标

## 📊 工具对比

| 工具名 | 用途 | 数据源 | 适用场景 |
|--------|------|--------|----------|
| `google_search` | 通用网页搜索 | Google | 通用问题、最新信息 |
| `snippet_search` | 学术论文片段搜索 | Semantic Scholar | 学术研究、精确引用 |
| `pubmed_search` | 医学/生命科学论文 | PubMed + Semantic Scholar | 医疗、生物医学研究 |
| `browse_webpage` | 网页内容提取 | Crawl4AI | 获取完整网页内容 |
| `massive_serve` | 文档检索 | Wikipedia 等 | 知识库检索 |

## 💡 最佳实践

### 医学研究问题

```bash
--mcp_tool_names 'pubmed_search,browse_webpage' \
```

使用 PubMed 找到相关论文，然后用 browse_webpage 获取全文。

### 综合研究问题

```bash
--mcp_tool_names 'google_search,snippet_search,pubmed_search,browse_webpage' \
```

组合使用多个搜索源，提供最全面的信息。

### 快速原型测试

```bash
--mcp_tool_names 'pubmed_search' \
```

单独测试 PubMed 功能。

## 🔍 调试技巧

### 查看工具调用日志

日志文件位置由 `MCP_TOOL_LOG_DIR` 环境变量控制，默认在：
```
./mcp_tool_logs/tool_calls_log.jsonl
```

### 检查可用工具

在 Python 中：

```python
from rl.open_instruct.open_instruct.search_utils.mcp_tools import MCP_TOOL_REGISTRY

print("可用的 MCP 工具:")
for tool_name in MCP_TOOL_REGISTRY.keys():
    print(f"  - {tool_name}")
```

输出应包含:
```
可用的 MCP 工具:
  - snippet_search
  - google_search
  - massive_serve
  - browse_webpage
  - pubmed_search
```

## ⚠️ 注意事项

1. **MCP 服务器必须运行**: 训练前确保 MCP 服务器已启动
2. **端口配置一致**: 确保训练脚本中的端口 (8003) 与 MCP 服务器端口一致
3. **API 限制**: PubMed API 有速率限制，建议合理设置 `limit` 参数
4. **网络依赖**: 工具需要访问 PubMed 和 Semantic Scholar API

## 📚 相关文件

- MCP 后端: `agent/dr_agent/mcp_backend/main.py` (第 134-169 行)
- 工具实现: `agent/dr_agent/tool_interface/mcp_tools.py` (第 748-805 行)
- 工具注册: `rl/open-instruct/open_instruct/search_utils/mcp_tools.py` (第 15-30 行)
- API 实现: `agent/dr_agent/mcp_backend/apis/pubmed_apis.py`
- 测试脚本: `test_pubmed_tool.py`

## 🎯 下一步

1. **测试工具**: 运行 `test_pubmed_tool.py` 确认工具正常工作
2. **更新训练脚本**: 修改 `train_dr_tulu.sh` 第 138 行添加 `pubmed_search`
3. **开始训练**: 运行训练脚本

祝训练顺利！🚀

