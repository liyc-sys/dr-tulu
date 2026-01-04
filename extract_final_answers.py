import json

def extract_final_answers(rollout_file, output_file, pubmed_test_file='/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'):
    """
    从rollout文件中提取final_answer并匹配对应的rubrics
    """
    # 首先读取pubmed_test.jsonl，建立question到all_rubrics的映射
    question_to_rubrics = {}
    with open(pubmed_test_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                question = data.get('question', '')
                all_rubrics = data.get('all_rubrics', [])
                if question and all_rubrics:
                    question_to_rubrics[question] = all_rubrics
            except json.JSONDecodeError:
                continue

    print(f"从pubmed_test.jsonl中读取了 {len(question_to_rubrics)} 个问题的rubrics")

    # 然后读取rollout文件，根据question匹配rubrics
    with open(rollout_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        count = 0
        matched_count = 0
        for line in f_in:
            try:
                data = json.loads(line.strip())
                question = data.get('question', '')
                trajectory = data.get('trajectory', {})
                final_answer = trajectory.get('final_answer', '')
                
                if final_answer:
                    # 写入final_answer
                    f_out.write(f"QUESTION:\n{question}\n\n")
                    f_out.write(f"FINAL ANSWER:\n{final_answer}\n\n")
                    
                    # 根据question查找对应的rubrics
                    if question in question_to_rubrics:
                        rubrics = question_to_rubrics[question]
                        f_out.write("RUBRICS:\n")
                        for i, rubric in enumerate(rubrics, 1):
                            category = rubric.get('category', '')
                            title = rubric.get('title', '')
                            description = rubric.get('description', '')
                            weight = rubric.get('weight', 0)
                            
                            f_out.write(f"{i}. [{category}] {title} (权重: {weight})\n")
                            f_out.write(f"   {description}\n")
                        matched_count += 1
                    else:
                        f_out.write("RUBRICS: 未找到对应的rubrics\n")
                    
                    f_out.write('\n' + '='*80 + '\n\n')
                    count += 1
            except json.JSONDecodeError:
                continue

    print(f"从 {rollout_file} 成功提取 {count} 个 final_answer 到 {output_file}")
    print(f"其中 {matched_count} 个找到了对应的rubrics")
    return count, matched_count

if __name__ == "__main__":
    # 处理dporollout文件
    print("处理 pubmed_test_dporollout.jsonl:")
    dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl'
    dporollout_output = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_final_answers.txt'
    extract_final_answers(dporollout_file, dporollout_output)
    
    print("\n处理 pubmed_test_tulurollout.jsonl:")
    # 处理tulurollout文件
    tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_tulurollout.jsonl'
    tulurollout_output = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_final_answers.txt'
    extract_final_answers(tulurollout_file, tulurollout_output)
