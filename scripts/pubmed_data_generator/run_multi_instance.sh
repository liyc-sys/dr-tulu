#!/bin/bash
# 使用多个DR-Tulu-8B实例并行生成轨迹
# 适用于在多个GPU上部署了多个模型实例的场景

QUESTIONS_FILE="${1:-../../pubmed_training_data/questions_20251217_033030_no_rubrics_incremental.jsonl}"
OUTPUT_DIR="../../pubmed_training_data"
MODEL_NAME="/workspace/math_science_data/lyc/models/DR-Tulu-8B"

# uv环境路径（根据实际情况修改）
UV_VENV="/workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct/.venv"

# 可用端口列表（8个GPU，8个实例）
PORTS=(8000 8001 8002 8009 8004 8005 8006 8007)

# 每个实例处理的并发数
CONCURRENCY_PER_INSTANCE=3

echo "=========================================="
echo "多实例并行轨迹生成"
echo "=========================================="
echo "问题文件: $QUESTIONS_FILE"
echo "模型: $MODEL_NAME"
echo "可用实例: ${#PORTS[@]} 个"
echo "端口: ${PORTS[@]}"
echo "每实例并发: $CONCURRENCY_PER_INSTANCE"
echo "总并发: $((${#PORTS[@]} * CONCURRENCY_PER_INSTANCE))"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="
echo ""

# 计算总问题数
TOTAL_QUESTIONS=$(wc -l < "$QUESTIONS_FILE")
echo "总问题数: $TOTAL_QUESTIONS"

# 计算每个实例处理的问题数
NUM_INSTANCES=${#PORTS[@]}
QUESTIONS_PER_INSTANCE=$((TOTAL_QUESTIONS / NUM_INSTANCES))
REMAINDER=$((TOTAL_QUESTIONS % NUM_INSTANCES))

echo "每实例处理: ~$QUESTIONS_PER_INSTANCE 个问题"
echo ""

# 创建临时文件目录
TEMP_DIR=$(mktemp -d)
echo "临时目录: $TEMP_DIR"

# 分割问题文件
echo "分割问题文件..."
split -l $QUESTIONS_PER_INSTANCE "$QUESTIONS_FILE" "$TEMP_DIR/questions_part_"

# 重命名分割文件
i=0
for file in "$TEMP_DIR"/questions_part_*; do
    mv "$file" "$TEMP_DIR/questions_part_$(printf "%02d" $i).jsonl"
    i=$((i + 1))
done

echo "✓ 已分割为 $i 个文件"
echo ""

# 启动多个进程
echo "启动生成进程..."
PIDS=()
for i in "${!PORTS[@]}"; do
    port=${PORTS[$i]}
    part_file="$TEMP_DIR/questions_part_$(printf "%02d" $i).jsonl"
    
    if [ ! -f "$part_file" ]; then
        echo "⚠ 文件 $part_file 不存在，跳过端口 $port"
        continue
    fi
    
    num_questions=$(wc -l < "$part_file")
    if [ "$num_questions" -eq 0 ]; then
        echo "⚠ 文件 $part_file 为空，跳过端口 $port"
        continue
    fi
    
    echo "启动实例 $((i+1))/${NUM_INSTANCES}: 端口 $port, 处理 $num_questions 个问题"
    
    # 使用uv环境运行
    if [ -d "$UV_VENV" ]; then
        source "$UV_VENV/bin/activate"
        python generate_trajectory_from_questions.py \
            --questions-file "$part_file" \
            --local-model-url "http://localhost:$port/v1" \
            --model-name "${MODEL_NAME}" \
            --instance-id "port${port}" \
            --concurrency $CONCURRENCY_PER_INSTANCE \
            --output "$OUTPUT_DIR" \
            > "$TEMP_DIR/log_port_${port}.txt" 2>&1 &
        deactivate
    else
        # 如果uv环境不存在，直接使用python
        python generate_trajectory_from_questions.py \
            --questions-file "$part_file" \
            --local-model-url "http://localhost:$port/v1" \
            --model-name "${MODEL_NAME}" \
            --instance-id "port${port}" \
            --concurrency $CONCURRENCY_PER_INSTANCE \
            --output "$OUTPUT_DIR" \
            > "$TEMP_DIR/log_port_${port}.txt" 2>&1 &
    fi
    
    PIDS+=($!)
done

echo ""
echo "已启动 ${#PIDS[@]} 个生成进程"
echo "PID: ${PIDS[@]}"
echo ""
echo "监控日志："
for i in "${!PORTS[@]}"; do
    port=${PORTS[$i]}
    echo "  tail -f $TEMP_DIR/log_port_${port}.txt"
done
echo ""

# 等待所有进程完成
echo "等待所有进程完成..."
failed=0
for i in "${!PIDS[@]}"; do
    pid=${PIDS[$i]}
    port=${PORTS[$i]}
    
    wait $pid
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✓ 实例 $((i+1)) (端口 $port, PID $pid) 完成"
    else
        echo "✗ 实例 $((i+1)) (端口 $port, PID $pid) 失败 (退出码: $exit_code)"
        failed=$((failed + 1))
    fi
done

echo ""
echo "=========================================="
echo "所有进程已完成"
echo "=========================================="
echo "成功: $((${#PIDS[@]} - failed))/${#PIDS[@]}"
echo "失败: $failed/${#PIDS[@]}"
echo ""

# 合并结果
echo "合并生成的轨迹文件..."
MERGED_FILE="$OUTPUT_DIR/pubmed_trajectory_$(date +%Y%m%d_%H%M%S)_${MODEL_NAME}_multi_instance.jsonl"

# 找到所有生成的轨迹文件并合并
find "$OUTPUT_DIR" -name "pubmed_trajectory_*_${MODEL_NAME}_port*_incremental.jsonl" -type f | while read file; do
    cat "$file" >> "$MERGED_FILE"
done

if [ -f "$MERGED_FILE" ]; then
    line_count=$(wc -l < "$MERGED_FILE")
    echo "✓ 已合并到: $MERGED_FILE"
    echo "  总样本数: $line_count"
else
    echo "⚠ 未找到可合并的文件"
fi

echo ""
echo "保留日志和分割文件在: $TEMP_DIR"
echo "如需清理: rm -rf $TEMP_DIR"
echo ""
echo "=========================================="
echo "生成完成！"
echo "=========================================="

