#!/bin/bash
# 使用本地Qwen3-8B模型从已有问题生成轨迹

# 配置参数
QUESTIONS_FILE="${1:-../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl}"
LOCAL_MODEL_URL="${2:-http://localhost:8000/v1}"
MODEL_NAME="${3:-Qwen3-8B}"
CONCURRENCY="${4:-5}"
OUTPUT_DIR="../../pubmed_training_data"

echo "=========================================="
echo "本地模型轨迹生成"
echo "=========================================="
echo "问题文件: $QUESTIONS_FILE"
echo "本地模型URL: $LOCAL_MODEL_URL"
echo "模型名称: $MODEL_NAME"
echo "并发数: $CONCURRENCY"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="
echo ""

# 运行生成脚本
python generate_trajectory_from_questions.py \
    --questions-file "$QUESTIONS_FILE" \
    --local-model-url "$LOCAL_MODEL_URL" \
    --model-name "$MODEL_NAME" \
    --output "$OUTPUT_DIR" \
    --concurrency "$CONCURRENCY"

echo ""
echo "=========================================="
echo "生成完成！"
echo "=========================================="

