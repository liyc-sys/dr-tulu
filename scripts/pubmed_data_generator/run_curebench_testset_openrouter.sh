#!/bin/bash
# CureBench Testset 对比测试 - 使用 OpenRouter API (seed1.8)
# 所有路径均为相对路径，基于本脚本所在位置推算

set -e

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 项目根目录: scripts/pubmed_data_generator/../../ = dr-tulu/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 配置
UV_PROJECT="$PROJECT_ROOT/rl/open-instruct"
DATA_FILE="$PROJECT_ROOT/训练和benchmark数据0120/curebench_testset_phase1.jsonl"
OUTPUT_BASE="$PROJECT_ROOT/curebench_testset_results"
MODEL_NAME="seed1.8"
INSTANCE_ID="comparison_test"
CONCURRENCY=5

# 检查环境变量
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "错误: 请设置环境变量 OPENROUTER_API_KEY"
    echo "  export OPENROUTER_API_KEY=your_key_here"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_BASE"

echo "========================================"
echo "CureBench Testset 对比测试 - OpenRouter ($MODEL_NAME)"
echo "========================================"
echo "数据文件: $DATA_FILE"
echo "输出目录: $OUTPUT_BASE"
echo "模型: $MODEL_NAME"
echo "并发数: $CONCURRENCY"
echo "========================================"

# 定义三个脚本
SCRIPTS=(
    "answer_curebench_testset_openrouter.py:original"
    "answer_curebench_testset1_openrouter.py:prompt1"
    "answer_curebench_testset3_openrouter.py:prompt3"
)

# 依次运行三个脚本
for script_info in "${SCRIPTS[@]}"; do
    script_name="${script_info%%:*}"
    prompt_version="${script_info##*:}"
    output_dir="$OUTPUT_BASE/$prompt_version"

    echo ""
    echo "========================================"
    echo "运行: $script_name (Prompt版本: $prompt_version)"
    echo "输出目录: $output_dir"
    echo "========================================"

    mkdir -p "$output_dir"

    uv run --project "$UV_PROJECT" \
        python3 "$SCRIPT_DIR/$script_name" \
        --data-file "$DATA_FILE" \
        --model-name "$MODEL_NAME" \
        --instance-id "$INSTANCE_ID" \
        --output "$output_dir" \
        --concurrency "$CONCURRENCY"

    echo "完成: $script_name"
done

echo ""
echo "========================================"
echo "所有测试完成！"
echo "结果保存在: $OUTPUT_BASE"
echo "========================================"
echo ""
echo "各版本结果目录:"
echo "  - original: $OUTPUT_BASE/original/"
echo "  - prompt1:  $OUTPUT_BASE/prompt1/"
echo "  - prompt3:  $OUTPUT_BASE/prompt3/"
