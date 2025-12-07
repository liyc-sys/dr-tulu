#!/bin/bash
# 清除 Semantic Scholar API 缓存

echo "清除 Semantic Scholar API 缓存..."
echo ""

# 查找所有可能的缓存目录
CACHE_DIRS=(
    "/workspace/math_science_data/lyc/1205/dr-tulu/agent/.cache"
    "/workspace/math_science_data/lyc/1205/dr-tulu/.cache"
    ".cache"
    "agent/.cache"
)

for cache_dir in "${CACHE_DIRS[@]}"; do
    if [ -d "$cache_dir" ]; then
        echo "发现缓存目录: $cache_dir"
        echo "  大小: $(du -sh "$cache_dir" 2>/dev/null | cut -f1)"
        
        # 只清除 diskcache 子目录（API 缓存）
        if [ -d "$cache_dir/diskcache" ]; then
            echo "  清除 API 缓存: $cache_dir/diskcache"
            rm -rf "$cache_dir/diskcache"
            echo "  ✓ 已清除"
        else
            echo "  (无 API 缓存)"
        fi
        echo ""
    fi
done

echo "缓存清除完成！"
echo ""
echo "现在可以重新运行测试："
echo "  uv run python /workspace/math_science_data/lyc/1205/dr-tulu/test_semantic_scholar_api.py"

