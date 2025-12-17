#!/bin/bash
# 诊断分布式训练环境的脚本

echo "========== 系统信息 =========="
echo "主机名: $(hostname)"
echo "日期: $(date)"
echo ""

echo "========== GPU 状态 =========="
nvidia-smi
echo ""

echo "========== GPU 详细信息 =========="
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv
echo ""

echo "========== 占用 GPU 的进程 =========="
nvidia-smi --query-compute-apps=pid,used_memory,gpu_name --format=csv 2>/dev/null || echo "没有进程在使用GPU"
echo ""

echo "========== NCCL 相关环境变量 =========="
env | grep -E "NCCL|CUDA|MASTER|RANK|WORLD|LOCAL" | sort
echo ""

echo "========== PyTorch 和 CUDA 版本 =========="
cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct
source .venv/bin/activate
python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
print(f'NCCL version: {torch.cuda.nccl.version()}')
print(f'GPU count: {torch.cuda.device_count()}')
for i in range(torch.cuda.device_count()):
    print(f'  GPU {i}: {torch.cuda.get_device_name(i)}')
    print(f'    Memory: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB')
"
echo ""

echo "========== 测试 GPU 间通信 =========="
python -c "
import torch
import torch.distributed as dist
import os

n_gpus = torch.cuda.device_count()
print(f'检测到 {n_gpus} 个 GPU')

# 测试每个 GPU 是否可访问
for i in range(n_gpus):
    try:
        torch.cuda.set_device(i)
        x = torch.randn(100, 100, device=f'cuda:{i}')
        print(f'  GPU {i}: ✅ 可用')
    except Exception as e:
        print(f'  GPU {i}: ❌ 错误 - {e}')
"
echo ""

echo "========== 检查端口占用 (58000-60000) =========="
ss -tlnp 2>/dev/null | grep -E ':58[0-9]{3}|:59[0-9]{3}' || netstat -tlnp 2>/dev/null | grep -E ':58[0-9]{3}|:59[0-9]{3}' || echo "端口范围内无监听"
echo ""

echo "========== 检查 Ray 进程 =========="
ps aux | grep -E "[r]ay|[p]ython.*grpo" | head -20
echo ""

echo "========== 系统资源 =========="
echo "内存使用:"
free -h
echo ""
echo "CPU 核心数: $(nproc)"
echo ""

echo "========== DeepSpeed 和关键包版本 =========="
pip list | grep -E "deepspeed|transformers|accelerate|ray|vllm|peft|torch"
echo ""

echo "========== 诊断完成 =========="

