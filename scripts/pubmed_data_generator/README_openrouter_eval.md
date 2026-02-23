# OpenRouter 评测脚本使用说明

## 这是什么

两个脚本分别对 **MedBrowseComp** 和 **CureBench Testset** 两个医学问答 benchmark 进行评测。模型通过 OpenRouter API 调用（默认 seed1.8），结合 MCP 工具（FDA 药品搜索、Google 搜索、网页浏览等）来回答问题。

## 前提条件

1. MCP 工具服务已启动（默认 `127.0.0.1:8003`）
2. 设置环境变量：
   ```bash
   export OPENROUTER_API_KEY=your_key_here
   ```

## 运行

```bash
# MedBrowseComp 评测（合并 part1+part2 CSV 后运行）
bash scripts/pubmed_data_generator/run_medbrowsecomp_openrouter.sh

# CureBench Testset 评测（依次运行 original/prompt1/prompt3 三个 prompt 版本）
bash scripts/pubmed_data_generator/run_curebench_testset_openrouter.sh
```

## 输出

- MedBrowseComp → `medbrowsecomp_comparison_results/openrouter_seed1.8/`
- CureBench → `curebench_testset_results/` 下的 `original/`、`prompt1/`、`prompt3/`

每个目录包含 `.jsonl`（逐条结果）和 `.json`（统计摘要）。
