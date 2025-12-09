# LiteLLM Connection Error 诊断和修复指南

## 问题描述

训练时出现以下错误：
```
Error in run_litellm_async: litellm.APIError: APIError: OpenAIException - Connection error. LiteLLM Retried: 5 times
Generated instance-wise adaptive rubrics: None
```

## 问题定位

### 错误发生位置

1. **代码文件**: `open_instruct/search_rewards/utils/run_utils.py`
   - 函数: `run_litellm_async()` (第237-303行)
   - 问题: LiteLLM无法连接到OpenRouter API

2. **调用链路**:
   ```
   grpo_fast.py (第2850行) 
   -> _generate_instance_wise_adaptive_rubrics()
   -> generate_instance_wise_adaptive_rubrics() (rubric_utils.py 第376行)
   -> run_litellm_async() (run_utils.py 第237行)
   -> litellm.acompletion() 连接失败
   ```

### 配置信息（来自train_dr_tulu.sh）

```bash
export http_proxy="http://httpproxy.glm.ai:8888"
export https_proxy="http://httpproxy.glm.ai:8888"
export OPENAI_API_KEY="sk-or-v1-..."
export OPENAI_API_BASE="https://openrouter.ai/api/v1"
export RUBRIC_JUDGE_MODEL=gpt-4.1-mini
```

## 可能的原因

### 1. 代理问题 (最可能)
- 代理服务器 `httpproxy.glm.ai:8888` 不可用
- 代理阻止了HTTPS连接到openrouter.ai
- 代理超时设置太短

### 2. API配置问题
- OpenRouter API key无效或过期
- OPENAI_API_BASE URL错误
- 模型名称不正确（gpt-4.1-mini可能不存在）

### 3. 网络问题
- 防火墙阻止连接
- DNS解析失败
- 网络不稳定导致超时

### 4. 并发问题
- 并发请求过多触发rate limiting
- 同时发起的请求超过了API限制

## 测试方法

我已经为你创建了两个测试脚本：

### 1. 基础连接测试
```bash
cd /Users/liyc/Desktop/dr-tulu/rl/open-instruct
python test_litellm_connection.py
```

这个脚本会测试：
- ✅ 基本LiteLLM连接
- ✅ 不使用代理的连接
- ✅ 调试模式
- ✅ Rubric生成模拟

### 2. 完整Rubric生成测试
```bash
cd /Users/liyc/Desktop/dr-tulu/rl/open-instruct
python test_rubric_generation.py
```

这个脚本会测试：
- ✅ 代理连接性
- ✅ LiteLLM直接调用
- ✅ 简单rubric生成
- ✅ 带existing rubrics的生成

## 修复方案

### 方案1: 禁用代理（快速测试）

在 `train_dr_tulu.sh` 中注释掉代理设置：

```bash
# export http_proxy="http://httpproxy.glm.ai:8888"
# export https_proxy="http://httpproxy.glm.ai:8888"
# export no_proxy="127.0.0.1,localhost,platform.glm.ai,::1,$no_proxy"
```

### 方案2: 修改模型名称

OpenRouter的模型名称格式可能需要带provider前缀：

```bash
# 原来的
export RUBRIC_JUDGE_MODEL=gpt-4.1-mini

# 改为以下之一
export RUBRIC_JUDGE_MODEL=openai/gpt-4-turbo-preview
export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini
export RUBRIC_JUDGE_MODEL=anthropic/claude-3-haiku
```

### 方案3: 增加超时时间

在 `run_utils.py` 中修改默认超时：

```python
# 第284-286行
chat_kwargs["timeout"] = chat_kwargs.get(
    "timeout", float(os.environ.get("LITELLM_DEFAULT_TIMEOUT", "600"))
)

# 改为更长的超时
chat_kwargs["timeout"] = chat_kwargs.get(
    "timeout", float(os.environ.get("LITELLM_DEFAULT_TIMEOUT", "1200"))  # 20分钟
)
```

或在训练脚本中设置：
```bash
export LITELLM_DEFAULT_TIMEOUT=1200
```

### 方案4: 修改重试策略

在 `run_utils.py` 第267行：

```python
# 增加重试次数和使用fallback
chat_kwargs["num_retries"] = chat_kwargs.get("num_retries", 10)  # 从5改为10
chat_kwargs["fallbacks"] = chat_kwargs.get("fallbacks", ["openai/gpt-4o-mini"])
```

### 方案5: 临时禁用adaptive rubric（训练继续）

如果rubric不是必需的，可以临时禁用：

在 `train_dr_tulu.sh` 中：
```bash
--apply_adaptive_rubric_reward false \  # 改为false
```

## 调试命令

### 1. 测试代理连接
```bash
# 测试代理是否能访问OpenRouter
curl -x http://httpproxy.glm.ai:8888 -I https://openrouter.ai

# 测试不使用代理
curl -I https://openrouter.ai
```

### 2. 测试API key
```bash
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer sk-or-v1-..." \
  -H "HTTP-Referer: http://localhost:3000" \
  -H "X-Title: Test"
```

### 3. 手动测试LiteLLM
```python
import litellm
litellm.set_verbose = True

response = litellm.completion(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    api_key="sk-or-v1-...",
    api_base="https://openrouter.ai/api/v1"
)
print(response)
```

## 推荐方案

**优先级排序**：

1. 🥇 **先运行测试脚本确认问题**
   ```bash
   python test_litellm_connection.py
   ```

2. 🥈 **如果是代理问题，尝试禁用代理**
   
3. 🥉 **如果是模型名称问题，改为标准的OpenRouter模型名**
   ```bash
   export RUBRIC_JUDGE_MODEL=openai/gpt-4o-mini
   ```

4. 🏅 **增加超时和重试次数**
   ```bash
   export LITELLM_DEFAULT_TIMEOUT=1200
   ```

## 预防措施

### 1. 添加更好的错误处理

在 `rubric_utils.py` 的 `generate_instance_wise_adaptive_rubrics` 函数中：

```python
try:        
    resp = await run_litellm_async(
            model_name=model_name,
            user_prompt=prompt,
        )
    
    # 检查返回值
    if not resp or resp == "":
        print(f"Warning: Empty response from LiteLLM for model {model_name}")
        return None
    
    obj = extract_json_from_response(resp)
    print(f"Generated instance-wise adaptive rubrics: {obj}")
except Exception as e:
    print(f"Error generating instance-wise adaptive rubrics: {e}")
    return None
```

### 2. 添加连接预检查

在训练开始前，先测试LiteLLM连接：

```python
async def check_litellm_connection():
    try:
        resp = await run_litellm_async(
            model_name=os.environ.get("RUBRIC_JUDGE_MODEL"),
            user_prompt="Hello",
            max_tokens=10,
            timeout=30
        )
        if resp:
            print("✅ LiteLLM connection check passed")
            return True
        else:
            print("❌ LiteLLM connection check failed: empty response")
            return False
    except Exception as e:
        print(f"❌ LiteLLM connection check failed: {e}")
        return False
```

## 相关文件

- 训练脚本: `train_dr_tulu.sh`
- LiteLLM调用: `open_instruct/search_rewards/utils/run_utils.py`
- Rubric生成: `open_instruct/search_rewards/utils/rubric_utils.py`
- 主训练逻辑: `open_instruct/grpo_fast.py`

## 联系支持

如果以上方法都不能解决问题，可以：

1. 检查OpenRouter的状态页面: https://status.openrouter.ai/
2. 查看OpenRouter文档: https://openrouter.ai/docs
3. 提交issue到LiteLLM: https://github.com/BerriAI/litellm/issues

