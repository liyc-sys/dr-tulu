"""
Step 1: 主题簇与查询模板生成
生成覆盖疾病/药物/通路/方法学的主题簇，包含长尾主题
"""
import json
import sys
from pathlib import Path

# 确保能找到 config 模块（支持绝对路径运行）
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import httpx
from typing import List, Dict, Any
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL

TOPIC_GENERATION_PROMPT = """你是一个生物医学专家。请生成 {num_clusters} 个 PubMed 搜索主题簇，用于训练 AI 模型的医学文献检索能力。

要求：
1. 覆盖以下领域（但不限于）：
   - 常见疾病（如癌症、心血管疾病、神经退行性疾病）
   - 罕见疾病（如渐冻症、囊性纤维化、亨廷顿病）
   - 药物/治疗（如免疫检查点抑制剂、基因治疗、mRNA疫苗）
   - 分子通路/机制（如 PI3K-AKT 通路、自噬、表观遗传调控）
   - 生物标志物（如 ctDNA、外泌体、蛋白组学标志物）
   - 研究方法（如 CRISPR 筛选、单细胞测序、类器官培养）

2. 包含约 30% 的长尾/冷门主题

3. 每个主题簇应该有明确的医学/生物学焦点

请以 JSON 格式输出，结构如下：
```json
{{
  "topic_clusters": [
    {{
      "cluster_id": 1,
      "name": "主题名称",
      "category": "疾病/药物/通路/方法学/生物标志物",
      "is_long_tail": false,
      "description": "简短描述"
    }}
  ]
}}
```

只输出 JSON，不要其他内容。
"""

QUERY_TEMPLATE_PROMPT = """针对以下医学主题簇，生成 {num_queries} 个 PubMed 查询模板。

主题簇: {cluster_name}
类别: {category}
描述: {description}

要求：
1. 查询以英文为主（可包含基因名、药物名、缩写）
2. 使用 PubMed 可识别的布尔运算符（AND, OR, NOT）和短语引号
3. 查询应该能稳定返回相关结果（使用更强限定）
4. 包含可变元素（如年份窗口、人群、结局）的占位符（用 {{variable}} 标记）
5. 涵盖不同类型的研究问题：
   - 疗效对比
   - 机制研究
   - 流行病学
   - 预后/生物标志物
   - 综述类

请以 JSON 格式输出：
```json
{{
  "query_templates": [
    {{
      "query_id": 1,
      "template": "PubMed 查询字符串",
      "query_type": "疗效对比/机制研究/流行病学/预后/综述",
      "variables": ["可替换的变量列表"],
      "description": "该查询旨在找到什么类型的文献"
    }}
  ]
}}
```

只输出 JSON，不要其他内容。
"""


async def call_llm(prompt: str, temperature: float = 0.7) -> str:
    """调用 OpenRouter LLM API（支持代理）"""
    import os
    
    # 获取代理设置
    proxy_url = os.environ.get("https_proxy") or os.environ.get("http_proxy")
    
    # 配置客户端
    client_kwargs = {"timeout": 120.0}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    
    async with httpx.AsyncClient(**client_kwargs) as client:
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]


def extract_json(text: str) -> Dict:
    """从 LLM 响应中提取 JSON（容错处理）"""
    import re
    
    # 尝试找到 JSON 代码块
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    json_str = json_match.group(1) if json_match else text
    
    # 尝试直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # 修复常见的转义问题
    # 1. 修复无效的转义序列
    def fix_escapes(s):
        # 替换无效的 \x 为 \\x（除了有效的转义字符）
        valid_escapes = ['\\n', '\\r', '\\t', '\\b', '\\f', '\\"', '\\\\', '\\/']
        result = s
        # 先处理已经是双反斜杠的情况
        result = result.replace('\\\\', '\x00DOUBLE_BACKSLASH\x00')
        # 修复单反斜杠后跟非法字符的情况
        result = re.sub(r'\\(?![nrtbf"\/u])', r'\\\\', result)
        # 恢复双反斜杠
        result = result.replace('\x00DOUBLE_BACKSLASH\x00', '\\\\')
        return result
    
    try:
        fixed_str = fix_escapes(json_str)
        return json.loads(fixed_str)
    except json.JSONDecodeError:
        pass
    
    # 尝试更宽松的解析：找到第一个 { 和最后一个 }
    try:
        start = json_str.find('{')
        end = json_str.rfind('}') + 1
        if start != -1 and end > start:
            json_substr = json_str[start:end]
            return json.loads(fix_escapes(json_substr))
    except json.JSONDecodeError:
        pass
    
    # 最后尝试：使用 ast.literal_eval 的方式清理
    try:
        # 移除可能导致问题的控制字符
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        return json.loads(cleaned)
    except:
        pass
    
    raise ValueError(f"无法解析 JSON 响应: {json_str[:500]}...")


async def generate_topic_clusters(num_clusters: int = 30, max_retries: int = 3) -> List[Dict]:
    """生成主题簇（带重试）"""
    prompt = TOPIC_GENERATION_PROMPT.format(num_clusters=num_clusters)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = await call_llm(prompt, temperature=0.7 if attempt == 0 else 0.5)
            result = extract_json(response)
            return result["topic_clusters"]
        except Exception as e:
            last_error = e
            print(f"  ⚠ 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2)
    
    raise ValueError(f"生成主题簇失败: {last_error}")


async def generate_query_templates(cluster: Dict, num_queries: int = 10, max_retries: int = 3) -> List[Dict]:
    """为单个主题簇生成查询模板（带重试）"""
    prompt = QUERY_TEMPLATE_PROMPT.format(
        num_queries=num_queries,
        cluster_name=cluster["name"],
        category=cluster["category"],
        description=cluster["description"]
    )
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = await call_llm(prompt, temperature=0.7 if attempt == 0 else 0.5)
            result = extract_json(response)
            return result["query_templates"]
        except Exception as e:
            last_error = e
            print(f"    ⚠ 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2)  # 等待 2 秒后重试
    
    # 如果全部失败，返回一个默认的查询模板
    print(f"    ✗ 生成失败，使用默认模板")
    return [{
        "query_id": 1,
        "template": f'"{cluster["name"]}"',
        "query_type": "综述",
        "variables": [],
        "description": f"搜索关于{cluster['name']}的文献"
    }]


async def generate_all_topic_clusters_and_queries(
    num_clusters: int = 30,
    queries_per_cluster: int = 10
) -> Dict[str, Any]:
    """生成所有主题簇及其查询模板"""
    print(f"正在生成 {num_clusters} 个主题簇...")
    topic_clusters = await generate_topic_clusters(num_clusters)
    print(f"✓ 生成了 {len(topic_clusters)} 个主题簇")
    
    result = {"topic_clusters": []}
    
    for i, cluster in enumerate(topic_clusters):
        print(f"正在为主题 '{cluster['name']}' 生成查询模板 ({i+1}/{len(topic_clusters)})...")
        queries = await generate_query_templates(cluster, queries_per_cluster)
        cluster["query_templates"] = queries
        result["topic_clusters"].append(cluster)
        print(f"  ✓ 生成了 {len(queries)} 个查询模板")
    
    return result


if __name__ == "__main__":
    import asyncio
    
    async def main():
        result = await generate_all_topic_clusters_and_queries(
            num_clusters=5,  # 测试时使用较小数量
            queries_per_cluster=3
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(main())

