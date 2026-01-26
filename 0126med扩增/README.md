# 医学数据扩增脚本

## 功能说明

使用OpenRouter调用GPT-4模型，将医学查询问题改写成3种不同风格，实现1+3=4倍数据扩增。

## 三种改写风格

1. **style1_formal (正式学术风格)**: 使用更专业的学术用语，句式更加严谨规范
2. **style2_concise (简洁直接风格)**: 去除冗余表达，语言更加精炼
3. **style3_stepwise (步骤引导风格)**: 将查询过程拆分成更清晰的步骤说明

## 使用方法

1. 安装依赖:
```bash
pip install -r requirements.txt
```

2. 设置OpenRouter API Key:
```bash
export OPENROUTER_API_KEY='your-api-key-here'
```

3. 运行脚本:
```bash
python main.py
```

## 增量保存特性

- 脚本支持增量保存，如果中断可以继续运行
- 进度信息保存在 `progress.json` 文件中
- 每处理完一条数据就会保存到输出文件

## 输出文件

- `MedBrowseComp_augmented.csv`: 扩增后的数据（包含原始数据和3种风格的改写）
- `progress.json`: 处理进度记录
