# Interleaved Text Fixer Usage Instructions

## Overview
This script fixes truncated `interleaved_text` entries in the PubMed trajectory JSONL file by completing missing `</answer>` tags using OpenRouter API.

## Setup

1. **Set up OpenRouter API key:**
   ```bash
   export OPENROUTER_API_KEY='your-openrouter-api-key-here'
   ```

2. **Install required dependencies:**
   ```bash
   pip install requests
   ```

## Running the Script

### 1. Preview Mode (Recommended First)
```bash
cd /Users/liyc/Desktop/dr-tulu
python fix_interleaved_text.py --preview
```
This shows what needs fixing without making any API calls.

### 2. Full Fix Mode with Parallel Processing
```bash
# Default 20 concurrent workers
python fix_interleaved_text.py

# Custom number of workers (recommended: 10-50)
python fix_interleaved_text.py --workers=30
```
This performs the actual fixes and API calls with 20 concurrent threads by default. If interrupted, it will offer to resume from where it left off.

### 3. Clear Progress
```bash
python fix_interleaved_text.py --clear-progress
```
Clears any saved progress and starts fresh next time.

### 4. Manage Backup Files
```bash
# List all backup files with timestamps and sizes
python fix_interleaved_text.py --list-backups

# Delete all backup files
python fix_interleaved_text.py --clean-backups
```

### 5. Help
```bash
python fix_interleaved_text.py --help
```
Shows all available options.

## What it does:

1. **Detection**: Identifies truncated entries where `<answer>` tags don't have matching `</answer>` tags
2. **Context Analysis**: Extracts the incomplete section and original question
3. **API Completion**: Calls OpenRouter API with Claude-3.5-Sonnet to complete the answer
4. **Integration**: Replaces the incomplete section with the completed answer
5. **Output**: Creates a new file with `_fixed.jsonl` suffix

## Input/Output

- **Input**: `pubmed_trajectory_20251218_060613_no_rubrics_incremental.jsonl`
- **Output**: `pubmed_trajectory_20251218_060613_no_rubrics_incremental_fixed.jsonl`

## Features

- **Parallel Processing**: Uses 20 concurrent threads by default for maximum speed
- **Smart Detection**: Differentiates between incomplete content vs missing closing tags
- **Selective API Usage**: Only calls API for actual content completion, not just adding missing tags
- **Resume Support**: Automatically saves progress every 20 lines, can resume from interruptions
- **Failure Retry**: Automatically retries failed API calls on subsequent runs
- **Success/Failure Tracking**: Shows detailed statistics of API call success and failure rates
- **Batch Processing**: Processes lines in batches of 20 for optimal performance
- **Incremental Saving**: Output file is updated continuously, no data lost if interrupted
- **Time Savings**: Calculates and displays time saved through parallel processing
- **Error Handling**: Continues processing even if individual entries fail
- **Progress Tracking**: Shows batch processing progress and completion statistics
- **Cost Tracking**: Only counts successful API calls for cost estimation
- **Configurable Concurrency**: Adjust worker count with --workers parameter
- **Automatic Backups**: Completed progress files are archived with timestamps
- **Backup Management**: List and clean backup files with built-in commands
- **Progress Management**: Commands to clear saved progress or start fresh
- **Preservation**: Original file remains unchanged

## Detection Logic

The script distinguishes between two cases:

1. **Needs API Completion**: 
   - Answer content is very short (<50 characters)
   - Answer ends with incomplete indicators (..., 。, ；, ，, " and ", " the ", etc.)
   - Content appears to be cut off mid-sentence

2. **Only Needs Closing Tag**:
   - Content appears complete but missing `</answer>` tag
   - No API call needed, just adds `</answer>`

## Backup and Progress Management

### Automatic Backup System
- **Completed Runs**: Progress files are automatically renamed with timestamps (e.g., `fix_progress_backup_20251220_143022.json`)
- **Failed Runs**: Progress files are kept for resuming (`fix_progress.json`)
- **Backup Format**: Includes all processing data, statistics, and results

### Backup File Management
```bash
# List all backup files with details
python fix_interleaved_text.py --list-backups

# Output example:
Found backup files:
  fix_progress_backup_20251220_143022.json (2025-12-20 14:30:22, 12.5 MB)
  fix_progress_backup_20251219_102156.json (2025-12-19 10:21:56, 8.3 MB)

# Clean all backup files
python fix_interleaved_text.py --clean-backups
```

### Progress File Scenarios
1. **Successful Completion**: `fix_progress.json` → `fix_progress_backup_TIMESTAMP.json`
2. **Partial Completion/Failures**: `fix_progress.json` remains for resuming
3. **Manual Clear**: `python fix_interleaved_text.py --clear-progress`

## Failure Retry Mechanism

The script includes intelligent failure handling:

1. **Failed API Tracking**: When an API call fails, the line number is recorded in the progress file
2. **Automatic Retry**: On the next run, failed lines are retried first before processing new lines
3. **Success Rate Display**: Shows both successful and failed API call counts
4. **Accurate Cost**: Only successful API calls are counted for cost estimation
5. **Progress Preservation**: Failed lines remain in the failed list until successfully processed

### Example Output:

```
=== 并行处理完成 ===
总行数: 200
修复条目数: 152
  - API调用次数: 152
    - API成功: 148
    - API失败: 4
  - 添加结束标签: 0
并发线程数: 20
实际API费用: $0.30 USD (148 次成功调用)
并发处理节省约 36.0 分钟
进度文件已备份为: fix_progress_backup_20251220_143022.json

所有条目处理成功！
```

## Performance

With 20 concurrent workers:
- **Sequential Processing**: ~38 minutes (152 calls × 15 seconds)
- **Parallel Processing**: ~2 minutes (38 ÷ 20)
- **Time Savings**: ~36 minutes (95% faster)

With custom workers:
- **10 workers**: ~4 minutes
- **30 workers**: ~1.3 minutes  
- **50 workers**: ~45 seconds

## Expected Results

Based on analysis:
- **Total entries**: 200
- **Truncated entries**: ~152 (180 `<answer>` tags vs 28 `</answer>` tags)
- **Split estimate**: 
  - ~152 actual content completions (need API)
  - ~0 missing closing tags (no API needed)
- **Estimated API calls**: ~152
- **Estimated cost**: ~$0.30 USD (assuming 95% success rate)
- **Estimated time with 20 workers**: ~2-3 minutes (including rate limiting delays and retries)