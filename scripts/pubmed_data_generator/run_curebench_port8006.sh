#!/bin/bash

# CureBench 评测 - 使用端口 8006 的模型

echo "=========================================="
echo "CureBench 评测 - 端口 8006"
echo "=========================================="

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_FILE="$PROJECT_ROOT/训练和benchmark数据0120/curebench_valset_pharse1.jsonl"
LOCAL_MODEL_URL="http://localhost:8006/v1"
MODEL_NAME="8B_DPO_run1_epoch0"
INSTANCE_ID="port8006"
OUTPUT_DIR="$PROJECT_ROOT/pubmed_training_data"
CONCURRENCY=3

# 如果提供了参数，使用参数中的 limit
if [ "$1" != "" ]; then
    LIMIT=$1
    echo ""
    echo "配置信息:"
    echo "  数据文件: $DATA_FILE"
    echo "  本地模型: $MODEL_NAME"
    echo "  API地址: $LOCAL_MODEL_URL"
    echo "  实例ID: $INSTANCE_ID"
    echo "  并发数: $CONCURRENCY"
    echo "  测试数量: 前 $LIMIT 个问题"
    echo ""
else
    echo ""
    echo "配置信息:"
    echo "  数据文件: $DATA_FILE"
    echo "  本地模型: $MODEL_NAME"
    echo "  API地址: $LOCAL_MODEL_URL"
    echo "  实例ID: $INSTANCE_ID"
    echo "  并发数: $CONCURRENCY"
    echo "  处理: 全部问题"
    echo ""
fi

# 检查数据文件
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ 错误: 数据文件不存在: $DATA_FILE"
    exit 1
fi

# 检查模型是否在运行
echo "检查模型服务..."
if curl -s --connect-timeout 3 "$LOCAL_MODEL_URL/models" > /dev/null 2>&1; then
    echo "✓ 模型服务正常运行"
else
    echo "❌ 错误: 无法连接到模型服务 ($LOCAL_MODEL_URL)"
    echo "   请确认模型已启动在端口 8006"
    exit 1
fi

# 检查 Python 脚本
PYTHON_SCRIPT="$SCRIPT_DIR/answer_curebench_with_tools.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ 错误: Python 脚本不存在: $PYTHON_SCRIPT"
    exit 1
fi

echo ""
echo "开始运行..."
echo ""

# 构建命令
CMD="python3 \"$PYTHON_SCRIPT\" \
    --data-file \"$DATA_FILE\" \
    --local-model-url \"$LOCAL_MODEL_URL\" \
    --model-name \"$MODEL_NAME\" \
    --instance-id \"$INSTANCE_ID\" \
    --output \"$OUTPUT_DIR\" \
    --concurrency $CONCURRENCY"

# 如果有 limit 参数，添加到命令中
if [ "$1" != "" ]; then
    CMD="$CMD --limit $LIMIT"
fi

# 运行
eval $CMD

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo "✓ 评测完成！"
    echo "结果保存在: $OUTPUT_DIR"
    echo "  - curebench_results_*_${MODEL_NAME}_${INSTANCE_ID}.jsonl"
    echo "  - curebench_stats_*_${MODEL_NAME}_${INSTANCE_ID}.json"
    echo "=========================================="
else
    echo "=========================================="
    echo "⚠️  评测中断或出错"
    echo "部分结果已保存在: $OUTPUT_DIR"
    echo "=========================================="
fi
