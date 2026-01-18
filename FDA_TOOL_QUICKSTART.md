# FDA Drug Label Search Tool - 快速开始

## 🎯 一句话总结

从 FDA 数据库搜索药物信息，支持智能提取，已集成到 MCP 训练框架。

## 📦 已添加的文件

```bash
agent/dr_agent/mcp_backend/apis/fda_apis.py          # FDA API 实现
agent/dr_agent/mcp_backend/main.py                   # 已添加工具函数
agent/dr_agent/tool_interface/mcp_tools.py           # 已添加工具类
agent/dr_agent/tool_interface/__init__.py            # 已导出
rl/open-instruct/open_instruct/search_utils/mcp_tools.py  # 已注册
test_fda_tool.py                                      # 测试脚本
FDA_TOOL_USAGE.md                                     # 详细文档
FDA_TOOL_SUMMARY.md                                   # 实现总结
```

## 🚀 快速使用

### 1. 设置环境变量（必需）

```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxx"
```

### 2. 启动 MCP Server

```bash
cd /path/to/dr-tulu/agent
uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp
```

### 3. 在训练中使用

```bash
--tools mcp \
--mcp_tool_names 'snippet_search,google_search,browse_webpage,fda_drug_search' \
--max_tool_calls 10
```

### 4. 模型调用格式

```xml
<tool name="fda_drug_search">
<parameter name="focus">adverse reactions</parameter>
aspirin
</tool>
```

## 🧪 测试

```bash
# 确保设置了 API Key
export OPENROUTER_API_KEY="your-api-key"

# 运行测试
python test_fda_tool.py
```

## 📖 工具参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `keyword` | 药物名称 | `"aspirin"`, `"metformin"` |
| `focus` | 关注点 | `"adverse reactions"`, `"dosage"` |
| `limit` | 结果数量 | `3` (默认) |
| `use_llm_extraction` | 是否用 LLM 提取 | `True` (默认) |

## 💡 常用 focus 参数

- `"adverse reactions"` - 副作用
- `"indications and usage"` - 适应症
- `"dosage and administration"` - 剂量
- `"warnings and precautions"` - 警告
- `"drug interactions"` - 药物相互作用
- `"contraindications"` - 禁忌症

## 🔍 工作原理

1. **三级搜索策略**:
   - 品牌名搜索 → 通用名搜索 → 全文搜索

2. **智能提取**:
   - 使用 LLM (bytedance-seed/seed-1.6) 根据 focus 提取相关信息

3. **错误处理**:
   - 自动重试机制
   - 回退到原始数据

## 📝 Python 代码示例

```python
# 直接调用 API
from agent.dr_agent.mcp_backend.apis.fda_apis import search_fda_drug_label

result = search_fda_drug_label(
    keyword="ibuprofen",
    focus="adverse reactions",
    limit=2
)

print(result['extracted_info'])
```

## ⚠️ 注意事项

1. **必须设置** `OPENROUTER_API_KEY` 环境变量
2. **推荐超时** 设置为 180 秒
3. **FDA API 有速率限制**，已内置重试机制

## 📚 更多文档

- 详细使用指南: `FDA_TOOL_USAGE.md`
- 实现总结: `FDA_TOOL_SUMMARY.md`
- FDA API 官方文档: https://open.fda.gov/apis/drug/label/

## ✅ 状态

- ✅ API 实现完成
- ✅ MCP 工具集成完成
- ✅ 工具注册完成
- ✅ 测试脚本完成
- ✅ 文档完成
- ✅ **可以在训练中使用！**

---

**有问题？查看 `FDA_TOOL_USAGE.md` 获取详细帮助。**

