# 7B RL模型训练硬件推荐

## RL训练的特殊性

RL训练比普通SFT训练更复杂，需要同时加载多个模型：

1. **Policy模型** (训练，需要梯度) - 7B
2. **Value模型** (训练，需要梯度) - 通常也是7B或更小
3. **Reference Policy模型** (推理，冻结) - 7B
4. **Reward模型** (推理，冻结，可选) - 通常7B或更小
5. **vLLM引擎** (用于生成) - 需要额外的7B模型副本

## 内存需求计算（7B模型，bf16）

### 单个7B模型的内存占用：
- **模型参数**: 7B × 2 bytes (bf16) = 14 GB
- **优化器状态** (AdamW): 7B × 8 bytes = 56 GB (参数 + 动量 + 方差)
- **梯度**: 7B × 2 bytes = 14 GB
- **激活值**: 取决于batch size和序列长度，通常 5-20 GB

**单个模型总内存**: ~90-100 GB (全参数微调)

### RL训练总内存需求：

#### 方案1: 不使用DoRA（全参数微调）
```
Policy模型:     90 GB (参数 + 优化器 + 梯度 + 激活)
Value模型:      90 GB (参数 + 优化器 + 梯度 + 激活)
Ref Policy:     14 GB (仅参数，推理模式)
Reward模型:     14 GB (仅参数，推理模式)
vLLM引擎:       14 GB (生成用)
激活值缓存:     10-30 GB
系统开销:       5-10 GB
─────────────────────────
总计:           ~237-262 GB
```

**推荐配置**: 
- **2× A100 80GB** (160GB总显存，需要ZeRO Stage 3)
- **4× A100 40GB** (160GB总显存，需要ZeRO Stage 3)
- **8× RTX 3090 24GB** (192GB总显存，需要ZeRO Stage 3，可能较慢)

#### 方案2: 使用DoRA (推荐) ⭐

使用DoRA后，可训练参数减少到约0.1-1%：

```
Policy模型 (DoRA):   ~20 GB (大部分参数冻结，只训练adapter)
Value模型 (DoRA):    ~20 GB
Ref Policy:          14 GB (推理)
Reward模型:          14 GB (推理)
vLLM引擎:            14 GB
激活值缓存:          10-20 GB
系统开销:            5-10 GB
─────────────────────────
总计:                ~97-113 GB
```

**推荐配置**:
- **1× A100 80GB** ✅ (最佳选择，单卡即可)
- **2× A100 40GB** ✅ (如果单卡不够，双卡更稳定)
- **2× RTX 3090 24GB** ⚠️ (可能较紧张，需要仔细调优)

#### 方案3: DoRA + DeepSpeed ZeRO Stage 3

使用ZeRO Stage 3可以进一步减少内存：

```
每个模型参数分片到多个GPU
优化器状态分片
梯度分片
─────────────────────────
单卡内存需求:    ~30-50 GB
```

**推荐配置**:
- **2× A100 40GB** ✅ (非常稳定)
- **2× RTX 3090 24GB** ✅ (可行，但需要仔细配置)
- **4× RTX 3090 24GB** ✅ (更稳定，有冗余)

## 具体硬件推荐

### 🥇 最佳选择：1× A100 80GB + DoRA + DeepSpeed Stage 3

**为什么推荐**:
- ✅ 单卡即可运行，无需多卡通信开销
- ✅ 80GB显存充足，有缓冲空间
- ✅ 训练速度快（A100性能强）
- ✅ 成本相对较低（相比多卡方案）

**配置**:
```yaml
use_peft: true
use_dora: true
lora_r: 16
deepspeed_stage: 3
per_device_train_batch_size: 1
gradient_accumulation_steps: 8
```

### 🥈 次优选择：2× A100 40GB + DoRA + DeepSpeed Stage 3

**为什么推荐**:
- ✅ 双卡提供更多显存缓冲
- ✅ 可以支持更大的batch size
- ✅ 训练更稳定
- ✅ 如果单卡不够，这是最佳备选

**配置**:
```yaml
use_peft: true
use_dora: true
lora_r: 16
deepspeed_stage: 3
per_device_train_batch_size: 2
gradient_accumulation_steps: 4
world_size: 2
```

### 🥉 经济选择：2× RTX 3090 24GB + DoRA + DeepSpeed Stage 3

**为什么推荐**:
- ✅ 成本较低（二手市场约$2000-3000）
- ✅ 24GB显存勉强够用
- ⚠️ 需要仔细调优配置
- ⚠️ 训练速度较慢（相比A100）

**配置**:
```yaml
use_peft: true
use_dora: true
lora_r: 8  # 降低rank以节省内存
deepspeed_stage: 3
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
local_rollout_batch_size: 32  # 降低batch size
vllm_gpu_memory_utilization: 0.85  # 降低vLLM内存使用
```

## 不推荐的配置

### ❌ 单卡RTX 3090 24GB（不使用DoRA）
- 显存不足，无法运行

### ❌ 单卡A100 40GB（不使用DoRA）
- 可能可以运行，但非常紧张，容易OOM

### ❌ 不使用DeepSpeed Stage 3
- 即使使用DoRA，单卡可能也不够

## 性能对比

| 配置 | 训练速度 | 稳定性 | 成本 | 推荐度 |
|------|---------|--------|------|--------|
| 1× A100 80GB + DoRA | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 2× A100 40GB + DoRA | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| 2× RTX 3090 + DoRA | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| 2× A100 80GB (无DoRA) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| 4× A100 40GB (无DoRA) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |

## 实际测试建议

1. **先用最小配置测试**:
   - 单卡 + DoRA + DeepSpeed Stage 3
   - 小batch size
   - 短序列长度

2. **逐步增加**:
   - 如果稳定，增加batch size
   - 增加序列长度
   - 增加rollout batch size

3. **监控指标**:
   - GPU内存使用率（应该<90%）
   - 训练速度（tokens/秒）
   - 是否出现OOM错误

## 总结

**强烈推荐**: **1× A100 80GB + DoRA + DeepSpeed Stage 3**

这是性价比最高的方案，单卡即可稳定训练7B RL模型，训练速度快，成本相对较低。

如果预算有限，可以考虑 **2× RTX 3090 + DoRA + DeepSpeed Stage 3**，但需要更多调优工作。

