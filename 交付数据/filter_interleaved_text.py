import json
import os

input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/3次数据收集.jsonl"
output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/3次数据收集_纯净.jsonl"

with open(input_file, 'r', encoding='utf-8') as f_in, \
     open(output_file, 'w', encoding='utf-8') as f_out:
    
    for line_num, line in enumerate(f_in, 1):
        line = line.strip()
        if not line:
            continue
        
        try:
            item = json.loads(line)
            
            # 检查并处理 interleaved_text
            if 'trajectory' in item and 'interleaved_text' in item['trajectory']:
                interleaved_text = item['trajectory']['interleaved_text']
                
                # 按行分割，只保留包含 </answer> 的行
                lines = interleaved_text.split('\n')
                filtered_lines = [l for l in lines if '</answer>' in l]
                
                # 重新组合过滤后的内容
                filtered_text = '\n'.join(filtered_lines)
                
                # 只保留过滤后内容不为空的条目
                if filtered_text.strip():
                    item['trajectory']['interleaved_text'] = filtered_text
                    # 写入新文件
                    f_out.write(json.dumps(item, ensure_ascii=False) + '\n')
            else:
                # 如果没有 trajectory 或 interleaved_text，跳过
                pass
            
        except json.JSONDecodeError as e:
            print(f"第 {line_num} 行解析失败: {e}")
        except Exception as e:
            print(f"第 {line_num} 行处理失败: {e}")

print(f"处理完成！结果已保存到: {output_file}")

