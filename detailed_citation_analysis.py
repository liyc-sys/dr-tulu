import json
import re

def analyze_citations_in_json(json_file, model_name):
    """
    直接分析JSON文件中的引用格式
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"\n=== {model_name} 引用格式分析 ===")
    
    total_entries = 0
    entries_with_citations = 0
    entries_with_year_journal = 0
    
    sample_good = []
    sample_bad = []
    
    for i, line in enumerate(lines):
        try:
            data = json.loads(line.strip())
            trajectory = data.get('trajectory', {})
            final_answer = trajectory.get('final_answer', '')
            
            if not final_answer:
                continue
                
            total_entries += 1
            
            # 检查<cite>标签中的内容
            cite_matches = re.findall(r'<cite[^>]*>.*?</cite>', final_answer, re.DOTALL)
            
            if cite_matches:
                entries_with_citations += 1
                
                has_complete_citation = False
                
                for cite in cite_matches:
                    # 提取cite内容
                    cite_content = re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', cite)
                    
                    # 检查是否包含年份
                    has_year = bool(re.search(r'\b(19|20)\d{2}\b', cite_content))
                    
                    # 检查期刊/会议信息（包括常见的期刊名模式）
                    journal_patterns = [
                        r'\b[Jj]ournal\b',
                        r'\b[Ll]ancet\b',
                        r'\b[Nn]ature\b', 
                        r'\b[Ss]cience\b',
                        r'\b[Pp]roc\b',
                        r'\b[Cc]onf\b',
                        r'\b[Cc]lin\b',
                        r'\b[Mm]ed\b',
                        r'\b[Bb]MJ\b',
                        r'\b[JAMA\b]',
                        r'\b[AAnn]nn\b',
                        r'\b[Arc][h-z]+\b'  # Archives, 等等
                    ]
                    
                    has_journal = any(re.search(pattern, cite_content) for pattern in journal_patterns)
                    
                    # 检查是否有具体的期刊名称（大写字母开头的词，后面跟小写字母）
                    has_journal_name = bool(re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Journal|Proceedings|Conference|Clinics|Archives)\b', cite_content))
                    
                    if has_year and (has_journal or has_journal_name):
                        has_complete_citation = True
                        if len(sample_good) < 2:
                            sample_good.append({
                                'entry': i+1,
                                'cite': cite_content[:300]
                            })
                        break
                
                if has_complete_citation:
                    entries_with_year_journal += 1
                elif len(sample_bad) < 2:
                    # 找一个不完整的例子
                    for cite in cite_matches:
                        cite_content = re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', cite)
                        sample_bad.append({
                            'entry': i+1,
                            'cite': cite_content[:300]
                        })
                        break
                        
        except json.JSONDecodeError:
            continue
    
    print(f"总条目数: {total_entries}")
    print(f"包含引用的条目: {entries_with_citations} ({entries_with_citations/total_entries*100:.1f}%)")
    print(f"引用包含年份和期刊信息的条目: {entries_with_year_journal} ({entries_with_year_journal/total_entries*100:.1f}%)")
    
    if sample_good:
        print(f"\n✓ 符合要求的引用示例:")
        for sample in sample_good:
            print(f"  条目{sample['entry']}: {sample['cite']}...")
    
    if sample_bad:
        print(f"\n✗ 缺少年份或期刊信息的引用示例:")
        for sample in sample_bad:
            print(f"  条目{sample['entry']}: {sample['cite']}...")

# 分析两个JSON文件
dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl'
tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_tulurollout.jsonl'

analyze_citations_in_json(dporollout_file, "DPO Rollout")
analyze_citations_in_json(tulurollout_file, "Tulu Rollout")
