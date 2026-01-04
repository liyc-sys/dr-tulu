import json
import re
from pathlib import Path

def redesign_rubrics(input_file: str, output_file: str):
    """
    重新设计rubrics权重：
    1. tool rubrics去掉"Provide year and journal info"，保留2个，每个weight=0.2
    2. content rubrics的weight加起来=0.6，平均分配
    """
    
    print(f"📖 读取文件: {input_file}")
    
    processed_count = 0
    error_count = 0
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for i, line in enumerate(f_in, 1):
            try:
                data = json.loads(line.strip())
                
                # 获取原始的all_rubrics
                all_rubrics = data.get('all_rubrics', [])
                if not all_rubrics:
                    print(f"⚠️  行{i}: 没有rubrics，跳过")
                    continue
                
                # 分离tool_use和content rubrics
                tool_rubrics = []
                content_rubrics = []
                
                for rubric in all_rubrics:
                    category = rubric.get('category', '')
                    title = rubric.get('title', '')
                    
                    # 去掉"Provide year and journal info"
                    if category == 'tool_use':
                        # 检查是否是要删除的那一条
                        if 'year and journal info' in title.lower() or 'year and journal' in title.lower():
                            print(f"🗑️  行{i}: 删除tool rubric - '{title}'")
                            continue
                        else:
                            tool_rubrics.append(rubric)
                    elif category == 'content':
                        content_rubrics.append(rubric)
                
                # 重新设计权重
                new_tool_rubrics = []
                new_content_rubrics = []
                
                # tool rubrics: 每个weight=0.2
                for rubric in tool_rubrics:
                    new_rubric = rubric.copy()
                    new_rubric['weight'] = 0.2
                    new_tool_rubrics.append(new_rubric)
                
                # content rubrics: 总weight=0.6，平均分配
                if content_rubrics:
                    content_weight_per_item = 0.6 / len(content_rubrics)
                    # 使用更高精度，然后确保总和等于0.6
                    content_weights = [content_weight_per_item] * len(content_rubrics)
                    # 调整最后一个rubric的权重以确保总和精确为0.6
                    content_weights[-1] = 0.6 - sum(content_weights[:-1])
                    
                    for i, rubric in enumerate(content_rubrics):
                        new_rubric = rubric.copy()
                        new_rubric['weight'] = content_weights[i]  # 使用预计算的精确权重
                        new_content_rubrics.append(new_rubric)
                
                # 组合新的rubrics
                new_all_rubrics = new_tool_rubrics + new_content_rubrics
                
                # 验证总权重
                total_weight = sum(r['weight'] for r in new_all_rubrics)
                
                # 更新数据
                data['all_rubrics'] = new_all_rubrics
                
                # 保存
                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                processed_count += 1
                
                # 显示修改信息
                if i <= 3:  # 只显示前3行的详细信息
                    print(f"\n✅ 行{i}: {data.get('sample_id', 'unknown')}")
                    print(f"   原始tool rubrics: {len(tool_rubrics)} → 新tool rubrics: {len(new_tool_rubrics)}")
                    print(f"   原始content rubrics: {len(content_rubrics)} → 新content rubrics: {len(new_content_rubrics)}")
                    print(f"   新的tool rubrics (每个weight=0.2):")
                    for r in new_tool_rubrics:
                        print(f"      - [{r['category']}] {r['title']} (weight: {r['weight']})")
                    if content_rubrics:
                        print(f"   新的content rubrics (总weight=0.6):")
                        for r in new_content_rubrics:
                            print(f"      - [{r['category']}] {r['title']} (weight: {r['weight']:.6f})")
                    print(f"   总权重: {total_weight:.6f}")
                
            except json.JSONDecodeError as e:
                print(f"❌ 行{i}: JSON解析错误 - {e}")
                error_count += 1
            except Exception as e:
                print(f"❌ 行{i}: 处理错误 - {e}")
                error_count += 1
    
    print(f"\n" + "="*60)
    print(f"✅ 处理完成!")
    print(f"📊 统计:")
    print(f"   成功处理: {processed_count} 行")
    print(f"   错误数量: {error_count} 行")
    print(f"📁 输出文件: {output_file}")

def main():
    # 文件路径
    input_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl'
    output_file = '/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_rubricsEdit.jsonl'
    
    # 检查输入文件是否存在
    if not Path(input_file).exists():
        print(f"❌ 输入文件不存在: {input_file}")
        return
    
    # 执行重新设计
    redesign_rubrics(input_file, output_file)
    
    print(f"\n💡 提示: 可以用新文件替换原始文件进行评估")
    print(f"   备份命令: cp {input_file} {input_file}.backup")
    print(f"   替换命令: mv {output_file} {input_file}")

if __name__ == "__main__":
    main()
