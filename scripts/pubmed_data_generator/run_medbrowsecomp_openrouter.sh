#!/bin/bash
# MedBrowseComp 评测 - 使用 OpenRouter API (seed1.8)
# 所有路径均为相对路径，基于本脚本所在位置推算

set -e

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 项目根目录: scripts/pubmed_data_generator/../../ = dr-tulu/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 配置
UV_PROJECT="$PROJECT_ROOT/rl/open-instruct"
DATA_DIR="$PROJECT_ROOT/训练和benchmark数据0120"
OUTPUT_BASE="$PROJECT_ROOT/medbrowsecomp_comparison_results"
MODEL_NAME="seed1.8"
CONCURRENCY=5

# 检查环境变量
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "错误: 请设置环境变量 OPENROUTER_API_KEY"
    echo "  export OPENROUTER_API_KEY=your_key_here"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_BASE"

# 合并两个 CSV 文件
MERGED_CSV="$OUTPUT_BASE/MedBrowseComp_605_merged.csv"
echo "合并数据集..."
head -1 "$DATA_DIR/MedBrowseComp_605_part1.csv" > "$MERGED_CSV"
tail -n +2 "$DATA_DIR/MedBrowseComp_605_part1.csv" >> "$MERGED_CSV"
tail -n +2 "$DATA_DIR/MedBrowseComp_605_part2.csv" >> "$MERGED_CSV"
MERGED_COUNT=$(wc -l < "$MERGED_CSV")
echo "合并完成: $MERGED_CSV (共 $((MERGED_COUNT - 1)) 条数据)"

echo ""
echo "========================================"
echo "MedBrowseComp 评测 - OpenRouter ($MODEL_NAME)"
echo "========================================"
echo "项目根目录: $PROJECT_ROOT"
echo "数据文件:   $MERGED_CSV"
echo "输出目录:   $OUTPUT_BASE/openrouter_${MODEL_NAME}"
echo "并发数:     $CONCURRENCY"
echo "========================================"

# 运行 OpenRouter 版本
uv run --project "$UV_PROJECT" \
    python3 "$SCRIPT_DIR/answer_medbrowsecomp_openrouter.py" \
    --data-file "$MERGED_CSV" \
    --model-name "$MODEL_NAME" \
    --instance-id "openrouter_${MODEL_NAME}" \
    --output "$OUTPUT_BASE/openrouter_${MODEL_NAME}" \
    --concurrency "$CONCURRENCY"

echo ""
echo "========================================"
echo "评测完成！"
echo "结果保存在: $OUTPUT_BASE/openrouter_${MODEL_NAME}/"
echo "========================================"
