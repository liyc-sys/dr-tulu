import re

def check_citation_compliance(file_path, model_name):
    """
    检查模型答案中的引用是否符合rubrics要求
    要求：每篇引用的论文必须包含发表年份和期刊/会议名称
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分割不同的问答条目
    entries = content.split('=' * 80)
    
    total_entries = 0
    compliant_entries = 0
    issues = []
    
    for entry in entries:
        if 'FINAL ANSWER:' not in entry:
            continue
            
        total_entries += 1
        
        # 提取final_answer部分
        final_answer_match = re.search(r'FINAL ANSWER:(.*?)(?=RUBRICS:|$)', entry, re.DOTALL)
        if not final_answer_match:
            continue
            
        final_answer = final_answer_match.group(1)
        
        # 查找引用模式
        # 常见引用格式：
        # 1. (Year, Journal)
        # 2. Year. Journal
        # 3. Journal, Year
        # 4. PMID引用格式
        
        # 检查是否包含引用
        has_citations = bool(re.search(r'\(\d{4}\)|\d{4}\.|PMID:?\s*\d+', final_answer))
        
        if has_citations:
            # 检查引用是否同时包含年份和期刊信息
            # 查找年份模式
            year_pattern = r'\b(19|20)\d{2}\b'
            years = re.findall(year_pattern, final_answer)
            
            # 查找期刊/会议模式
            journal_patterns = [
                r'\b[Jj]ournal\b',
                r'\b[Ll]ancet\b',
                r'\b[Nn]ature\b',
                r'\b[Ss]cience\b',
                r'\b[Pp]roc\b',
                r'\b[Cc]onf\b',
                r'\b[Mm]ed\b',
                r'\b[Cc]lin\b',
                r'\b[AAnn]nn\b',
                r'\b[Bb]MJ\b',
                r'\b[JAMA\b]'
            ]
            
            has_journal = any(re.search(pattern, final_answer) for pattern in journal_patterns)
            
            # 检查是否有具体的期刊名称（大写字母开头的期刊名）
            has_journal_name = bool(re.search(r'\b[A-Z][a-zA-Z\s&]+\b', final_answer))
            
            if years and (has_journal or has_journal_name):
                compliant_entries += 1
            else:
                # 记录不符合的情况
                if not years:
                    issues.append(f"条目{total_entries}: 缺少年份信息")
                if not (has_journal or has_journal_name):
                    issues.append(f"条目{total_entries}: 缺少期刊/会议信息")
        else:
            issues.append(f"条目{total_entries}: 未找到任何引用")
    
    print(f"\n=== {model_name} 引用检查结果 ===")
    print(f"总条目数: {total_entries}")
    print(f"符合rubrics要求的条目数: {compliant_entries}")
    print(f"符合率: {compliant_entries/total_entries*100:.1f}%" if total_entries > 0 else "无数据")
    
    if issues:
        print(f"\n发现的问题 (前10个):")
        for issue in issues[:10]:
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... 还有 {len(issues)-10} 个问题")
    
    return total_entries, compliant_entries, len(issues)

# 检查两个文件
dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_final_answers.txt'
tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_final_answers.txt'

check_citation_compliance(dporollout_file, "DPO Rollout")
check_citation_compliance(tulurollout_file, "Tulu Rollout")
