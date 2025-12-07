#!/usr/bin/env python3
"""
简单测试脚本，验证 Semantic Scholar API 的修改是否正常工作
"""

import sys
sys.path.insert(0, '/Users/liyc/Desktop/dr-tulu/agent')

from dr_agent.mcp_backend.apis.semantic_scholar_apis import (
    search_semantic_scholar_snippets,
    SemanticScholarSnippetSearchQueryParams,
)

print("=" * 60)
print("测试 Semantic Scholar API 修改")
print("=" * 60)
print()
print("配置信息:")
print("- 免费调用地址: https://api.semanticscholar.org/graph/v1")
print("- 付费调用地址: https://lifuai.com/api/v1/graph/v1")
print("- 免费重试次数: 3 次")
print()
print("策略:")
print("  1. 先访问官方地址进行免费调用（不带 API key）")
print("  2. 重试 3 次，每次失败等待 1 秒")
print("  3. 如果都失败，切换到代理地址付费调用（带 API key）")
print()
print("=" * 60)
print()

# 测试 snippet search
print("测试: Semantic Scholar Snippet Search")
print("-" * 60)

try:
    query_params = SemanticScholarSnippetSearchQueryParams(
        query="large language model evaluation",
        year="2023-2024",
    )
    
    print(f"查询参数:")
    print(f"  - query: {query_params.query}")
    print(f"  - year: {query_params.year}")
    print()
    
    results = search_semantic_scholar_snippets(
        query_params=query_params,
        limit=3,
    )
    
    print(f"\n✓ 调用成功!")
    print(f"结果数量: {len(results.get('data', []))}")
    
    if results.get('data'):
        print("\n前 2 个结果:")
        for i, item in enumerate(results['data'][:2], 1):
            print(f"\n  结果 {i}:")
            if 'snippet' in item:
                print(f"    snippet: {item['snippet'][:100]}...")
            if 'paper' in item:
                paper = item['paper']
                print(f"    paper title: {paper.get('title', 'N/A')}")
                print(f"    paper year: {paper.get('year', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ 调用失败: {str(e)}")
    print("\n请检查:")
    print("  1. 代理地址是否正确")
    print("  2. 网络连接是否正常")
    print("  3. API 响应格式是否与预期一致")
    import traceback
    traceback.print_exc()

