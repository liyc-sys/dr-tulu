# DoRA (Weight-Decomposed Low-Rank Adaptation) 使用指南

## 概述

DoRA是LoRA的一种改进版本，通过将权重分解为"幅度"和"方向"两部分来优化，可以在减少计算资源的同时保持或提升性能。

## 已完成的修改

1. **ModelConfig** (`open_instruct/model_utils.py`)
   - 添加了 `use_dora: bool = False` 参数

2. **PPO训练代码** (`open_instruct/ppo_vllm_thread_ray_gtrl.py`)
   - 在 `from_pretrained` 方法中添加了DoRA支持
   - 对policy和ref_policy模型应用PEFT/DoRA

3. **GRPO训练代码** (`open_instruct/grpo_vllm_thread_ray_gtrl.py`)
   - 在 `from_pretrained` 方法中添加了DoRA支持
   - 对policy和ref_policy模型应用PEFT/DoRA

4. **GRPO Fast训练代码** (`open_instruct/grpo_fast.py`)
   - 在 `from_pretrained` 方法中添加了DoRA支持
   - 对policy和ref_policy模型应用PEFT/DoRA
   - 支持与grpo_vllm_thread_ray_gtrl.py相同的PEFT配置

## 使用方法

### 1. 在配置文件中启用DoRA

```yaml
# 启用PEFT和DoRA
use_peft: true
use_dora: true

# LoRA参数配置
lora_r: 16          # 秩，越小参数越少（建议8-32）
lora_alpha: 32      # 通常设为2倍lora_r
lora_dropout: 0.05  # Dropout率

# 可选：指定目标模块（不指定会自动检测）
# lora_target_modules: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
```

### 2. 命令行参数

对于 `ppo_vllm_thread_ray_gtrl.py` 或 `grpo_vllm_thread_ray_gtrl.py`：

```bash
python open_instruct/ppo_vllm_thread_ray_gtrl.py \
    --model_name_or_path meta-llama/Llama-2-7b-hf \
    --use_peft \
    --use_dora \
    --lora_r 16 \
    --lora_alpha 32 \
    --lora_dropout 0.05 \
    # ... 其他参数
```

对于 `grpo_fast.py`（推荐用于生产环境）：

```bash
python open_instruct/grpo_fast.py \
    --model_name_or_path meta-llama/Llama-2-7b-hf \
    --use_peft \
    --use_dora \
    --lora_r 16 \
    --lora_alpha 32 \
    --lora_dropout 0.05 \
    # ... 其他参数
```

## 计算资源需求

### 不使用DoRA（全参数微调）
- **7B模型**: 需要2-4个A100 40GB GPU，或1个A100 80GB GPU
- **13B模型**: 需要4-8个A100 40GB GPU，或2个A100 80GB GPU
- **70B模型**: 需要8+个A100 40GB GPU

### 使用DoRA + DeepSpeed Stage 3
- **7B模型**: 
  - 1个RTX 3090 (24GB) 或 1个A100 40GB GPU
  - 内存节省：约70-80%的可训练参数
- **13B模型**: 
  - 1-2个A100 40GB GPU，或1个A100 80GB GPU
- **70B模型**: 
  - 4-8个A100 40GB GPU（相比全参数微调减少50%+）

### 进一步优化（DoRA + 量化）
如果启用4-bit或8-bit量化，可以进一步减少内存：
```yaml
use_peft: true
use_dora: true
load_in_4bit: true  # 或 load_in_8bit: true
```

## 性能影响

- **参数效率**: DoRA通常只需要训练原模型0.1-1%的参数
- **训练速度**: 由于参数更少，训练速度可能更快
- **模型性能**: DoRA通常能达到或超过全参数微调的性能
- **内存使用**: 显著减少，特别是在使用DeepSpeed Stage 3时

## 示例配置文件和脚本

参考以下示例配置文件：
- `configs/train_configs/ppo/ppo_with_dora_example.yaml`
- `configs/train_configs/grpo/grpo_with_dora_example.yaml`

参考以下示例训练脚本：
- `train_dr_tulu_with_dora.sh` - 使用 DoRA 训练 DR-Tulu 的完整示例

### 使用 DoRA 训练脚本

```bash
# 使用 DoRA 训练（默认 8 GPU）
bash train_dr_tulu_with_dora.sh

# 使用 DoRA 训练（单 GPU 模式）
NUM_GPUS=1 bash train_dr_tulu_with_dora.sh

# 使用 DoRA 训练（自定义 GPU 数量）
NUM_GPUS=4 bash train_dr_tulu_with_dora.sh
```

### 快速对比：全参数训练 vs DoRA

| 特性 | 全参数训练 (`train_dr_tulu.sh`) | DoRA 训练 (`train_dr_tulu_with_dora.sh`) |
|------|--------------------------------|------------------------------------------|
| 训练参数量 | 100% | 0.1-1% |
| GPU 内存需求 | 高 | 显著降低（约 70-80%） |
| 训练速度 | 基准 | 相似或更快 |
| 模型性能 | 基准 | 通常相当或更好 |
| 保存的权重 | 完整模型 | Adapter 权重（需合并到基础模型） |

## 注意事项

1. **DeepSpeed兼容性**: DoRA与DeepSpeed完全兼容，建议使用DeepSpeed Stage 3以获得最大内存节省
2. **参考模型**: ref_policy也会应用相同的PEFT配置（但处于推理模式），确保一致性
3. **保存模型**: 使用DoRA训练后，保存的是adapter权重，可以通过`merge_lora.py`合并到基础模型
4. **目标模块**: 如果不指定`lora_target_modules`，代码会根据模型架构自动检测（支持Llama、Mistral等常见架构）

## 故障排除

如果遇到问题：
1. 确保PEFT版本 >= 0.13.2（支持DoRA）
2. 检查模型架构是否被正确识别
3. 如果自动检测失败，手动指定`lora_target_modules`
4. 对于非常大的模型，考虑降低`lora_r`值（如8或16）

