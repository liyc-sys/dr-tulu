#!/usr/bin/env python3
"""
测试脚本 - 显式设置代理
"""

import sys
import os
import importlib

# 显式设置代理环境变量（与训练脚本一致）
os.environ['http_proxy'] = 'http://httpproxy.glm.ai:8888'
os.environ['https_proxy'] = 'http://httpproxy.glm.ai:8888'
os.environ['no_proxy'] = '127.0.0.1,localhost,platform.glm.ai,::1'

# 禁用缓存
os.environ['MCP_CACHE_DIR'] = '/tmp/test_cache_with_proxy'

print("=" * 60)
print("环境设置")
print("=" * 60)
print(f"http_proxy: {os.environ.get('http_proxy')}")
print(f"https_proxy: {os.environ.get('https_proxy')}")
print()

sys.path.insert(0, '/workspace/math_science_data/lyc/1205/dr-tulu/agent')

# 导入并重新加载
from dr_agent.mcp_backend import cache as cache_module
from dr_agent.mcp_backend.apis import semantic_scholar_apis

print("重新加载模块...")
importlib.reload(cache_module)
importlib.reload(semantic_scholar_apis)
print("✓ 模块已重新加载")
print()

# 禁用缓存
cache_module.set_cache_enabled(False)

from dr_agent.mcp_backend.apis.semantic_scholar_apis import (
    search_semantic_scholar_snippets,
    SemanticScholarSnippetSearchQueryParams,
)

print("=" * 60)
print("测试 Semantic Scholar API 修改")
print("=" * 60)
print()
print("配置:")
print("- 免费地址: https://api.semanticscholar.org/graph/v1")
print("- 付费地址: https://lifuai.com/api/v1/graph/v1")
print("- 代理: http://httpproxy.glm.ai:8888")
print("- 重试: 3 次")
print()
print("=" * 60)
print()

print("测试: Snippet Search")
print("-" * 60)

try:
    query_params = SemanticScholarSnippetSearchQueryParams(
        query="deep learning",
        year="2024",
    )
    
    print(f"查询: {query_params.query}")
    print(f"年份: {query_params.year}")
    print()
    print("⏳ 开始调用...")
    print()
    
    results = search_semantic_scholar_snippets(
        query_params=query_params,
        limit=3,
    )
    
    print()
    print("=" * 60)
    print("调用结果")
    print("=" * 60)
    
    # 检查是否是错误响应
    if 'message' in results and len(results) == 1:
        print(f"❌ API 返回错误: {results['message']}")
    elif 'error' in results:
        print(f"❌ API 返回错误: {results['error']}")
    else:
        print(f"✅ 调用成功!")
        data = results.get('data', [])
        print(f"结果数量: {len(data)}")
        print(data)
        
        if data:
            print("\n前 2 个结果:")
            for i, item in enumerate(data[:2], 1):
                print(f"\n结果 {i}:")
                if 'snippet' in item:
                    print(f"  snippet: {item['snippet'][:80]}...")
                if 'paper' in item:
                    paper = item['paper']
                    print(f"  title: {paper.get('title', 'N/A')}")
                    print(f"  year: {paper.get('year', 'N/A')}")
    
    print("\n" + "=" * 60)
    
except Exception as e:
    print(f"\n❌ 异常: {str(e)}")
    import traceback
    traceback.print_exc()

