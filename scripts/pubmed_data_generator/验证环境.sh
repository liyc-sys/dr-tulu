#!/bin/bash
# 验证所有环境是否正常

echo "=========================================="
echo "环境验证脚本"
echo "=========================================="
echo ""

# 验证uv环境
UV_VENV="/workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct/.venv"
echo "1. 检查uv环境..."
if [ -d "$UV_VENV" ]; then
    echo "   ✓ uv环境存在: $UV_VENV"
else
    echo "   ✗ uv环境不存在: $UV_VENV"
fi
echo ""

# 验证MCP服务器
echo "2. 检查MCP服务器（端口8003）..."
if curl -s http://127.0.0.1:8003/mcp/health > /dev/null 2>&1; then
    echo "   ✓ MCP服务器正常"
else
    echo "   ✗ MCP服务器无响应"
fi
echo ""

# 验证模型实例
echo "3. 检查DR-Tulu-8B模型实例..."
PORTS=(8000 8001 8002 8009 8004 8005 8006 8007)
OK_COUNT=0
FAIL_COUNT=0

for port in "${PORTS[@]}"; do
    if curl -s http://localhost:$port/v1/models > /dev/null 2>&1; then
        echo "   ✓ 端口 $port 正常"
        OK_COUNT=$((OK_COUNT + 1))
    else
        echo "   ✗ 端口 $port 无响应"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done
echo ""

# 总结
echo "=========================================="
echo "验证结果"
echo "=========================================="
echo "模型实例: $OK_COUNT/${#PORTS[@]} 个正常"

if [ $FAIL_COUNT -eq 0 ] && [ -d "$UV_VENV" ]; then
    echo ""
    echo "✓ 所有环境正常，可以开始生成轨迹！"
    echo ""
    echo "运行命令："
    echo "  cd /workspace/math_science_data/lyc/1205/dr-tulu/scripts/pubmed_data_generator"
    echo "  bash run_multi_instance.sh /path/to/questions.jsonl"
else
    echo ""
    echo "⚠ 存在问题，请检查："
    if [ $FAIL_COUNT -gt 0 ]; then
        echo "  - 启动失败的模型实例"
    fi
    if [ ! -d "$UV_VENV" ]; then
        echo "  - 设置uv环境路径"
    fi
fi
echo ""

