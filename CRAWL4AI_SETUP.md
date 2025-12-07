# Crawl4AIBrowseTool 配置指南

本文档说明如何配置和测试 `Crawl4AIBrowseTool`，确保其在训练时正常工作。

## 概述

训练脚本使用3个工具：
1. **snippet_search** - Semantic Scholar学术搜索
2. **google_search** - Google网页搜索（通过Serper）
3. **browse_webpage** - 网页内容提取（通过Crawl4AI）

## 必需配置

### 1. API Keys

在训练脚本中已设置：
```bash
export S2_API_KEY=sk-user-F788DB8EABBDAD1858E82734A4E0C1BA
export SERPER_API_KEY=56e20b0fb1dc8a9d19fb80be90fb346e63294148
```

### 2. Crawl4AI Docker API配置

训练脚本使用 `use_docker_version=True` 和 `use_ai2_config=True`，因此需要配置：

```bash
# Crawl4AI Docker API地址
export CRAWL4AI_API_URL="http://your-crawl4ai-server:8000"

# Crawl4AI API Key（可选，取决于服务器配置）
export CRAWL4AI_API_KEY="your-api-key"

# Crawl4AI Blocklist文件路径（必需）
export CRAWL4AI_BLOCKLIST_PATH="/path/to/blocklist.txt"
```

### 3. 下载Blocklist文件

```bash
# 创建目录
mkdir -p /stage/rl-rag-mcp/utils/

# 下载blocklist
wget https://raw.githubusercontent.com/allenai/crawler-rules/main/blocklist.txt \
  -O /stage/rl-rag-mcp/utils/crawl4ai_block_list.txt

# 或者使用训练脚本中的路径
export CRAWL4AI_BLOCKLIST_PATH=/stage/rl-rag-mcp/utils/crawl4ai_block_list.txt
```

如果 `/stage` 目录不存在，可以使用本地路径：
```bash
# 下载到项目目录
mkdir -p utils
wget https://raw.githubusercontent.com/allenai/crawler-rules/main/blocklist.txt \
  -O utils/crawl4ai_block_list.txt

export CRAWL4AI_BLOCKLIST_PATH=$(pwd)/utils/crawl4ai_block_list.txt
```

### 4. 启动MCP服务器

训练需要MCP服务器运行在端口8003：

```bash
# 进入agent目录
cd agent

# 启动MCP服务器（与训练脚本一致的配置）
uv run python -m dr_agent.mcp_backend.main \
  --transport http \
  --port 8003 \
  --host 0.0.0.0 \
  --path /mcp
```

### 5. 设置Crawl4AI Docker服务

如果你没有Crawl4AI Docker服务，有两个选项：

#### 选项A：部署Crawl4AI Docker服务

参考 Crawl4AI 官方文档部署 Docker 服务。

#### 选项B：不使用AI2配置（简化版）

如果不需要AI2配置，可以修改训练脚本的browse配置：

在 `open_instruct/search_utils/mcp_tools.py` 第117-119行：
```python
# 修改前
if mcp_tool_name == "browse_webpage":
    filtered_kwargs["use_docker_version"] = True
    filtered_kwargs["use_ai2_config"] = True

# 修改后（使用本地Crawl4AI，不需要Docker服务）
if mcp_tool_name == "browse_webpage":
    filtered_kwargs["use_docker_version"] = False
    filtered_kwargs["use_ai2_config"] = False
```

## 完整配置示例

### 方案1：完整Docker配置（推荐用于生产）

```bash
# API Keys
export S2_API_KEY=sk-user-F788DB8EABBDAD1858E82734A4E0C1BA
export SERPER_API_KEY=56e20b0fb1dc8a9d19fb80be90fb346e63294148

# Crawl4AI配置
export CRAWL4AI_API_URL="http://your-crawl4ai-server:8000"
export CRAWL4AI_API_KEY="your-api-key"
export CRAWL4AI_BLOCKLIST_PATH=/stage/rl-rag-mcp/utils/crawl4ai_block_list.txt

# MCP配置
export MCP_TRANSPORT_PORT=8003
export MCP_MAX_CONCURRENT_CALLS=512

# 启动MCP服务器
cd agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp &

# 等待服务器启动
sleep 5

# 运行训练
cd ../rl/open-instruct
./train_dr_tulu_with_dora.sh
```

