import json
import re

def check_original_answer_format(json_file):
    """
    检查原始pubmed_test.jsonl中的答案引用格式
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("=== 检查原始pubmed_test.jsonl中的答案格式 ===")
    
    count = 0
    for i, line in enumerate(lines):
        if i >= 3:  # 只检查前3条
            break
            
        try:
            data = json.loads(line.strip())
            
            # 检查是否有answer相关字段
            print(f"\n--- 条目 {i+1} ---")
            print(f"Sample ID: {data.get('sample_id', 'N/A')}")
            print(f"Question: {data.get('question', 'N/A')[:100]}...")
            
            # 检查trajectory字段
            trajectory = data.get('trajectory', {})
            if trajectory:
                print(f"\nTrajectory字段包含:")
                for key in trajectory.keys():
                    print(f"  - {key}")
                
                # 检查是否有final_answer
                if 'final_answer' in trajectory:
                    final_answer = trajectory['final_answer']
                    print(f"\nFinal Answer长度: {len(final_answer)} 字符")
                    print(f"Final Answer预览:\n{final_answer[:300]}...")
                    
                    # 检查引用格式
                    cite_matches = re.findall(r'<cite[^>]*>.*?</cite>', final_answer, re.DOTALL)
                    if cite_matches:
                        print(f"\n发现 {len(cite_matches)} 个引用")
                        for j, cite in enumerate(cite_matches[:2]):  # 只显示前2个
                            cite_content = re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', cite)
                            print(f"  引用{j+1}: {cite_content[:150]}...")
                    
                    # 检查是否有年份和期刊信息
                    has_year = bool(re.search(r'\b(19|20)\d{2}\b', final_answer))
                    has_journal = bool(re.search(r'\b[Jj]ournal\b|\b[Ll]ancet\b|\b[Nn]ature\b', final_answer))
                    
                    print(f"\n包含年份: {has_year}")
                    print(f"包含期刊名: {has_journal}")
                else:
                    print("  没有final_answer字段")
            else:
                print("  没有trajectory字段")
                
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")

# 检查原始文件
pubmed_test_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'
check_original_answer_format(pubmed_test_file)
