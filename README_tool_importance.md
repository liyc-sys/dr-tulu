# 工具调用重要性分析脚本使用说明

## 功能概述
这个脚本调用OpenRouter GPT-4o来分析interleaved_text中最重要的2-3个工具调用步骤。

## 主要特性
- ✅ 支持断点续跑（中断后可以继续处理）
- ✅ 20个并发处理，提高效率
- ✅ 增量保存，每批处理完立即保存
- ✅ 智能解析GPT-4o返回的步骤编号
- ✅ 详细的进度显示和错误处理

## 使用方法

### 1. 安装依赖
```bash
pip install aiohttp asyncio
```

### 2. 设置API密钥
```bash
export OPENROUTER_API_KEY="your_api_key_here"
```

### 3. 运行脚本
```bash
python analyze_tool_importance.py
```

## 输出文件格式

每个记录的输出包含：
- `sample_id`: 样本ID
- `question`: 原始问题  
- `total_steps`: 总工具调用步骤数
- `important_steps`: 重要的步骤编号列表（如[1,3,5]）
- `analysis_response`: GPT-4o的完整分析结果
- `tool_calls_summary`: 所有工具调用的摘要
- `status`: 处理状态（success/error）
- `processed_time`: 处理时间

## 步骤编号说明

脚本会提取interleaved_text中所有的`<call_tool name="xxx">`标签，从1开始编号。

例如，如果`important_steps: [2,5]`，表示第2个和第5个工具调用最重要。

## 断点续跑

如果脚本中断，重新运行时会：
1. 自动检测已处理的记录
2. 跳过已完成的记录
3. 继续处理剩余的记录

## 性能优化

- 20个并发请求
- 每批处理完立即保存（防止数据丢失）
- 自动重试机制（3次重试）
- 指数退避策略

## 监控进度

脚本运行时会显示：
- 当前处理的批次和进度
- 每批的成功/失败统计
- 最终的汇总报告

## 故障排除

1. **API密钥错误**: 检查OPENROUTER_API_KEY环境变量
2. **网络超时**: 脚本会自动重试，如果持续失败请检查网络连接
3. **解析失败**: 查看输出文件中的error字段了解具体原因