import json

# 加载rubrics映射
rubrics_map = {}
with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line.strip())
            question = data.get('question', '')
            all_rubrics = data.get('all_rubrics', [])
            if question and all_rubrics:
                rubrics_map[question] = all_rubrics
        except json.JSONDecodeError:
            continue

print(f"📋 加载了 {len(rubrics_map)} 个问题的rubrics")

# 检查rollout文件中的问题
missing_count = 0
found_count = 0

with open('/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        try:
            data = json.loads(line.strip())
            sample_id = data.get('sample_id')
            question = data.get('question', '')
            
            if question in rubrics_map:
                found_count += 1
                if i <= 5:  # 只显示前5个匹配的
                    print(f"✅ 行{i} ({sample_id}): 找到rubrics")
            else:
                missing_count += 1
                print(f"❌ 行{i} ({sample_id}): 未找到rubrics")
                print(f"   问题: {question[:100]}...")
                
                # 尝试找到最相似的问题
                best_match = None
                best_similarity = 0
                for rubric_question in rubrics_map.keys():
                    # 简单的相似度计算：共同字符比例
                    common_chars = set(question) & set(rubric_question)
                    similarity = len(common_chars) / max(len(set(question)), len(set(rubric_question)))
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = rubric_question
                
                if best_similarity > 0.8:
                    print(f"   最相似的问题 ({best_similarity:.2f}):")
                    print(f"   {best_match[:100]}...")
                print()
                
                if missing_count >= 3:  # 只显示前3个缺失的
                    print(f"... 还有 {missing_count - 3} 个问题找不到rubrics")
                    break
                    
        except json.JSONDecodeError:
            continue

print(f"\n📊 统计:")
print(f"   找到rubrics: {found_count}")
print(f"   未找到rubrics: {missing_count}")
