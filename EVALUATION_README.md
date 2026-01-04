# GPT-4o Rubrics 评估工具

## 功能特性

- ✅ **并发处理**: 支持多个请求同时进行，提高处理速度
- ✅ **增量保存**: 每个条目评估完成后立即保存，防止数据丢失
- ✅ **断点续传**: 程序中断后可以继续处理未完成的条目
- ✅ **无Token限制**: 不设置max_tokens，让模型自由生成完整的评估
- ✅ **错误重试**: 自动重试失败的请求，提高成功率
- ✅ **进度显示**: 实时显示处理进度和状态

## 安装依赖

```bash
pip install aiohttp asyncio
```

## 配置API密钥

设置OpenRouter API密钥：

```bash
export OPENROUTER_API_KEY="your-api-key-here"
```

或者在代码中直接修改：

```python
API_KEY = "sk-or-v1-your-actual-api-key"
```

## 使用方法

### 1. 基本使用

```bash
python3 evaluate_with_gpt4o.py
```

### 2. 自定义配置

编辑代码中的以下参数：

```python
# 并发数（根据API限制调整）
concurrency=3  # 建议从3开始，逐步增加

# 输出文件路径
output_file='/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
```

### 3. 调整并发数

- **低并发 (1-3)**: 稳定但较慢，适合API限制严格的情况
- **中并发 (3-5)**: 平衡速度和稳定性
- **高并发 (5-10)**: 快速但可能触发API限制

## 输出格式

每个评估结果包含：

```json
{
  "sample_id": "sample_id",
  "question": "原始问题",
  "final_answer_length": 1234,
  "evaluation_timestamp": "2025-01-02 10:30:45",
  "processing_duration_seconds": 15.3,
  "success": true,
  "total_score": 25,
  "max_score": 30,
  "rubric_scores": [
    {
      "rubric_id": 1,
      "category": "tool_use",
      "title": "Correct pubmed_search usage",
      "score": 3,
      "max_score": 3,
      "weight": 3,
      "reasoning": "模型正确使用了pubmed_search工具",
      "issues": ""
    }
  ],
  "overall_feedback": "整体表现良好",
  "suggestions": "建议改进引用格式"
}
```

## 监控进度

程序运行时会显示：

```
[1/142] 开始评估: port8000_eval_00013
[1/142] ✓ 完成: port8000_eval_00013 - 总分: 25/30
[2/142] 开始评估: port8000_eval_00014
```

## 断点续传

如果程序中断，重新运行会自动跳过已完成的条目：

```
已完成的条目: 50
跳过已完成条目 1: port8000_eval_00013
...
```

## 故障排除

### 1. API限流
**症状**: 大量请求失败，显示429错误
**解决**: 降低`concurrency`参数，增加请求延迟

### 2. 超时
**症状**: 请求超时错误
**解决**: 增加`timeout`参数（默认300秒）

### 3. JSON解析失败
**症状**: "JSON解析失败"错误
**解决**: 模型返回的内容可能不是纯JSON，代码会自动尝试清理

### 4. 内存不足
**症状**: 程序运行缓慢或崩溃
**解决**: 降低`concurrency`参数

## 费用估算

基于OpenRouter的GPT-4o定价（请查看最新价格）：
- 每个评估大约消耗1000-3000 tokens
- 142个条目 × 2500 tokens ≈ 355,000 tokens
- 输入和输出都需要计费

## 进阶功能

### 自定义评估提示

修改`create_evaluation_prompt`方法来自定义评估标准：

```python
def create_evaluation_prompt(self, question: str, final_answer: str, rubrics: List[Dict]) -> str:
    # 自定义你的评估提示
    prompt = f"""..."""
    return prompt
```

### 批量处理多个文件

```python
files_to_process = [
    ('input1.jsonl', 'output1.jsonl'),
    ('input2.jsonl', 'output2.jsonl'),
    ('input3.jsonl', 'output3.jsonl'),
]

for input_file, output_file in files_to_process:
    await evaluator.process_file(
        input_file=input_file,
        output_file=output_file,
        rubrics_map=rubrics_map,
        concurrency=3
    )
```

## 技术架构

- **异步处理**: 使用asyncio和aiohttp实现高并发
- **连接池**: 复用HTTP连接，提高性能
- **错误处理**: 多层错误处理和重试机制
- **增量写入**: 每个结果立即写入文件，确保数据安全

## 注意事项

1. **API成本**: GPT-4o是付费模型，请注意控制成本
2. **网络稳定**: 确保网络连接稳定，避免大量重试
3. **磁盘空间**: 确保有足够的磁盘空间存储结果
4. **API限制**: 遵守OpenRouter的使用条款和限制