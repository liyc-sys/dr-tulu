import os
import json
import csv
from datasets import load_dataset
import pandas as pd

def safe_serialize(obj):
    """
    辅助函数：将列表或字典转换为 JSON 字符串，
    防止内部的逗号或结构破坏 CSV 格式。
    """
    if isinstance(obj, (list, dict)):
        return json.dumps(obj, ensure_ascii=False)
    return obj

def download_and_convert_robust(dataset_name, output_dir="tulu_data_robust"):
    print(f"正在下载数据集: {dataset_name} ...")
    
    try:
        # 1. 加载数据集
        ds = load_dataset(dataset_name)
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        print(f"数据集包含的部分: {list(ds.keys())}")

        for split in ds.keys():
            print(f"正在处理 '{split}' ...")
            
            # 转换为 Pandas DataFrame
            df = ds[split].to_pandas()
            
            # ---------------------------------------------------------
            # 关键步骤 1：处理复杂数据类型
            # 遍历所有列，如果是 list 或 dict，转换成 JSON 字符串
            # ---------------------------------------------------------
            for col in df.columns:
                # 检查第一条非空数据来判断类型
                first_valid = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
                if isinstance(first_valid, (list, dict)):
                    print(f"  - 检测到列 '{col}' 包含复杂结构，正在序列化为 JSON 字符串...")
                    df[col] = df[col].apply(safe_serialize)
            
            # 定义输出路径
            output_file = os.path.join(output_dir, f"dr_tulu_{split}.csv")
            
            # ---------------------------------------------------------
            # 关键步骤 2：使用更严格的 CSV 参数保存
            # quoting=csv.QUOTE_ALL: 强制给所有字段加引号
            # escapechar='\\': 遇到特殊字符时使用反斜杠转义
            # ---------------------------------------------------------
            df.to_csv(
                output_file, 
                index=False, 
                encoding='utf-8-sig', 
                quoting=csv.QUOTE_ALL,  # 强制引用所有字段，这是防止错位的关键
                escapechar='\\'         # 处理引号冲突
            )
            
            print(f"成功保存: {output_file} (行数: {len(df)})")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    DATASET_ID = "rl-research/dr-tulu-rl-data"
    download_and_convert_robust(DATASET_ID)