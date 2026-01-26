"""
医学数据扩增脚本
使用OpenRouter调用模型，将问题改写成3种不同风格
实现1+3=4倍数据扩增，增量保存，支持并发
"""

import pandas as pd
import aiohttp
import asyncio
import json
import os
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm

# OpenRouter API配置
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "your-api-key-here")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# 并发配置
CONCURRENT_REQUESTS = 10  # 同时处理的请求数
BATCH_SIZE = 20  # 每批处理的数据条数

# 文件路径
INPUT_FILE = "/Users/liyc/Desktop/dr-tulu/训练和benchmark数据0120/MedBrowseComp_605_part2.csv"
OUTPUT_FILE = "/Users/liyc/Desktop/dr-tulu/0126med扩增/MedBrowseComp_augmented.csv"
PROGRESS_FILE = "/Users/liyc/Desktop/dr-tulu/0126med扩增/progress.json"

# 三种改写风格的prompt
STYLE_PROMPTS = {
    "style1_formal": """Rephrase the following medical query in a more formal and academic style.

Requirements:
1. Use more professional and scholarly terminology
2. Make the sentence structure more rigorous and formal
3. Keep all key information (clinical trial IDs, letter requirements, date formats, etc.) exactly the same
4. The output format must match the original exactly
5. Output must be in English

Original question:
{question}

Output only the rephrased question with no explanation or prefix:""",

    "style2_concise": """Rephrase the following medical query in a more concise and direct style.

Requirements:
1. Remove redundant expressions, make the language more succinct
2. Use shorter sentence structures
3. Keep all key information (clinical trial IDs, letter requirements, date formats, etc.) exactly the same
4. The output format must match the original exactly
5. Output must be in English

Original question:
{question}

Output only the rephrased question with no explanation or prefix:""",

    "style3_stepwise": """Rephrase the following medical query in a step-by-step guided style.

Requirements:
1. Break down the query process into clearer steps
2. Use guide words like "First...", "Then...", "Finally..."
3. Keep all key information (clinical trial IDs, letter requirements, date formats, etc.) exactly the same
4. The output format must match the original exactly
5. Output must be in English

Original question:
{question}

Output only the rephrased question with no explanation or prefix:"""
}


async def call_api(session: aiohttp.ClientSession, prompt: str, semaphore: asyncio.Semaphore, max_retries: int = 3) -> str:
    """异步调用OpenRouter API"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
    }

    data = {
        "model": "google/gemini-2.5-pro-preview",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }

    async with semaphore:
        for attempt in range(max_retries):
            try:
                async with session.post(
                    OPENROUTER_BASE_URL,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    print(f"API调用失败: {e}")
                    return None
    return None


async def process_single_row(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore,
                             idx: int, row: pd.Series) -> tuple:
    """处理单行数据，生成3种风格的改写"""
    question = row["prompt"]
    gold = row["gold"]
    task_name = row["task_name"]

    # 并发生成3种风格
    tasks = []
    for style_name, style_prompt in STYLE_PROMPTS.items():
        prompt = style_prompt.format(question=question)
        tasks.append(call_api(session, prompt, semaphore))

    results = await asyncio.gather(*tasks)

    augmented_rows = []
    style_names = list(STYLE_PROMPTS.keys())

    success = True
    for i, augmented_question in enumerate(results):
        if augmented_question is None:
            success = False
            break
        augmented_rows.append({
            "gold": gold,
            "prompt": augmented_question,
            "task_name": task_name,
            "style": style_names[i]
        })

    return idx, augmented_rows if success else None


def load_progress() -> dict:
    """加载进度信息"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_indices": [], "last_index": -1}


def save_progress(progress: dict):
    """保存进度信息"""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def load_or_create_output_df(input_df: pd.DataFrame) -> pd.DataFrame:
    """加载已有输出文件或创建新的DataFrame"""
    if os.path.exists(OUTPUT_FILE):
        return pd.read_csv(OUTPUT_FILE)
    columns = list(input_df.columns) + ["style"]
    return pd.DataFrame(columns=columns)


async def main():
    print("=" * 60)
    print("医学数据扩增脚本 - 并发版本")
    print(f"并发数: {CONCURRENT_REQUESTS}, 批次大小: {BATCH_SIZE}")
    print("=" * 60)

    if OPENROUTER_API_KEY == "your-api-key-here":
        print("\n错误: 请设置OPENROUTER_API_KEY环境变量")
        return

    # 加载输入数据
    print(f"\n加载输入文件: {INPUT_FILE}")
    input_df = pd.read_csv(INPUT_FILE)
    total_rows = len(input_df)
    print(f"总共 {total_rows} 条原始数据")

    # 加载进度
    progress = load_progress()
    processed_set = set(progress["processed_indices"])
    print(f"已处理 {len(processed_set)} 条数据")

    # 加载或创建输出DataFrame
    output_df = load_or_create_output_df(input_df)

    # 如果输出文件为空，先添加原始数据
    if len(output_df) == 0:
        print("\n添加原始数据到输出文件...")
        original_data = input_df.copy()
        original_data["style"] = "original"
        output_df = pd.concat([output_df, original_data], ignore_index=True)
        output_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
        print(f"已保存原始数据 ({len(original_data)} 条)")

    # 筛选未处理的数据
    pending_indices = [i for i in range(total_rows) if i not in processed_set]
    print(f"待处理: {len(pending_indices)} 条数据")

    if not pending_indices:
        print("所有数据已处理完毕!")
        return

    # 创建信号量控制并发
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    # 分批处理
    async with aiohttp.ClientSession() as session:
        for batch_start in range(0, len(pending_indices), BATCH_SIZE):
            batch_indices = pending_indices[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(pending_indices) + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n处理批次 {batch_num}/{total_batches} ({len(batch_indices)} 条)")

            # 并发处理当前批次
            tasks = [
                process_single_row(session, semaphore, idx, input_df.iloc[idx])
                for idx in batch_indices
            ]

            results = await tqdm_asyncio.gather(*tasks, desc=f"批次 {batch_num}")

            # 收集成功的结果
            new_rows = []
            successful_indices = []

            for idx, augmented_rows in results:
                if augmented_rows is not None:
                    new_rows.extend(augmented_rows)
                    successful_indices.append(idx)

            # 批量保存
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                output_df = pd.concat([output_df, new_df], ignore_index=True)
                output_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

                # 更新进度
                processed_set.update(successful_indices)
                progress["processed_indices"] = list(processed_set)
                progress["last_index"] = max(successful_indices)
                save_progress(progress)

                print(f"✓ 批次完成: 成功 {len(successful_indices)}/{len(batch_indices)}, 总数据: {len(output_df)}")

    print("\n" + "=" * 60)
    print("扩增完成!")
    print(f"原始数据: {total_rows} 条")
    print(f"扩增后总数据: {len(output_df)} 条")
    print(f"输出文件: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
