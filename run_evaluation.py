#!/usr/bin/env python3
"""
简化的评估启动脚本
"""

import os
import sys
import asyncio
from evaluate_with_gpt4o import RubricsEvaluator

async def main():
    # 配置参数
    config = {
        # API设置
        "api_key": os.getenv("OPENROUTER_API_KEY", "sk-or-v1-your-key-here"),
        
        # 文件路径
        "rubrics_file": "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test.jsonl",
        "dporollout_input": "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_dporollout.jsonl",
        "dporollout_output": "/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl",
        "tulurollout_input": "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_test_tulurollout.jsonl",
        "tulurollout_output": "/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl",
        
        # 处理设置
        "concurrency": 3,  # 并发数
        "timeout": 300,    # 超时时间（秒）
    }
    
    # 验证API密钥
    if config["api_key"] == "sk-or-v1-your-key-here":
        print("❌ 错误: 请设置OPENROUTER_API_KEY环境变量")
        print("   运行: export OPENROUTER_API_KEY='your-api-key'")
        sys.exit(1)
    
    print("🚀 启动GPT-4o评估工具")
    print("="*50)
    
    # 创建评估器
    evaluator = RubricsEvaluator(config["api_key"])
    
    # 加载rubrics
    print("📋 加载评估标准...")
    rubrics_map = evaluator.load_rubrics(config["rubrics_file"])
    
    # 询问用户要处理哪个文件
    print("\n请选择要处理的文件:")
    print("1. DPO Rollout (pubmed_test_dporollout.jsonl)")
    print("2. Tulu Rollout (pubmed_test_tulurollout.jsonl)")
    print("3. 全部处理")
    
    choice = input("\n请输入选择 (1/2/3): ").strip()
    
    if choice == "1":
        print("\n🔍 开始处理 DPO Rollout...")
        await evaluator.process_file(
            input_file=config["dporollout_input"],
            output_file=config["dporollout_output"],
            rubrics_map=rubrics_map,
            concurrency=config["concurrency"],
            checkpoint_file=config["dporollout_output"]
        )
    elif choice == "2":
        print("\n🔍 开始处理 Tulu Rollout...")
        await evaluator.process_file(
            input_file=config["tulurollout_input"],
            output_file=config["tulurollout_output"],
            rubrics_map=rubrics_map,
            concurrency=config["concurrency"],
            checkpoint_file=config["tulurollout_output"]
        )
    elif choice == "3":
        print("\n🔍 开始处理 DPO Rollout...")
        await evaluator.process_file(
            input_file=config["dporollout_input"],
            output_file=config["dporollout_output"],
            rubrics_map=rubrics_map,
            concurrency=config["concurrency"],
            checkpoint_file=config["dporollout_output"]
        )
        
        print("\n🔍 开始处理 Tulu Rollout...")
        await evaluator.process_file(
            input_file=config["tulurollout_input"],
            output_file=config["tulurollout_output"],
            rubrics_map=rubrics_map,
            concurrency=config["concurrency"],
            checkpoint_file=config["tulurollout_output"]
        )
    else:
        print("❌ 无效选择")
        sys.exit(1)
    
    print("\n✅ 评估完成!")
    print(f"📁 DPO结果保存在: {config['dporollout_output']}")
    print(f"📁 Tulu结果保存在: {config['tulurollout_output']}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏸️  程序被用户中断")
        print("💡 提示: 重新运行程序可以继续处理未完成的条目")
    except Exception as e:
        print(f"\n❌ 程序错误: {e}")
        sys.exit(1)
