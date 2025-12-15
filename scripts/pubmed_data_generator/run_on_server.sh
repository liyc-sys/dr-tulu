#!/bin/bash
# PubMed 数据生成器服务器启动脚本
# 使用方法: bash run_on_server.sh [参数]

# 配置路径（根据你的服务器环境修改）
SERVER_PROJECT_ROOT="/workspace/math_science_data/lyc/1205/dr-tulu"
UV_PROJECT_DIR="${SERVER_PROJECT_ROOT}/rl/open-instruct"
SCRIPT_DIR="${SERVER_PROJECT_ROOT}/scripts/pubmed_data_generator"
OUTPUT_DIR="${SERVER_PROJECT_ROOT}/pubmed_training_data"

# ========== 代理配置（GLM 服务器必需）==========
export http_proxy="http://httpproxy.glm.ai:8888"
export https_proxy="http://httpproxy.glm.ai:8888"
export no_proxy="127.0.0.1,localhost,platform.glm.ai"

# ========== MCP 和 API 配置 ==========
export MCP_TRANSPORT="StreamableHttpTransport"
export MCP_TRANSPORT_HOST="127.0.0.1"
export MCP_TRANSPORT_PORT="8003"

# 如果没有设置 OPENROUTER_API_KEY，使用配置中的默认值
if [ -z "$OPENROUTER_API_KEY" ]; then
    export OPENROUTER_API_KEY="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"
fi

# 确保输出目录存在
mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "PubMed 训练数据生成器"
echo "============================================"
echo "UV 项目目录: $UV_PROJECT_DIR"
echo "脚本目录: $SCRIPT_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "MCP 服务器: $MCP_TRANSPORT_HOST:$MCP_TRANSPORT_PORT"
echo "============================================"

# 切换到 UV 项目目录并运行
cd "$UV_PROJECT_DIR"

# 默认参数
CLUSTERS=${1:-5}
QUERIES=${2:-3}
SAMPLES=${3:-1}
PAGINATION_RATIO=${4:-0.2}

echo ""
echo "运行参数:"
echo "  --clusters $CLUSTERS"
echo "  --queries $QUERIES"
echo "  --samples $SAMPLES"
echo "  --pagination-ratio $PAGINATION_RATIO"
echo "  --output $OUTPUT_DIR"
echo ""

# 使用 uv run 执行脚本
uv run python "$SCRIPT_DIR/generate_dataset.py" \
    --clusters "$CLUSTERS" \
    --queries "$QUERIES" \
    --samples "$SAMPLES" \
    --pagination-ratio "$PAGINATION_RATIO" \
    --output "$OUTPUT_DIR"

echo ""
echo "============================================"
echo "完成！输出目录: $OUTPUT_DIR"
echo "============================================"

