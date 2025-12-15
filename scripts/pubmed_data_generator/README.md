# PubMed 训练数据生成器

为 `pubmed_search` 工具生成训练/评测数据，确保每条样本必须调用 PubMed 搜索才能取得最佳效果。

## 功能特点

1. **必须依赖工具调用**：生成的问题必须调用 `pubmed_search` 才能高质量回答
2. **可验证的证据**：答案必须引用 PMID、摘要证据句、年份、期刊
3. **支持分页任务**：部分样本需要多次调用（offset 分页）
4. **稳定性策略**：内置证据库快照缓存，避免 API 漂移影响评测

## 快速开始

### 1. 环境准备

```bash
# 设置环境变量
export OPENROUTER_API_KEY="your-api-key"
export MCP_TRANSPORT="StreamableHttpTransport"
export MCP_TRANSPORT_PORT="8003"
export MCP_TRANSPORT_HOST="127.0.0.1"
```

### 2. 启动 MCP 服务器

```bash
cd /Users/liyc/Desktop/dr-tulu/agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

### 3. 运行测试

```bash
cd /Users/liyc/Desktop/dr-tulu/scripts/pubmed_data_generator
python test_generator.py --all
```

### 4. 生成数据集

```bash
# 生成小规模数据集（测试用）
python generate_dataset.py --clusters 5 --queries 3 --samples 1

# 生成完整数据集
python generate_dataset.py --clusters 30 --queries 10 --samples 1 --pagination-ratio 0.2
```

## 数据格式

### 输出文件

生成器会产出以下文件：

1. **`pubmed_train_YYYYMMDD_HHMMSS.jsonl`** - 完整训练数据（JSONL 格式）
2. **`pubmed_train_YYYYMMDD_HHMMSS.csv`** - CSV 格式（兼容现有训练流程）
3. **`evidence_cache_YYYYMMDD_HHMMSS.json`** - 证据库快照（评测稳定性）
4. **`stats_YYYYMMDD_HHMMSS.json`** - 统计信息

### 样本结构

```json
{
  "sample_id": "pubmed_00001",
  "user_question": "BRCA1 突变乳腺癌患者的靶向治疗选择有哪些？请引用相关研究并提供证据。",
  "expected_tools": [
    {
      "tool_name": "pubmed_search",
      "parameters": {"keywords": "BRCA1 breast cancer treatment", "limit": 5, "offset": 0},
      "purpose": "检索相关医学文献"
    }
  ],
  "evidence_pmids": ["12345678", "87654321"],
  "evidence_requirements": [
    {
      "pmid": "12345678",
      "title": "BRCA1 mutations in breast cancer treatment",
      "year": "2023",
      "venue": "Nature Medicine",
      "abstract_evidence_sentence": "This study investigates the role of BRCA1 mutations...",
      "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    }
  ],
  "answer_rubric": {
    "rubric_items": [
      {
        "category": "tool_use",
        "title": "正确调用 pubmed_search",
        "description": "模型必须调用 pubmed_search 工具进行文献检索",
        "weight": 3,
        "pass_condition": "调用了 pubmed_search 且参数格式正确",
        "fail_condition": "未调用 pubmed_search 或参数错误"
      },
      {
        "category": "verifiability",
        "title": "引用正确的 PMID",
        "description": "输出必须包含正确的 PMID，与证据库对齐",
        "weight": 3,
        "pass_condition": "正确引用了至少 2 个 PMID",
        "fail_condition": "未引用 PMID 或 PMID 不在证据库中"
      }
    ],
    "stability_strategy": {
      "strategy_type": "cache_snapshot",
      "description": "该样本依赖对 pubmed_search 返回做快照缓存",
      "implementation": "评测时使用缓存的证据库快照，避免实时 API 调用带来的漂移"
    }
  }
}
```

## 评分机制

### 三类评分

1. **工具使用分 (tool_use)**
   - 是否调用 `pubmed_search`
   - 分页任务是否调用足够页

2. **可验证性分 (verifiability)**
   - PMID/标题/年份/期刊一致性
   - 摘要证据句能在 abstract 中对齐

3. **任务完成分 (task_completion)**
   - 是否完成指定的比较/抽取/统计/归纳目标

### 稳定性策略

- **cache_snapshot**: 使用缓存快照评测（默认）
- **query_stabilization**: 查询包含强限定降低漂移
- **semantic_scoring**: 语义对齐评分（允许论文集变化）

## 配置选项

编辑 `config.py` 修改默认配置：

```python
# 数据生成配置
NUM_TOPIC_CLUSTERS = 30    # 主题簇数量
QUERIES_PER_CLUSTER = 10   # 每个主题簇的查询模板数量
SAMPLES_PER_QUERY = 1      # 每个查询生成的样本数量

# LLM 配置
LLM_MODEL = "openai/gpt-4o"  # OpenRouter 模型

# MCP 服务器配置
MCP_HOST = "127.0.0.1"
MCP_PORT = "8003"
```

## 主题簇覆盖

生成器会自动覆盖以下领域：

- 常见疾病（癌症、心血管、神经退行性）
- 罕见疾病（渐冻症、囊性纤维化）
- 药物/治疗（免疫检查点、基因治疗）
- 分子通路（PI3K-AKT、自噬、表观遗传）
- 生物标志物（ctDNA、外泌体）
- 研究方法（CRISPR、单细胞测序）

约 30% 为长尾/冷门主题。

## 问题类型

生成的问题涵盖以下类型：

- **比较**: 比较不同研究的方法/结果/结论
- **汇总**: 综合多项研究的发现
- **抽取**: 从论文中提取特定数据/方法
- **分类**: 按标准分类分析不同研究
- **统计**: 基于多篇论文进行趋势分析

## 模块说明

| 模块 | 功能 |
|------|------|
| `config.py` | 配置管理 |
| `topic_generator.py` | 主题簇和查询模板生成 |
| `pubmed_client.py` | PubMed MCP 客户端 |
| `question_generator.py` | 基于证据反向生成问题 |
| `rubric_generator.py` | 评分 Rubric 生成 |
| `generate_dataset.py` | 主生成脚本 |
| `test_generator.py` | 组件测试 |

## 依赖

- Python 3.10+
- httpx
- fastmcp
- dotenv

确保项目根目录的 `.env` 文件包含：
```
OPENROUTER_API_KEY=your-key-here
```

## 注意事项

1. PubMed API 有速率限制，建议设置适当的延迟
2. 生成过程需要网络访问 OpenRouter 和 MCP 服务器
3. 证据库快照应与训练数据一起保存，用于评测
4. 建议先小规模测试 (`--clusters 3 --queries 2`)

