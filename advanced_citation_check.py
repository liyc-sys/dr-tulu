import re

def check_citation_details(file_path, model_name):
    """
    详细检查引用是否包含年份和期刊信息
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = content.split('=' * 80)
    
    total_entries = 0
    has_citations = 0
    has_year_journal = 0
    
    citation_examples = []
    missing_examples = []
    
    for entry in entries:
        if 'FINAL ANSWER:' not in entry:
            continue
            
        total_entries += 1
        
        final_answer_match = re.search(r'FINAL ANSWER:(.*?)(?=RUBRICS:|$)', entry, re.DOTALL)
        if not final_answer_match:
            continue
            
        final_answer = final_answer_match.group(1)
        
        # 检查<cite>标签
        cite_matches = re.findall(r'<cite[^>]*>(.*?)</cite>', final_answer, re.DOTALL)
        
        if cite_matches:
            has_citations += 1
            
            # 检查这些引用是否包含年份和期刊信息
            entry_has_year_journal = False
            
            for cite in cite_matches:
                # 检查年份
                has_year = bool(re.search(r'\b(19|20)\d{2}\b', cite))
                
                # 检查期刊/会议信息
                journal_indicators = [
                    r'\b[Jj]ournal\b',
                    r'\b[Ll]ancet\b', 
                    r'\b[Nn]ature\b',
                    r'\b[Ss]cience\b',
                    r'\b[Cc]lin\b',
                    r'\b[Pp]roc\b',
                    r'\b[AAnn]nn\b',
                    r'\b[Bb]MJ\b',
                    r'\b[JAMA\b]'
                ]
                
                has_journal = any(re.search(pattern, cite) for pattern in journal_indicators)
                # 也检查是否有大写字母开头的期刊名模式
                has_journal_name = bool(re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', cite))
                
                if has_year and (has_journal or has_journal_name):
                    entry_has_year_journal = True
                    if len(citation_examples) < 3:
                        citation_examples.append(f"条目{total_entries}: {cite[:200]}...")
                    break
            
            if entry_has_year_journal:
                has_year_journal += 1
            elif len(missing_examples) < 3:
                # 找一个缺少信息的例子
                for cite in cite_matches:
                    missing_example = f"条目{total_entries}: {cite[:300]}..."
                    missing_examples.append(missing_example)
                    break
    
    print(f"\n=== {model_name} 详细引用检查 ===")
    print(f"总条目数: {total_entries}")
    print(f"包含引用的条目: {has_citations} ({has_citations/total_entries*100:.1f}%)")
    print(f"引用包含年份和期刊信息的条目: {has_year_journal} ({has_year_journal/total_entries*100:.1f}%)")
    
    if citation_examples:
        print(f"\n符合要求的引用示例:")
        for example in citation_examples:
            print(f"  ✓ {example}")
    
    if missing_examples:
        print(f"\n缺少年份或期刊信息的引用示例:")
        for example in missing_examples:
            print(f"  ✗ {example}")

# 检查两个文件
dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_final_answers.txt'
tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_final_answers.txt'

check_citation_details(dporollout_file, "DPO Rollout")
check_citation_details(tulurollout_file, "Tulu Rollout")
