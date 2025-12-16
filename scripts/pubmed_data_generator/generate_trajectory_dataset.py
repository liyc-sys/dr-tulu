"""
PubMed 轨迹数据生成器 - 主脚本
生成：问题 + GPT-5 工具调用轨迹 + 评判 rubrics

流程：
1. 生成适合 pubmed_search 的问题
2. 调用 GPT-5 连接 MCP 工具，生成工具调用轨迹
3. 根据轨迹结果生成 content rubrics
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import OUTPUT_DIR
from topic_generator import call_llm, extract_json
from trajectory_generator import (
    GPT5TrajectoryGenerator,
    Trajectory,
    generate_content_rubrics_from_trajectory
)


# 固定的工具调用 rubrics（4条，所有数据一样）
FIXED_TOOL_RUBRICS = [
    {
        "category": "tool_use",
        "title": "正确调用 pubmed_search",
        "description": "模型必须调用 pubmed_search 工具进行文献检索，参数格式正确",
        "weight": 3
    },
    {
        "category": "tool_use",
        "title": "引用正确的 PMID",
        "description": "输出必须包含正确的 PMID，与工具返回结果对齐",
        "weight": 3
    },
    {
        "category": "tool_use",
        "title": "提供年份和期刊信息",
        "description": "每篇被引用文献必须给出发表年份(year)和期刊名称(venue)",
        "weight": 2
    },
    {
        "category": "tool_use",
        "title": "摘要证据句对齐",
        "description": "每篇被引用文献必须给出至少 1 句摘要证据句，可从 abstract 中摘写或紧贴改写",
        "weight": 3
    }
]


# 问题生成 Prompt
QUESTION_GENERATION_PROMPT = """你是一个医学研究问题生成专家。请生成 {num_questions} 个适合使用 PubMed 医学文献搜索来回答的研究问题。

**要求**:
1. 问题必须需要查阅 PubMed 论文才能准确回答
2. 问题涉及具体的医学/生物医学研究（疾病、药物、机制、治疗方法等）
3. 问题需要引用具体论文的 PMID 和研究数据
4. 涵盖不同类型：疗效比较、机制研究、流行病学、预后分析、综述
5. 语言：{language}
6. 难度适中，需要查阅 2-5 篇论文才能完整回答

**主题覆盖**（每类至少 1-2 个）：
- 癌症治疗（靶向治疗、免疫治疗）
- 心血管疾病
- 神经系统疾病
- 感染性疾病
- 罕见病/遗传病
- 药物研发/临床试验

**输出 JSON 格式**:
```json
{{
  "questions": [
    {{
      "question": "问题内容",
      "topic": "主题分类",
      "question_type": "疗效比较/机制研究/流行病学/预后/综述",
      "expected_search_terms": ["可能的 PubMed 搜索词"]
    }}
  ]
}}
```

