import json
import os

# ================= 文件路径 =================
# input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/4次数据收集.jsonl"
# output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/4次数据收集_纯净.jsonl"

input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/4次tulu数据收集.jsonl"
output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/4次tulu数据收集_纯净.jsonl"
# ===========================================

print(f"开始筛选: {input_file}")
kept_count = 0
dropped_count = 0

with open(input_file, 'r', encoding='utf-8') as f_in, \
     open(output_file, 'w', encoding='utf-8') as f_out:
    
    for line_num, line in enumerate(f_in, 1):
        line = line.strip()
        if not line:
            continue
        
        try:
            item = json.loads(line)
            
            # 安全获取 interleaved_text，如果没有该字段默认为空字符串
            text_content = item.get('trajectory', {}).get('interleaved_text', '')
            
            # -------------------------------------------------
            # 核心逻辑：只检查，不修改！
            # 只要包含 </answer>，就整条写入，原汁原味
            # -------------------------------------------------
            if '</answer>' in text_content:
                f_out.write(json.dumps(item, ensure_ascii=False) + '\n')
                kept_count += 1
            else:
                dropped_count += 1
                
        except json.JSONDecodeError:
            print(f"第 {line_num} 行 JSON 格式错误，跳过。")
        except Exception as e:
            print(f"第 {line_num} 行发生未知错误: {e}")

print("=" * 30)
print(f"筛选完成！")
print(f"保留行数 (包含 </answer>): {kept_count}")
print(f"丢弃行数 (不含 </answer>): {dropped_count}")
print(f"文件已保存至: {output_file}")