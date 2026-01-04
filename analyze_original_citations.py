import json
import re

def analyze_original_citations(json_file, num_entries=5):
    """
    分析原始文件中的引用格式是否包含年份和期刊信息
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("=== 分析原始pubmed_test.jsonl引用格式 ===\n")
    
    total_entries = 0
    entries_with_citations = 0
    entries_with_year_journal = 0
    
    for i, line in enumerate(lines):
        if i >= num_entries:  # 检查前num_entries条
            break
            
        try:
            data = json.loads(line.strip())
            trajectory = data.get('trajectory', {})
            final_answer = trajectory.get('final_answer', '')
            
            if not final_answer:
                continue
                
            total_entries += 1
            
            # 提取引用
            cite_matches = re.findall(r'<cite[^>]*>(.*?)</cite>', final_answer, re.DOTALL)
            
            if cite_matches:
                entries_with_citations += 1
                print(f"--- 条目 {i+1} ---")
                print(f"问题: {data.get('question', 'N/A')[:80]}...")
                print(f"引用数量: {len(cite_matches)}")
                
                # 分析引用格式
                has_complete_info = False
                
                for j, cite_content in enumerate(cite_matches[:3]):  # 只看前3个引用
                    print(f"\n  引用{j+1}: '{cite_content.strip()}'")
                    
                    # 检查年份
                    has_year = bool(re.search(r'\b(19|20)\d{2}\b', cite_content))
                    
                    # 检查期刊名
                    journal_patterns = [
                        r'\b[Jj]ournal\b',
                        r'\b[Ll]ancet\b',
                        r'\b[Nn]ature\b',
                        r'\b[Ss]cience\b',
                        r'\b[Cc]lin\b',
                        r'\b[Pp]roc\b'
                    ]
                    
                    has_journal = any(re.search(pattern, cite_content) for pattern in journal_patterns)
                    
                    # 检查作者格式 (et al.)
                    has_authors = bool(re.search(r'et al\.', cite_content))
                    
                    print(f"    年份: {'✓' if has_year else '✗'}")
                    print(f"    期刊名: {'✓' if has_journal else '✗'}")  
                    print(f"    作者格式: {'✓' if has_authors else '✗'}")
                    
                    if has_year and has_journal:
                        has_complete_info = True
                
                if has_complete_info:
                    entries_with_year_journal += 1
                    print("  ✅ 包含年份和期刊信息")
                else:
                    print("  ❌ 缺少年份或期刊信息")
                
                print()
                
        except json.JSONDecodeError:
            continue
    
    print("=== 统计结果 ===")
    print(f"检查条目数: {total_entries}")
    print(f"包含引用的条目: {entries_with_citations}")
    print(f"包含完整引用信息(年份+期刊)的条目: {entries_with_year_journal}")
    
    return total_entries, entries_with_citations, entries_with_year_journal

# 分析原始文件
pubmed_test_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'
analyze_original_citations(pubmed_test_file, num_entries=10)
