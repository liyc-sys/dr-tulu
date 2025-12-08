#!/bin/bash
# 诊断虚拟环境内的包版本

cd /workspace/math_science_data/lyc/1205/dr-tulu/rl/open-instruct

echo "========== 虚拟环境内的关键包版本 =========="
uv run pip list | grep -E "deepspeed|transformers|accelerate|ray|vllm|peft|torch|bitsandbytes"

echo ""
echo "========== 测试 DeepSpeed 分布式初始化 =========="
uv run python -c "
import os
import torch
import deepspeed

print(f'DeepSpeed version: {deepspeed.__version__}')
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'GPU count: {torch.cuda.device_count()}')

# 检查 NCCL
print(f'NCCL version: {torch.cuda.nccl.version()}')
print(f'NCCL available: {torch.distributed.is_nccl_available()}')
"

echo ""
echo "========== 测试简单的 4 GPU 分布式通信 =========="
uv run python -c "
import os
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import time

def test_worker(rank, world_size):
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '29500'
    os.environ['RANK'] = str(rank)
    os.environ['WORLD_SIZE'] = str(world_size)
    os.environ['LOCAL_RANK'] = str(rank)
    
    try:
        dist.init_process_group(backend='nccl', rank=rank, world_size=world_size, timeout=torch.distributed.timedelta(seconds=30))
        torch.cuda.set_device(rank)
        
        # 简单的 all_reduce 测试
        tensor = torch.ones(1).cuda()
        dist.all_reduce(tensor)
        
        print(f'Rank {rank}: ✅ 分布式通信成功, all_reduce result = {tensor.item()}')
        dist.destroy_process_group()
    except Exception as e:
        print(f'Rank {rank}: ❌ 失败 - {e}')

if __name__ == '__main__':
    world_size = 4
    print(f'测试 {world_size} 个 GPU 的 NCCL 通信...')
    mp.spawn(test_worker, args=(world_size,), nprocs=world_size, join=True)
    print('所有 worker 测试完成!')
"

echo ""
echo "========== 检查 Ray 能否正常启动 =========="
uv run python -c "
import ray
ray.init(num_gpus=4, ignore_reinit_error=True)
print(f'Ray initialized with {ray.available_resources()}')
ray.shutdown()
print('Ray shutdown successfully')
"

echo ""
echo "========== 检查 PEFT/DoRA =========="
uv run python -c "
from peft import LoraConfig
print('PEFT import successful')
config = LoraConfig(r=16, lora_alpha=32, use_dora=True)
print(f'DoRA config: {config}')
"

echo ""
echo "========== 诊断完成 =========="

