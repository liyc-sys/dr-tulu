import json
import re

def detailed_original_check(json_file):
    """
    详细检查原始文件中的引用格式
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("=== 详细检查原始pubmed_test.jsonl引用格式 ===")
    
    for i, line in enumerate(lines):
        if i >= 2:  # 只检查前2条
            break
            
        try:
            data = json.loads(line.strip())
            trajectory = data.get('trajectory', {})
            final_answer = trajectory.get('final_answer', '')
            
            if not final_answer:
                continue
                
            print(f"\n--- 条目 {i+1} ---")
            print(f"Question: {data.get('question', 'N/A')[:80]}...")
            
            # 提取所有引用
            cite_matches = re.findall(r'<cite[^>]*>(.*?)</cite>', final_answer, re.DOTALL)
            
            print(f"\n共发现 {len(cite_matches)} 个引用，显示前3个:")
            
            for j, cite_content in enumerate(cite_matches[:3]):
                print(f"\n引用 {j+1}:")
                print(f"  内容: {cite_content[:200]}...")
                
                # 分析这个引用是否包含年份和期刊
                has_year = bool(re.search(r'\b(19|20)\d{2}\b', cite_content))
                
                # 检查期刊相关词汇
                journal_indicators = []
                if re.search(r'\b[Jj]ournal\b', cite_content):
                    journal_indicators.append("Journal")
                if re.search(r'\b[Ll]ancet\b', cite_content):
                    journal_indicators.append("Lancet") 
                if re.search(r'\b[Nn]ature\b', cite_content):
                    journal_indicators.append("Nature")
                if re.search(r'\b[Ss]cience\b', cite_content):
                    journal_indicators.append("Science")
                if re.search(r'et al\.', cite_content):
                    journal_indicators.append("et al. (作者引用格式)")
                if re.search(r'\d{4}', cite_content):
                    journal_indicators.append("包含数字(可能是年份)")
                
                print(f"  年份: {'✓' if has_year else '✗'}")
                print(f"  期刊相关信息: {', '.join(journal_indicators) if journal_indicators else '✗'}")
                
        except json.JSONDecodeError:
            continue

# 检查原始文件
pubmed_test_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'
detailed_original_check(pubmed_test_file)
