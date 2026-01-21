#!/bin/bash

# CureBench 测试脚本 - 用本地模型 + MCP 工具回答问题

echo "=========================================="
echo "CureBench 测试 - 本地模型 + MCP 工具"
echo "=========================================="

# 默认参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_FILE="$PROJECT_ROOT/训练和benchmark数据0120/curebench_valset_pharse1.jsonl"
LOCAL_MODEL_URL="http://localhost:8000/v1"
MODEL_NAME="Qwen3-8B"
OUTPUT_DIR="$PROJECT_ROOT/pubmed_training_data"
CONCURRENCY=3
LIMIT=10  # 先测试前10个问题

echo ""
echo "配置信息:"
echo "  数据文件: $DATA_FILE"
echo "  本地模型: $MODEL_NAME"
echo "  API地址: $LOCAL_MODEL_URL"
echo "  并发数: $CONCURRENCY"
echo "  测试数量: 前 $LIMIT 个问题"
echo ""

# 检查数据文件
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ 错误: 数据文件不存在: $DATA_FILE"
    exit 1
fi

# 检查 Python 脚本
PYTHON_SCRIPT="$SCRIPT_DIR/answer_curebench_with_tools.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ 错误: Python 脚本不存在: $PYTHON_SCRIPT"
    exit 1
fi

echo "开始运行..."
echo ""

# 运行 Python 脚本
python3 "$PYTHON_SCRIPT" \
    --data-file "$DATA_FILE" \
    --local-model-url "$LOCAL_MODEL_URL" \
    --model-name "$MODEL_NAME" \
    --output "$OUTPUT_DIR" \
    --concurrency "$CONCURRENCY" \
    --limit "$LIMIT"

echo ""
echo "=========================================="
echo "测试完成！"
echo "结果保存在: $OUTPUT_DIR"
echo "=========================================="
