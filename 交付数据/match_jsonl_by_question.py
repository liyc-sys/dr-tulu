#!/usr/bin/env python3
"""
Match data from two JSONL files based on question field
Creates paired datasets where questions are the same
"""

import json
import os
import sys
from typing import Dict, List, Tuple, Set
from collections import defaultdict

class QuestionMatcher:
    def __init__(self, file1_path: str, file2_path: str):
        self.file1_path = file1_path
        self.file2_path = file2_path
        self.file1_questions = {}
        self.file2_questions = {}
        self.common_questions = set()
        
    def load_jsonl_file(self, file_path: str) -> Tuple[Dict[str, dict], List[str]]:
        """Load JSONL file and return question mapping and list of questions"""
        questions = {}
        question_list = []
        duplicate_questions = []
        
        print(f"正在加载文件: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())
                    question = data.get('question', '').strip()
                    
                    if question:
                        if question in questions:
                            duplicate_questions.append(question)
                            print(f"发现重复问题 (行 {line_num}): {question[:50]}...")
                        else:
                            questions[question] = data
                            question_list.append(question)
                    else:
                        print(f"警告: 行 {line_num} 没有question字段")
                        
                except json.JSONDecodeError as e:
                    print(f"警告: 行 {line_num} JSON解析错误: {e}")
                except Exception as e:
                    print(f"警告: 行 {line_num} 处理错误: {e}")
        
        print(f"文件加载完成: {len(questions)} 个问题")
        if duplicate_questions:
            print(f"发现 {len(duplicate_questions)} 个重复问题")
            for q in set(duplicate_questions[:5]):  # 只显示前5个重复问题
                print(f"  - {q[:50]}...")
        
        return questions, question_list
    
    def validate_questions(self) -> bool:
        """Validate that questions are unique in both files"""
        print("\n=== 验证问题唯一性 ===")
        
        # Load both files
        self.file1_questions, file1_q_list = self.load_jsonl_file(self.file1_path)
        self.file2_questions, file2_q_list = self.load_jsonl_file(self.file2_path)
        
        # Check uniqueness in file1
        file1_unique = len(self.file1_questions) == len(file1_q_list)
        print(f"文件1问题唯一性: {'通过' if file1_unique else '失败'}")
        
        # Check uniqueness in file2  
        file2_unique = len(self.file2_questions) == len(file2_q_list)
        print(f"文件2问题唯一性: {'通过' if file2_unique else '失败'}")
        
        if not file1_unique or not file2_unique:
            print("\n错误: 文件中存在重复问题，无法进行一一对应匹配")
            return False
        
        return True
    
    def find_common_questions(self):
        """Find common questions between the two files"""
        print("\n=== 查找共同问题 ===")
        
        questions1 = set(self.file1_questions.keys())
        questions2 = set(self.file2_questions.keys())
        
        self.common_questions = questions1.intersection(questions2)
        
        print(f"文件1总问题数: {len(questions1)}")
        print(f"文件2总问题数: {len(questions2)}")
        print(f"共同问题数: {len(self.common_questions)}")
        print(f"文件1独有问题: {len(questions1 - questions2)}")
        print(f"文件2独有问题: {len(questions2 - questions1)}")
        
        return len(self.common_questions)
    
    def create_paired_files(self, output1_path: str, output2_path: str):
        """Create paired JSONL files with matching questions"""
        print(f"\n=== 创建配对文件 ===")
        
        if not self.common_questions:
            print("错误: 没有找到共同问题")
            return False
        
        # Sort questions for consistent ordering
        sorted_questions = sorted(self.common_questions)
        
        print(f"正在创建 {len(sorted_questions)} 对配对数据...")
        
        matched_count = 0
        
        with open(output1_path, 'w', encoding='utf-8') as out1, \
             open(output2_path, 'w', encoding='utf-8') as out2:
            
            for i, question in enumerate(sorted_questions):
                # Get corresponding data from both files
                data1 = self.file1_questions[question]
                data2 = self.file2_questions[question]
                
                # Write to output files (maintaining original order)
                out1.write(json.dumps(data1, ensure_ascii=False) + '\n')
                out2.write(json.dumps(data2, ensure_ascii=False) + '\n')
                
                matched_count += 1
                
                # Progress indicator
                if (i + 1) % 1000 == 0 or (i + 1) == len(sorted_questions):
                    print(f"已处理: {i + 1}/{len(sorted_questions)} ({(i + 1)/len(sorted_questions)*100:.1f}%)")
        
        print(f"\n配对文件创建完成:")
        print(f"  - 输出文件1: {output1_path} ({matched_count} 行)")
        print(f"  - 输出文件2: {output2_path} ({matched_count} 行)")
        
        return True
    
    def save_unmatched_questions(self, output_dir: str = "."):
        """Save unmatched questions for reference"""
        print(f"\n=== 保存未匹配问题 ===")
        
        questions1 = set(self.file1_questions.keys())
        questions2 = set(self.file2_questions.keys())
        
        # File1 only questions
        file1_only = questions1 - questions2
        file2_only = questions2 - questions1
        
        # Save file1 only questions
        if file1_only:
            file1_only_path = os.path.join(output_dir, "file1_only_questions.jsonl")
            with open(file1_only_path, 'w', encoding='utf-8') as f:
                for question in sorted(file1_only):
                    data = self.file1_questions[question]
                    f.write(json.dumps(data, ensure_ascii=False) + '\n')
            print(f"文件1独有问题保存至: {file1_only_path} ({len(file1_only)} 个)")
        
        # Save file2 only questions
        if file2_only:
            file2_only_path = os.path.join(output_dir, "file2_only_questions.jsonl")
            with open(file2_only_path, 'w', encoding='utf-8') as f:
                for question in sorted(file2_only):
                    data = self.file2_questions[question]
                    f.write(json.dumps(data, ensure_ascii=False) + '\n')
            print(f"文件2独有问题保存至: {file2_only_path} ({len(file2_only)} 个)")

def main():
    # 硬编码的文件路径
    file1_path = "/Users/liyc/Desktop/dr-tulu/交付数据/4次数据收集_纯净.jsonl"
    file2_path = "/Users/liyc/Desktop/dr-tulu/交付数据/4次tulu数据收集_纯净.jsonl"
    output_dir = "/Users/liyc/Desktop/dr-tulu/交付数据"
    
    # 生成输出文件路径
    output1_path = os.path.join(output_dir, "matched_data_1.jsonl")
    output2_path = os.path.join(output_dir, "matched_data_2.jsonl")
    
    print(f"开始匹配问题...")
    print(f"文件1: {file1_path}")
    print(f"文件2: {file2_path}")
    print(f"输出目录: {output_dir}")
    
    # 检查输入文件是否存在
    if not os.path.exists(file1_path):
        print(f"错误: 文件不存在: {file1_path}")
        return
    
    if not os.path.exists(file2_path):
        print(f"错误: 文件不存在: {file2_path}")
        return
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # Create matcher and process
    matcher = QuestionMatcher(file1_path, file2_path)
    
    # Validate question uniqueness
    if not matcher.validate_questions():
        print("验证失败，程序终止")
        return
    
    # Find common questions
    common_count = matcher.find_common_questions()
    
    if common_count == 0:
        print("没有找到共同问题，程序终止")
        return
    
    # Create paired files
    if matcher.create_paired_files(output1_path, output2_path):
        # Save unmatched questions
        matcher.save_unmatched_questions(output_dir)
        
        print(f"\n=== 匹配完成 ===")
        print(f"成功匹配 {common_count} 对问题")
        print(f"输出文件1: {output1_path}")
        print(f"输出文件2: {output2_path}")
        print(f"未匹配文件保存在: {output_dir}")
    else:
        print("配对文件创建失败")

if __name__ == "__main__":
    main()