只输出 JSON，不要其他内容。
"""


@dataclass
class TrajectoryDataSample:
    """完整的轨迹数据样本"""
    sample_id: str
    question: str
    topic: str
    question_type: str
    trajectory: Dict[str, Any]  # GPT-5 生成的轨迹
    tool_rubrics: List[Dict]  # 固定的工具调用 rubrics
    content_rubrics: List[Dict]  # 动态生成的内容 rubrics
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "topic": self.topic,
            "question_type": self.question_type,
            "trajectory": self.trajectory,
            "tool_rubrics": self.tool_rubrics,
            "content_rubrics": self.content_rubrics,
            "all_rubrics": self.tool_rubrics + self.content_rubrics,
            "metadata": self.metadata
        }


class TrajectoryDatasetGenerator:
    """轨迹数据集生成器"""
    
    def __init__(
        self,
        model: str = "openai/gpt-4o",
        num_questions: int = 10,
        language: str = "zh"
    ):
        self.model = model
        self.num_questions = num_questions
        self.language = language
        self.trajectory_generator = GPT5TrajectoryGenerator(model=model)
        self.samples: List[TrajectoryDataSample] = []
    
    async def generate_questions(self) -> List[Dict]:
        """Step 1: 生成适合 pubmed 搜索的问题"""
        print("\n" + "=" * 60)
        print("Step 1: 生成问题")
        print("=" * 60)
        
        prompt = QUESTION_GENERATION_PROMPT.format(
            num_questions=self.num_questions,
            language="中文" if self.language == "zh" else "English"
        )
        
        try:
            response = await call_llm(prompt, temperature=0.7, model=self.model)
            result = extract_json(response)
            questions = result.get("questions", [])
            print(f"✓ 生成了 {len(questions)} 个问题")
            return questions
        except Exception as e:
            print(f"✗ 生成问题失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def generate_trajectory_for_question(
        self,
        question_data: Dict,
        sample_index: int
    ) -> Optional[TrajectoryDataSample]:
        """Step 2 & 3: 为单个问题生成轨迹和 rubrics"""
        question = question_data["question"]
        
        print(f"\n[{sample_index}] 问题: {question[:60]}...")
        
        # Step 2: 生成轨迹
        print("  正在生成工具调用轨迹...")
        try:
            trajectory = await self.trajectory_generator.generate_trajectory(question)
            print(f"  ✓ 轨迹生成完成: {trajectory.total_tool_calls} 次工具调用")
        except Exception as e:
            print(f"  ✗ 轨迹生成失败: {e}")
            return None
        
        # Step 3: 根据轨迹生成 content rubrics
        print("  正在生成内容 rubrics...")
        try:
            content_rubrics = await generate_content_rubrics_from_trajectory(
                question, trajectory, model=self.model
            )
            print(f"  ✓ 生成了 {len(content_rubrics)} 条内容 rubrics")
        except Exception as e:
            print(f"  ⚠ 内容 rubrics 生成失败: {e}")
            content_rubrics = []
        
        return TrajectoryDataSample(
            sample_id=f"pubmed_traj_{sample_index:05d}",
            question=question,
            topic=question_data.get("topic", ""),
            question_type=question_data.get("question_type", ""),
            trajectory=trajectory.to_dict(),
            tool_rubrics=FIXED_TOOL_RUBRICS.copy(),
            content_rubrics=content_rubrics,
            metadata={
                "expected_search_terms": question_data.get("expected_search_terms", []),
                "tools_used": trajectory.tools_used,
                "total_tool_calls": trajectory.total_tool_calls,
                "generation_time": datetime.now().isoformat()
            }
        )
    
    async def generate_dataset(self) -> List[TrajectoryDataSample]:
        """生成完整数据集"""
        print("\n" + "=" * 60)
        print("PubMed 轨迹数据生成器")
        print("=" * 60)
        print(f"模型: {self.model}")
        print(f"计划生成: {self.num_questions} 个问题")
        
        # Step 1: 生成问题
        questions = await self.generate_questions()
        
        if not questions:
            print("✗ 没有生成任何问题")
            return []
        
        # Step 2 & 3: 为每个问题生成轨迹和 rubrics
        print("\n" + "=" * 60)
        print("Step 2 & 3: 生成轨迹和 rubrics")
        print("=" * 60)
        
        samples = []
        for i, q_data in enumerate(questions, 1):
            sample = await self.generate_trajectory_for_question(q_data, i)
            if sample:
                samples.append(sample)
            
            # 避免 API 限流
            await asyncio.sleep(2)
        
        self.samples = samples
        print(f"\n✓ 完成！共生成 {len(samples)} 个样本")
        return samples
    
    def save_dataset(self, output_dir: str = OUTPUT_DIR):
        """保存数据集"""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存 JSONL
        jsonl_path = os.path.join(output_dir, f"pubmed_trajectory_{timestamp}.jsonl")
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for sample in self.samples:
                f.write(json.dumps(sample.to_dict(), ensure_ascii=False) + '\n')
        print(f"✓ 保存 JSONL: {jsonl_path}")
        
        # 保存 CSV（兼容现有训练格式）
        csv_path = os.path.join(output_dir, f"pubmed_trajectory_{timestamp}.csv")
        self._save_as_csv(csv_path)
        print(f"✓ 保存 CSV: {csv_path}")
        
        # 保存统计
        stats = self._generate_stats()
        stats_path = os.path.join(output_dir, f"trajectory_stats_{timestamp}.json")
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存统计: {stats_path}")
        
        return jsonl_path
    
    def _save_as_csv(self, csv_path: str):
        """保存为 CSV 格式"""
        import csv
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'source', 'question_type', 'messages', 'ground_truth', 'dataset'
            ])
            writer.writeheader()
            
            for sample in self.samples:
                messages = [{"content": sample.question, "role": "user"}]
                
                ground_truth = {
                    "query": sample.question,
                    "rubrics": sample.tool_rubrics + sample.content_rubrics,
                    "tool_rubrics": sample.tool_rubrics,
                    "content_rubrics": sample.content_rubrics,
                    "trajectory": sample.trajectory,
                    "expected_answer": sample.trajectory.get("final_answer", "")
                }
                
                writer.writerow({
                    'source': 'pubmed_trajectory_generator',
                    'question_type': 'pubmed_search',
                    'messages': json.dumps(messages, ensure_ascii=False),
                    'ground_truth': json.dumps(ground_truth, ensure_ascii=False),
                    'dataset': 'pubmed_trajectory'
                })
    
    def _generate_stats(self) -> Dict:
        """生成统计信息"""
        if not self.samples:
            return {}
        
        topics = {}
        question_types = {}
        tool_calls_counts = []
        content_rubrics_counts = []
        
        for sample in self.samples:
            topics[sample.topic] = topics.get(sample.topic, 0) + 1
            question_types[sample.question_type] = question_types.get(sample.question_type, 0) + 1
            tool_calls_counts.append(sample.metadata.get("total_tool_calls", 0))
            content_rubrics_counts.append(len(sample.content_rubrics))
        
        return {
            "total_samples": len(self.samples),
            "topics": topics,
            "question_types": question_types,
            "avg_tool_calls": sum(tool_calls_counts) / len(tool_calls_counts),
            "avg_content_rubrics": sum(content_rubrics_counts) / len(content_rubrics_counts),
            "generation_time": datetime.now().isoformat()
        }


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="生成 PubMed 轨迹数据集")
    parser.add_argument("--model", type=str, default="openai/gpt-4o", help="LLM 模型")
    parser.add_argument("--num-questions", type=int, default=5, help="问题数量")
    parser.add_argument("--language", type=str, default="zh", choices=["zh", "en"], help="语言")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="输出目录")
    
    args = parser.parse_args()
    
    generator = TrajectoryDatasetGenerator(
        model=args.model,
        num_questions=args.num_questions,
        language=args.language
    )
    
    await generator.generate_dataset()
    generator.save_dataset(args.output)
    
    print("\n" + "=" * 60)
    print("数据生成完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

