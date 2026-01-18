# Rubrics评估工具使用说明

## 功能特点

- ✅ **并发处理**: 支持多个请求同时进行，提高处理速度
- ✅ **增量保存**: 每处理10条数据自动保存一次，防止数据丢失  
- ✅ **失败重试**: API调用失败自动重试，支持指数退避
- ✅ **断点续跑**: 程序中断后重新运行会自动跳过已评估的项目
- ✅ **二值判断**: 强制模型输出"合理"或"不合理"，避免模糊回答

## 安装依赖

```bash
pip install aiohttp
```

## 使用方法

### 1. 设置API密钥

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
```

### 2. 运行评估脚本

```bash
python rubrics_evaluator.py
```

### 3. 自定义参数

编辑 `rubrics_evaluator.py` 中的 `main()` 函数:

```python
MAX_CONCURRENT = 5   # 并发数，根据API限制调整
MAX_RETRIES = 3      # 失败重试次数
INPUT_FILE = "path/to/your/input.jsonl"
OUTPUT_FILE = "path/to/output/results.json"
```

## 输出格式

评估结果保存在JSON文件中，每条记录包含:

```json
{
  "sample_id": {
    "question": "问题文本",
    "content_rubrics": {...},
    "response": "模型原始回答",
    "is_reasonable": true,
    "evaluated": true,
    "timestamp": "2025-01-04T..."
  }
}
```

## 断点续跑

如果程序因网络问题或其他原因中断，只需重新运行即可。程序会自动:
1. 加载已有的评估结果
2. 跳过已评估的项目
3. 继续评估剩余项目

## 注意事项

1. 确保OpenRouter账户有足够的API额度
2. 根据网络状况调整并发数，避免触发API限流
3. 评估大量数据时建议分批进行
4. 结果文件会覆盖保存，请备份重要数据