### 方案2：本地Crawl4AI配置（简化版）

```bash
# API Keys
export S2_API_KEY=sk-user-F788DB8EABBDAD1858E82734A4E0C1BA
export SERPER_API_KEY=56e20b0fb1dc8a9d19fb80be90fb346e63294148

# MCP配置
export MCP_TRANSPORT_PORT=8003
export MCP_MAX_CONCURRENT_CALLS=512

# 修改代码使用本地Crawl4AI（见上面的代码修改）

# 启动MCP服务器
cd agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp &

# 等待服务器启动
sleep 5

# 运行训练
cd ../rl/open-instruct
./train_dr_tulu_with_dora.sh
```

## 测试配置

运行测试脚本验证配置：

```bash
# 确保MCP服务器正在运行
cd agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp &

# 在新终端运行测试
cd ..
python test_crawl4ai_browse_tool.py
```

测试脚本会检查：
- ✅ 环境变量配置
- ✅ MCP服务器连接
- ✅ snippet_search工具
- ✅ google_search工具
- ✅ browse_webpage工具

## 常见问题

### 1. MCP服务器连接失败

**错误**: `无法连接到MCP服务器`

**解决**:
```bash
# 检查服务器是否运行
curl http://localhost:8003/health

# 如果没有运行，启动服务器
cd agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

### 2. Blocklist文件不存在

**错误**: `Blocklist file not found`

**解决**:
```bash
# 下载blocklist文件
mkdir -p utils
wget https://raw.githubusercontent.com/allenai/crawler-rules/main/blocklist.txt -O utils/blocklist.txt
export CRAWL4AI_BLOCKLIST_PATH=$(pwd)/utils/blocklist.txt
```

### 3. Crawl4AI API连接失败

**错误**: `CRAWL4AI_API_URL is not set` 或连接超时

**解决**:

方案A - 如果有Crawl4AI服务：
```bash
export CRAWL4AI_API_URL="http://your-server:8000"
export CRAWL4AI_API_KEY="your-key"
```

方案B - 使用本地Crawl4AI（推荐测试）：
修改 `rl/open-instruct/open_instruct/search_utils/mcp_tools.py`:
```python
# 第117-119行
if mcp_tool_name == "browse_webpage":
    filtered_kwargs["use_docker_version"] = False  # 改为False
    filtered_kwargs["use_ai2_config"] = False      # 改为False
```

### 4. API Key无效

**错误**: `API key invalid` 或 `401 Unauthorized`

**解决**:
- 检查S2_API_KEY和SERPER_API_KEY是否正确
- 确认API配额未用完

## 训练脚本中的工具调用流程

训练过程中，模型会按以下方式调用工具：

1. **搜索阶段**: 使用 `snippet_search` 或 `google_search`
   ```xml
   <call_tool name="google_search">machine learning tutorial</call_tool>
   ```

2. **浏览阶段**: 使用 `browse_webpage` 打开搜索结果中的URL
   ```xml
   <call_tool name="browse_webpage">https://example.com/article</call_tool>
   ```

3. **工具调用限制**: 最多10次（`--max_tool_calls 10`）

4. **工具输出格式**:
   - 搜索: `<snippet id=...>content</snippet>`
   - 浏览: `<webpage id=...>content</webpage>`

## 参考

- 训练脚本: `rl/open-instruct/train_dr_tulu_with_dora.sh`
- 工具定义: `agent/dr_agent/mcp_backend/main.py`
- 工具包装: `agent/dr_agent/tool_interface/mcp_tools.py`
- 系统提示: `rl/open-instruct/open_instruct/search_utils/system_prompts/unified_tool_calling_v20250907.yaml`

