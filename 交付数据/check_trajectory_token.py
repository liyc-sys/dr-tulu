import json
import os
from transformers import AutoTokenizer

def check_trajectory_length(file_path, model_path="Qwen/Qwen2.5-72B-Instruct", limit=16000):
    """
    检查 jsonl 文件中 trajectory (含工具调用轨迹) 的 token 长度。
    """
    
    print(f"正在加载 Tokenizer: {model_path} ...")
    try:
        # 如果是本地的 Qwen3-8B，请将 model_path 改为本地文件夹路径
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    except Exception as e:
        print(f"加载 Tokenizer 失败: {e}")
        return

    over_limit_count = 0
    max_tokens_found = 0
    total_samples = 0
    
    print(f"开始扫描文件: {file_path} ...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                data = json.loads(line)
                total_samples += 1
                
                # 提取 trajectory 
                traj = data.get("trajectory", {})
                
                content_to_tokenize = ""
                
                if isinstance(traj, dict):
                    # 1. 获取中间过程 (Thinking, Tool Calls, Tool Outputs)
                    # 根据你的样例，这部分主要在 interleaved_text 里
                    interleaved = traj.get("interleaved_text", "")
                    
                    # 2. 获取最终回答 (如果有单独的字段)
                    final_ans = traj.get("final_answer", "")
                    
                    # 3. 拼接
                    # 提示：实际输入模型时，这些部分通常是拼在一起的。
                    # 如果 interleaved_text 已经包含了最后的 answer (如你的样例中有 <answer> 标签)，
                    # 这里的拼接逻辑可能需要根据实际情况调整，但在做长度检查时，多拼一点比少拼一点更安全。
                    content_to_tokenize = f"{interleaved}\n{final_ans}"
                    
                elif isinstance(traj, str):
                    # 如果 trajectory 本身就是字符串
                    content_to_tokenize = traj
                
                # 如果内容为空，跳过
                if not content_to_tokenize.strip():
                    continue

                # 计算 Token
                token_ids = tokenizer.encode(content_to_tokenize, add_special_tokens=False)
                token_count = len(token_ids)
                
                if token_count > max_tokens_found:
                    max_tokens_found = token_count

                if token_count > limit:
                    over_limit_count += 1
                    sample_id = data.get("sample_id", f"Line {line_num}")
                    print(f"[超长] ID: {sample_id} | 长度: {token_count} | 超过 {limit}")

            except json.JSONDecodeError:
                print(f"[错误] 第 {line_num} 行 JSON 格式错误")

    print("-" * 30)
    print(f"统计完成 (Limit: {limit} tokens)")
    print(f"总样本数: {total_samples}")
    print(f"最大 Token 数: {max_tokens_found}")
    print(f"超长样本数: {over_limit_count}")

if __name__ == "__main__":
    # --- 配置 ---
    input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_092432_no_rubrics_incremental.jsonl"  # 你的文件名
    
    # 指向你的 Qwen3-8B 本地路径
    # 如果还没有下载，可以使用兼容的 Qwen2.5-7B
    model_path = "Qwen/Qwen2.5-7B-Instruct" 
    
    if os.path.exists(input_file):
        check_trajectory_length(input_file, model_path=model_path, limit=15384)
    else:
        print(f"文件 {input_file} 不存在，请修改脚本中的 input_file 路径。")