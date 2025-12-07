#!/usr/bin/env python3
"""
强制重新加载测试脚本 - 确保使用最新代码
"""

import sys
import os
import importlib

# 首先检查环境变量
print("=" * 60)
print("环境检查")
print("=" * 60)
print(f"http_proxy: {os.getenv('http_proxy', 'NOT SET')}")
print(f"https_proxy: {os.getenv('https_proxy', 'NOT SET')}")
print()

# 禁用缓存
os.environ['MCP_CACHE_DIR'] = '/tmp/test_cache_fresh'

sys.path.insert(0, '/workspace/math_science_data/lyc/1205/dr-tulu/agent')

# 先导入模块
from dr_agent.mcp_backend import cache as cache_module
from dr_agent.mcp_backend.apis import semantic_scholar_apis

# 强制重新加载模块
print("重新加载模块...")
importlib.reload(cache_module)
importlib.reload(semantic_scholar_apis)
print("✓ 模块已重新加载")
print()

# 禁用缓存
cache_module.set_cache_enabled(False)

# 导入需要的类和函数
from dr_agent.mcp_backend.apis.semantic_scholar_apis import (
    search_semantic_scholar_snippets,
    SemanticScholarSnippetSearchQueryParams,
)

print("=" * 60)
print("测试 Semantic Scholar API 修改 (强制刷新)")
print("=" * 60)
print()
print("配置信息:")
print("- 免费调用地址: https://api.semanticscholar.org/graph/v1")
print("- 付费调用地址: https://lifuai.com/api/v1/graph/v1")
print("- 免费重试次数: 3 次")
print("- 缓存: 已禁用 ✓")
print()
print("=" * 60)
print()

# 测试 snippet search
print("测试: Semantic Scholar Snippet Search")
print("-" * 60)

try:
    query_params = SemanticScholarSnippetSearchQueryParams(
        query="transformer attention",
        year="2023-2024",
    )
    
    print(f"查询参数:")
    print(f"  - query: {query_params.query}")
    print(f"  - year: {query_params.year}")
    print()
    print("开始调用 API...")
    print()
    
    results = search_semantic_scholar_snippets(
        query_params=query_params,
        limit=3,
    )
    
    print(f"\n✓ API 调用完成!")
    print(f"返回结果: {results}")
    print(f"结果数量: {len(results.get('data', []))}")
    
    if results.get('data'):
        print("\n前 2 个结果:")
        for i, item in enumerate(results['data'][:2], 1):
            print(f"\n  结果 {i}:")
            if 'snippet' in item:
                snippet_text = item['snippet']
                print(f"    snippet: {snippet_text[:100]}...")
            if 'paper' in item:
                paper = item['paper']
                print(f"    paper title: {paper.get('title', 'N/A')}")
                print(f"    paper year: {paper.get('year', 'N/A')}")
    else:
        print("\n⚠ 返回了空结果")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ 调用失败: {str(e)}")
    print("\n详细错误信息:")
    import traceback
    traceback.print_exc()

