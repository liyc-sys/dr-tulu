#!/bin/bash
# 使用本地DR-Tulu-8B模型从已有问题生成轨迹

# 配置参数
QUESTIONS_FILE="${1:-../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl}"
LOCAL_MODEL_URL="${2:-http://localhost:8000/v1}"
MODEL_NAME="${3:-DR-Tulu-8B}"
CONCURRENCY="${4:-5}"
OUTPUT_DIR="../../pubmed_training_data"

# uv环境路径
UV_VENV="/workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct/.venv"

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

# 激活uv环境（如果存在）
if [ -d "$UV_VENV" ]; then
    echo "激活uv环境: $UV_VENV"
    source "$UV_VENV/bin/activate"
fi

# 运行生成脚本
python generate_trajectory_from_questions.py \
    --questions-file "$QUESTIONS_FILE" \
    --local-model-url "$LOCAL_MODEL_URL" \
    --model-name "$MODEL_NAME" \
    --output "$OUTPUT_DIR" \
    --concurrency "$CONCURRENCY"

# 退出虚拟环境
if [ -d "$UV_VENV" ]; then
    deactivate
fi

echo ""
echo "=========================================="
echo "生成完成！"
echo "=========================================="

