#!/usr/bin/env python3
"""
Fix truncated interleaved_text by completing missing </answer> tags
Uses OpenRouter API to continue writing incomplete answers
"""

import json
import os
import re
import time
import requests
import threading
import queue
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

class InterleavedTextFixer:
    def __init__(self, openrouter_api_key: str, max_workers: int = 20, input_file: str = ""):
        self.api_key = openrouter_api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.input_file = input_file
        self.progress_file = self.get_progress_filename(input_file)
        self.max_workers = max_workers
        self.api_lock = threading.Lock()  # Thread safety for API stats
        self.progress_bar_lock = threading.Lock()  # Thread safety for progress bar updates
    
    def get_progress_filename(self, input_file: str) -> str:
        """Generate progress filename based on input filename"""
        import hashlib
        if not input_file:
            return "fix_progress.json"
        
        # Extract filename from path
        import os
        basename = os.path.basename(input_file)
        name_without_ext = os.path.splitext(basename)[0]
        
        # Clean up filename (remove special chars, keep alphanumeric and underscore)
        clean_name = ''.join(c if c.isalnum() or c in ('_', '-') else '_' for c in name_without_ext)
        
        # Add hash to ensure uniqueness and avoid filename length issues
        file_hash = hashlib.md5(input_file.encode()).hexdigest()[:8]
        
        return f"fix_progress_{clean_name}_{file_hash}.json"
    
    def print_progress_bar(self, current: int, total: int, prefix: str = "", suffix: str = "", 
                          bar_length: int = 50, show_percentage: bool = True):
        """Print a progress bar to show processing progress"""
        if total == 0:
            return
            
        percentage = current / total * 100
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        
        with self.progress_bar_lock:
            if show_percentage:
                print(f'\r{prefix} |{bar}| {current}/{total} ({percentage:.1f}%) {suffix}', end='', flush=True)
            else:
                print(f'\r{prefix} |{bar}| {current}/{total} {suffix}', end='', flush=True)
            
            if current >= total:
                print()  # New line when complete
    
    def update_progress_with_stats(self, current_line: int, total_lines: int, processed_count: int, 
                                 fixed_count: int, api_success: int, api_failures: int):
        """Update progress bar with statistics"""
        suffix = f"已处理: {processed_count}, 修复: {fixed_count}, API成功: {api_success}, 失败: {api_failures}"
        self.print_progress_bar(current_line, total_lines, "进度:", suffix)
        
    def is_incomplete(self, interleaved_text: str) -> bool:
        """Check if interleaved_text is truncated"""
        start_tags = interleaved_text.count("<answer>")
        end_tags = interleaved_text.count("</answer>")
        
        # 如果开始标签多于结束标签，说明有截断
        if start_tags > end_tags:
            return True
        
        # 如果标签数量相等，检查最后一个<answer>是否有对应的</answer>
        last_answer_start = interleaved_text.rfind("<answer>")
        if last_answer_start != -1:
            remaining_text = interleaved_text[last_answer_start:]
            if "</answer>" not in remaining_text:
                return True
                
        return False
    
    def needs_completion(self, incomplete_section: str) -> bool:
        """Check if the incomplete section actually needs content completion"""
        if not incomplete_section:
            return False
        
        # 如果有<answer>标签但没有内容，肯定需要续写
        answer_content = incomplete_section.replace("<answer>", "").strip()
        if len(answer_content) == 0:
            return True
        
        # 只要没有</answer>标签，就认为内容被截断了，需要续写
        # 因为原问题提到interleaved_text要求有最终的<answer></answer>包裹的答案
        # 但有的被截断了导致没有</answer>
        # 这意味着<answer>中的内容本身就是不完整的
        
        return True
    
    def extract_last_incomplete_section(self, interleaved_text: str) -> Optional[str]:
        """Extract the last incomplete <answer> section"""
        last_answer_start = interleaved_text.rfind("<answer>")
        
        if last_answer_start == -1:
            return None
            
        incomplete_section = interleaved_text[last_answer_start:]
        
        # Already complete
        if "</answer>" in incomplete_section:
            return None
            
        return incomplete_section
    
    def call_openrouter_to_complete(self, question: str, incomplete_text: str) -> Tuple[str, bool]:
        """Call OpenRouter API to complete truncated text
        
        Returns:
            Tuple[str, bool]: (completion_text, success_status)
        """
        
        prompt = f"""I need you to help me complete a truncated answer in a tool-using conversation.

Original Question: {question}

Here's the existing conversation content (including tool calls and partial answer):
{incomplete_text}

Context: This appears to be a research process where the model was using PubMed search tools to find scientific literature and then providing a comprehensive answer. The answer was cut off mid-response.

Your task:
1. Continue the answer in a coherent and contextually appropriate manner
2. Base your continuation on the literature information already provided in the search results
3. The final answer MUST be wrapped in <answer></answer> tags
4. Maintain academic rigor and professionalism
5. The answer should be complete, accurate, and in-depth
6. Do not repeat information already stated in the existing content
7. Focus on synthesizing the research findings to comprehensively answer the original question
8. Make sure the answer flows naturally from where it was cut off
9. If there's an unclosed tag other than `<answer>`, close that tag and start writing your final answer with `<answer>`. Don't create your own content within that unclosed tag.

Please provide the completion:"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "qwen/qwen3-8b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            completion = result["choices"][0]["message"]["content"].strip()
            
            # Ensure it ends with </answer>
            if not completion.endswith("</answer>"):
                completion += "</answer>"
                
            return completion, True
            
        except requests.exceptions.HTTPError as e:
            error_detail = f"HTTP {e.response.status_code}: {e.response.text}"
            print(f"API HTTP error: {error_detail[:200]}...")
            return "</answer>", False
            
        except requests.exceptions.Timeout:
            print("API timeout after 30 seconds")
            return "</answer>", False
            
        except requests.exceptions.ConnectionError as e:
            print(f"API connection error: {str(e)[:100]}...")
            return "</answer>", False
            
        except requests.exceptions.RequestException as e:
            print(f"API request error: {str(e)[:100]}...")
            return "</answer>", False
            
        except json.JSONDecodeError as e:
            print(f"API response JSON decode error: {str(e)[:100]}...")
            return "</answer>", False
            
        except KeyError as e:
            print(f"API response missing expected key: {e}")
            return "</answer>", False
            
        except Exception as e:
            print(f"Unexpected API error: {str(e)[:100]}...")
            return "</answer>", False
    
    def fix_single_interleaved_text(self, question: str, interleaved_text: str) -> Tuple[str, bool]:
        """Fix a single truncated interleaved_text
        
        Returns:
            Tuple[str, bool]: (fixed_text, api_call_success)
        """
        
        if not self.is_incomplete(interleaved_text):
            return interleaved_text, True  # No fix needed, considered success
            
        pass
        
        # Extract incomplete section
        incomplete_section = self.extract_last_incomplete_section(interleaved_text)
        
        if incomplete_section is None:
            return interleaved_text, True
            
        pass
        
        # Check if we need content completion or just add closing tag
        if self.needs_completion(incomplete_section):
            pass
            # Call API to complete
            completion, api_success = self.call_openrouter_to_complete(question, incomplete_section)
            
            # Remove incomplete section and add completion
            last_answer_start = interleaved_text.rfind("<answer>")
            fixed_text = interleaved_text[:last_answer_start] + completion
            
            pass
                
            return fixed_text, api_success
        else:
            pass
            # Just add the missing closing tag
            fixed_text = interleaved_text + "</answer>"
            pass
            return fixed_text, True  # Tag addition always succeeds
    
    def save_progress(self, current_line: int, processed_count: int, fixed_count: int, 
                     api_completions: int, tag_additions: int, output_data: list,
                     api_success: int, api_failures: int, failed_lines: list):
        """Save current progress to file"""
        progress = {
            "current_line": current_line,
            "processed_count": processed_count,
            "fixed_count": fixed_count,
            "api_completions": api_completions,
            "tag_additions": tag_additions,
            "api_success": api_success,
            "api_failures": api_failures,
            "failed_lines": failed_lines,
            "output_data": output_data,
            "timestamp": time.time()
        }
        
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    
    def load_progress(self) -> Optional[Dict]:
        """Load progress from file"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading progress: {e}")
        return None
    
    def clear_progress(self):
        """Clear progress file"""
        if os.path.exists(self.progress_file):
            os.remove(self.progress_file)
    
    def archive_progress(self):
        """Archive progress file with timestamp"""
        if os.path.exists(self.progress_file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(self.progress_file)[0]
            archive_filename = f"{base_name}_backup_{timestamp}.json"
            
            try:
                os.rename(self.progress_file, archive_filename)
            except Exception:
                # If rename fails, try copy and delete
                try:
                    import shutil
                    shutil.copy2(self.progress_file, archive_filename)
                    os.remove(self.progress_file)
                except Exception:
                    pass
    
    def save_incremental_output(self, output_data: list, output_file: str):
        """Save output data to file incrementally"""
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for data in output_data:
                outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    def process_single_line(self, line_data: Dict) -> Tuple[Dict, bool]:
        """Process a single line (thread-safe version)
        
        Returns:
            Tuple[Dict, bool]: (processed_data, api_success)
        """
        try:
            data = line_data.copy()
            
            if 'trajectory' in data and 'interleaved_text' in data['trajectory']:
                original_text = data['trajectory']['interleaved_text']
                question = data.get('question', '')
                
                # Check and fix truncation
                if self.is_incomplete(original_text):
                    incomplete_section = self.extract_last_incomplete_section(original_text)
                    needs_api = self.needs_completion(incomplete_section) if incomplete_section else False
                    
                    fixed_text, api_success = self.fix_single_interleaved_text(question, original_text)
                    data['trajectory']['interleaved_text'] = fixed_text
                    
                    return data, api_success
                else:
                    return data, True  # No fix needed
            else:
                return data, True  # No trajectory data
                
        except Exception as e:
            pass
            return line_data, False
    
    def process_batch_parallel(self, lines_data: List[Dict], start_line: int) -> Tuple[List[Dict], int, int, List[int]]:
        """Process a batch of lines in parallel
        
        Returns:
            Tuple[List[Dict], int, int, List[int]]: (processed_data, success_count, failure_count, failed_indices)
        """
        results = [None] * len(lines_data)
        success_count = 0
        failure_count = 0
        failed_indices = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self.process_single_line, line_data): i 
                for i, line_data in enumerate(lines_data)
            }
            
            # Process results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    processed_data, api_success = future.result()
                    results[index] = processed_data
                    
                    if api_success:
                        success_count += 1
                    else:
                        failure_count += 1
                        failed_indices.append(start_line + index)
                        
                except Exception as e:
                    pass
                    results[index] = lines_data[index]  # Use original data
                    failure_count += 1
                    failed_indices.append(start_line + index)
        
        return results, success_count, failure_count, failed_indices
    
    def process_jsonl_file(self, input_file: str, output_file: str):
        """Process entire JSONL file"""
        
        # Check for existing progress
        progress = self.load_progress()
        
        if progress:
            print("发现未完成的进度，可以从断点继续:")
            print(f"  - 上次处理到第 {progress['current_line']} 行")
            print(f"  - 已处理 {progress['processed_count']} 行")
            print(f"  - 已修复 {progress['fixed_count']} 行")
            print(f"  - API调用次数: {progress['api_completions']}")
            
            # Show success/failure stats if available
            if 'api_success' in progress and 'api_failures' in progress:
                print(f"  - API成功: {progress['api_success']} 次")
                print(f"  - API失败: {progress['api_failures']} 次")
                if progress.get('failed_lines'):
                    print(f"  - 失败的行号: {progress['failed_lines']}")
            
            resume = input("是否从断点继续？(y/N): ").strip().lower()
            if resume not in ['y', 'yes']:
                print("开始新的处理...")
                self.clear_progress()
                progress = None
            else:
                print(f"从第 {progress['current_line'] + 1} 行继续处理...")
                # 如果有失败的行，也会重试那些行
                if progress.get('failed_lines'):
                    print(f"将重试之前失败的行: {progress['failed_lines']}")
        
        if not progress:
            # First pass: analyze what needs to be fixed
            print("\n正在分析文件...")
            
            # First, count total lines
            with open(input_file, 'r', encoding='utf-8') as infile:
                total_lines = sum(1 for _ in infile)
            
            print(f"\n分析 {total_lines} 行数据，查找需要修复的内容...")
            
            api_needed = 0
            tag_needed = 0
            analyzed_lines = 0
            
            with open(input_file, 'r', encoding='utf-8') as infile:
                for line_num, line in enumerate(infile, 1):
                    analyzed_lines += 1
                    try:
                        data = json.loads(line.strip())
                        
                        if 'trajectory' in data and 'interleaved_text' in data['trajectory']:
                            original_text = data['trajectory']['interleaved_text']
                            
                            if self.is_incomplete(original_text):
                                incomplete_section = self.extract_last_incomplete_section(original_text)
                                needs_api = self.needs_completion(incomplete_section) if incomplete_section else False
                                
                                if needs_api:
                                    api_needed += 1
                                else:
                                    tag_needed += 1
                        
                        # Update analysis progress every 100 lines
                        if line_num % 100 == 0 or line_num == total_lines:
                            suffix = f"找到需要修复: {api_needed + tag_needed} 项 (API: {api_needed}, 标签: {tag_needed})"
                            self.print_progress_bar(analyzed_lines, total_lines, "分析进度:", suffix)
                                    
                    except Exception:
                        continue
            
            print()  # New line after progress bar complete
            
            # Show summary and ask for confirmation
            print(f"\n=== 修复分析结果 ===")
            print(f"文件总行数: {total_lines}")
            print(f"需要修复的总条目数: {api_needed + tag_needed}")
            print(f"  - 需要API续写: {api_needed} 条")
            print(f"  - 只需添加结束标签: {tag_needed} 条")
            
            if api_needed > 0:
                estimated_cost = api_needed * 0.002
                estimated_time = api_needed * 15  # ~15 seconds per API call including delays
                print(f"\n预计API费用: ${estimated_cost:.2f} USD")
                print(f"预计处理时间: ~{estimated_time//60} 分钟")
                
                # Ask for confirmation
                # Ask for confirmation
                print(f"\n即将调用 OpenRouter API {api_needed} 次来续写截断的答案。")
                confirm = input("是否继续？(y/N): ").strip().lower()
                
                if confirm not in ['y', 'yes']:
                    print("操作已取消。")
                    return
        
        # Second pass: actually process the file
        print(f"\n开始处理文件...")
        
        # Initialize counters
        if progress:
            processed_count = progress['processed_count']
            fixed_count = progress['fixed_count']
            api_completions = progress['api_completions']
            tag_additions = progress['tag_additions']
            output_data = progress['output_data']
            start_line = progress['current_line'] + 1
            api_success = progress.get('api_success', 0)
            api_failures = progress.get('api_failures', 0)
            failed_lines = progress.get('failed_lines', [])
        else:
            processed_count = 0
            fixed_count = 0
            api_completions = 0
            tag_additions = 0
            output_data = []
            start_line = 1
            api_success = 0
            api_failures = 0
            failed_lines = []
        
        # First, retry any previously failed lines (if any)
        if progress and failed_lines:
            print(f"重试之前失败的 {len(failed_lines)} 行 (并行处理)...")
            retry_lines = failed_lines.copy()
            retry_data = []
            retry_indices = []
            
            with open(input_file, 'r', encoding='utf-8') as infile:
                lines = infile.readlines()
                
                for failed_line_num in retry_lines:
                    if failed_line_num <= len(lines):
                        try:
                            line = lines[failed_line_num - 1]
                            data = json.loads(line.strip())
                            retry_data.append(data)
                            retry_indices.append(failed_line_num - 1)  # Convert to 0-based index
                        except Exception as e:
                            pass
            
            if retry_data:
                print(f"\n重试 {len(retry_data)} 个之前失败的项目...")
                retry_results, retry_success, retry_failure, retry_failed_indices = self.process_batch_parallel(retry_data, 0)
                
                # Update output_data with retry results
                for i, result_index in enumerate(retry_indices):
                    if result_index < len(output_data):
                        output_data[result_index] = retry_results[i]
                
                api_success += retry_success
                api_failures += retry_failure
                api_completions += retry_success + retry_failure
                
                # Update failed_lines list
                new_failed_lines = []
                for i, original_line_num in enumerate(retry_lines):
                    if (i < len(retry_failed_indices) and retry_failed_indices[i] is not None):
                        new_failed_lines.append(original_line_num)
                
                failed_lines = new_failed_lines
                print(f"重试完成: 成功 {retry_success}, 失败 {retry_failure}")
        
        # Then process new lines in parallel batches
        print(f"\n继续处理新行，从第 {start_line} 行开始 (并行处理)...")
        batch_size = 20  # Process 20 lines at a time
        save_interval = 20  # Save progress every 20 lines
        
        with open(input_file, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
            total_lines = len(lines)
            
            print(f"\n总共需要处理 {total_lines} 行数据")
            print(f"进度条:")
            
            # Process in batches
            for batch_start in range(start_line - 1, total_lines, batch_size):
                batch_end = min(batch_start + batch_size, total_lines)
                batch_lines = lines[batch_start:batch_end]
                
                # Parse batch data
                batch_data = []
                for line in batch_lines:
                    try:
                        data = json.loads(line.strip())
                        batch_data.append(data)
                    except Exception as e:
                        # Add empty data to maintain indices
                        batch_data.append({})
                
                # Process batch in parallel
                batch_results, batch_success, batch_failure, batch_failed_indices = self.process_batch_parallel(
                    batch_data, batch_start + 1
                )
                
                # Update counters
                api_success += batch_success
                api_failures += batch_failure
                api_completions += batch_success + batch_failure
                
                # Update failed_lines with new failures
                for failed_idx in batch_failed_indices:
                    failed_lines.append(failed_idx)
                
                # Count fixed items
                for i, original_data in enumerate(batch_data):
                    if original_data and 'trajectory' in original_data and 'interleaved_text' in original_data['trajectory']:
                        if self.is_incomplete(original_data['trajectory']['interleaved_text']):
                            fixed_count += 1
                
                # Add to output_data
                if progress and batch_start < len(output_data):
                    # Update existing data
                    for i, result in enumerate(batch_results):
                        if batch_start + i < len(output_data):
                            output_data[batch_start + i] = result
                        else:
                            output_data.append(result)
                else:
                    # Append new data
                    output_data.extend(batch_results)
                
                processed_count = len(output_data)
                current_line = batch_end
                
                # Update progress bar
                self.update_progress_with_stats(current_line, total_lines, processed_count, 
                                             fixed_count, api_success, api_failures)
                
                # Save progress periodically
                if current_line % save_interval == 0:
                    self.save_progress(current_line, processed_count, fixed_count, 
                                     api_completions, tag_additions, output_data,
                                     api_success, api_failures, failed_lines)
                    self.save_incremental_output(output_data, output_file)
                
                # Brief pause between batches to avoid overwhelming the API
                if batch_success > 0:
                    time.sleep(1)
        
        # Final save
        self.save_incremental_output(output_data, output_file)
        
        print(f"\n=== 并行处理完成 ===")
        print(f"总行数: {processed_count}")
        print(f"修复条目数: {fixed_count}")
        print(f"  - API调用次数: {api_completions}")
        print(f"    - API成功: {api_success}")
        print(f"    - API失败: {api_failures}")
        print(f"  - 添加结束标签: {tag_additions}")
        
        if failed_lines:
            print(f"  - 仍有失败的行: {failed_lines}")
            print(f"    可以重新运行脚本重试这些行")
        
        print(f"输出文件: {output_file}")
        print(f"并发线程数: {self.max_workers}")
        
        if api_success > 0:
            actual_cost = api_success * 0.002  # Only count successful API calls
            print(f"实际API费用: ${actual_cost:.2f} USD ({api_success} 次成功调用)")
            
            # Calculate time saved compared to sequential processing
            estimated_sequential_time = api_success * 15  # ~15 seconds per call sequentially
            estimated_parallel_time = estimated_sequential_time / self.max_workers
            time_saved_minutes = (estimated_sequential_time - estimated_parallel_time) / 60
            print(f"并发处理节省约 {time_saved_minutes:.1f} 分钟")
            
        if failed_lines:
            print(f"\n注意: 有 {len(failed_lines)} 行处理失败，重新运行脚本将自动重试这些行。")
            print("进度文件已保留，便于下次继续处理。")
        else:
            print(f"\n所有条目处理成功！")
            self.archive_progress()  # Archive progress file with timestamp instead of deleting


def preview_fixes(input_file: str, limit: int = 5):
    """Preview what needs to be fixed without making changes"""
    
    print("=== PREVIEW OF NEEDED FIXES ===\n")
    
    api_needed = 0
    tag_needed = 0
    
    with open(input_file, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, 1):
            try:
                data = json.loads(line.strip())
                
                if 'trajectory' in data and 'interleaved_text' in data['trajectory']:
                    original_text = data['trajectory']['interleaved_text']
                    question = data.get('question', '')
                    
                    # Create temporary fixer for analysis
                    temp_fixer = InterleavedTextFixer("dummy_key", input_file=input_file)
                    
                    if temp_fixer.is_incomplete(original_text):
                        incomplete_section = temp_fixer.extract_last_incomplete_section(original_text)
                        needs_api = temp_fixer.needs_completion(incomplete_section) if incomplete_section else False
                        
                        if needs_api:
                            api_needed += 1
                        else:
                            tag_needed += 1
                        
                        # Show examples
                        if api_needed + tag_needed <= limit:
                            print(f"Line {line_num} - {'API NEEDED' if needs_api else 'TAG NEEDED'}")
                            print(f"Question: {question[:100]}...")
                            print(f"Incomplete section: {incomplete_section[:150]}...")
                            print("-" * 80)
                        
            except Exception as e:
                continue
    
    print(f"\n=== SUMMARY ===")
    print(f"Total lines needing fixes: {api_needed + tag_needed}")
    print(f"  - Need API completion: {api_needed}")
    print(f"  - Need closing tags only: {tag_needed}")
    
    if api_needed > 0:
        print(f"\nEstimated API cost: ${api_needed * 0.002:.2f} USD")

def main():
    # Check command line arguments
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--preview":
            # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_060613_no_rubrics_incremental.jsonl"
            input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_092432_no_rubrics_incremental.jsonl"
            if not os.path.exists(input_file):
                print(f"Error: Input file does not exist: {input_file}")
                return
            preview_fixes(input_file)
            return
        
        elif sys.argv[1] == "--clear-progress":
            # Clear progress files (can specify input file or clear all)
            if len(sys.argv) > 2 and sys.argv[2] != "--all":
                input_file = sys.argv[2]
                if not os.path.exists(input_file):
                    print(f"Error: Input file does not exist: {input_file}")
                    return
                fixer = InterleavedTextFixer("dummy_key", input_file=input_file)
                fixer.clear_progress()
                print(f"Progress file cleared for: {input_file}")
            else:
                # Clear all progress files
                import glob
                progress_files = glob.glob("fix_progress_*.json")
                if progress_files:
                    print(f"Deleting {len(progress_files)} progress files...")
                    for pf in progress_files:
                        try:
                            os.remove(pf)
                            print(f"  Deleted: {pf}")
                        except Exception as e:
                            print(f"  Error deleting {pf}: {e}")
                    print("All progress files cleared.")
                else:
                    print("No progress files found.")
            return
        
        elif sys.argv[1] == "--list-backups":
            # List backup files (can specify input file or list all)
            import glob
            if len(sys.argv) > 2 and sys.argv[2] != "--all":
                input_file = sys.argv[2]
                if not os.path.exists(input_file):
                    print(f"Error: Input file does not exist: {input_file}")
                    return
                fixer = InterleavedTextFixer("dummy_key", input_file=input_file)
                base_name = os.path.splitext(fixer.progress_file)[0]
                backup_files = glob.glob(f"{base_name}_backup_*.json")
                print(f"Backup files for {os.path.basename(input_file)}:")
            else:
                # List all backup files
                backup_files = glob.glob("fix_progress_*_backup_*.json")
                print("All backup files:")
            
            if backup_files:
                for backup in sorted(backup_files):
                    try:
                        # Extract timestamp from filename
                        parts = backup.split('_backup_')
                        if len(parts) == 2:
                            timestamp_str = parts[1].replace('.json', '')
                            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                            size = os.path.getsize(backup) / (1024*1024)  # Size in MB
                            print(f"  {backup} ({formatted_time}, {size:.1f} MB)")
                        else:
                            print(f"  {backup}")
                    except Exception as e:
                        print(f"  {backup}")
            else:
                print("No backup files found.")
            return
        
        elif sys.argv[1] == "--clean-backups":
            # Clean backup files (can specify input file or clean all)
            import glob
            if len(sys.argv) > 2 and sys.argv[2] != "--all":
                input_file = sys.argv[2]
                if not os.path.exists(input_file):
                    print(f"Error: Input file does not exist: {input_file}")
                    return
                fixer = InterleavedTextFixer("dummy_key", input_file=input_file)
                base_name = os.path.splitext(fixer.progress_file)[0]
                backup_files = glob.glob(f"{base_name}_backup_*.json")
                print(f"Deleting backup files for {os.path.basename(input_file)}...")
            else:
                # Clean all backup files
                backup_files = glob.glob("fix_progress_*_backup_*.json")
                print(f"Deleting {len(backup_files)} backup files...")
            
            if backup_files:
                for backup in backup_files:
                    try:
                        os.remove(backup)
                        print(f"  Deleted: {backup}")
                    except Exception as e:
                        print(f"  Error deleting {backup}: {e}")
                print("Backup cleanup completed.")
            else:
                print("No backup files to delete.")
            return
        
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python fix_interleaved_text.py                     # Run with resume check (20 workers)")
            print("  python fix_interleaved_text.py --workers=N        # Use N concurrent workers")
            print("  python fix_interleaved_text.py --preview          # Preview what needs fixing")
            print("  python fix_interleaved_text.py --clear-progress [file|all]    # Clear progress for specific file or all")
            print("  python fix_interleaved_text.py --list-backups [file|all]       # List backup files for specific file or all")
            print("  python fix_interleaved_text.py --clean-backups [file|all]      # Delete backup files for specific file or all")
            print("  python fix_interleaved_text.py --help             # Show this help")
            print("")
            print("Progress Files:")
            print("  - Progress files are now tied to input filenames")
            print("  - Each input file has its own progress and backup files")
            print("  - Format: fix_progress_{filename}_{hash}.json")
            print("  - Backup format: fix_progress_{filename}_{hash}_backup_{timestamp}.json")
            print("")
            print("Examples:")
            print("  python fix_interleaved_text.py --clear-progress data.jsonl    # Clear progress for data.jsonl")
            print("  python fix_interleaved_text.py --clear-progress all          # Clear all progress files")
            print("  python fix_interleaved_text.py --list-backups data.jsonl     # List backups for data.jsonl")
            print("  python fix_interleaved_text.py --workers=30                 # Use 30 concurrent threads")
            return
    
    # Get API key from environment variable
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    if not api_key:
        print("Error: Please set OPENROUTER_API_KEY environment variable")
        print("Example: export OPENROUTER_API_KEY='your-api-key-here'")
        print("Or run with --preview to see what needs fixing without API calls")
        return
    
    # Input and output file paths
    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_060613_no_rubrics_incremental.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_060613_no_rubrics_incremental_fixed.jsonl"
    
    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_092432_no_rubrics_incremental.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_092432_no_rubrics_incremental_fixed.jsonl"

    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_135723_no_rubrics_incremental.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_135723_no_rubrics_incremental_fixed.jsonl"

    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251220_144143_no_rubrics_incremental.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251220_144143_no_rubrics_incremental_fixed.jsonl"

    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据2.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据2_fixed.jsonl"

    # input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据3.jsonl"
    # output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据3_fixed.jsonl"

    input_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据4.jsonl"
    output_file = "/Users/liyc/Desktop/dr-tulu/交付数据/tulu数据4_fixed.jsonl"

    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file does not exist: {input_file}")
        return
    
    # Check for custom worker count
    workers = 30  # default
    for arg in sys.argv[1:]:
        if arg.startswith("--workers="):
            try:
                workers = int(arg.split("=")[1])
                print(f"使用自定义并发数: {workers}")
                break
            except:
                print(f"无效的并发数设置，使用默认值: {workers}")
                break
    
    # Create fixer and process file
    fixer = InterleavedTextFixer(api_key, max_workers=workers, input_file=input_file)
    fixer.process_jsonl_file(input_file, output_file)


if __name__ == "__main__":
    main()