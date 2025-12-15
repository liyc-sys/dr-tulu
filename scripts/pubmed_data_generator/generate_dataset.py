"""
PubMed 训练数据生成器 - 主脚本
生成完整的 pubmed_search 工具训练/评测数据集
"""
import asyncio
import json
import os
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from config import (
    OUTPUT_DIR, 
    NUM_TOPIC_CLUSTERS, 
    QUERIES_PER_CLUSTER,
    SAMPLES_PER_QUERY
)
from topic_generator import (
    generate_topic_clusters,
    generate_query_templates,
    call_llm,
    extract_json
)
from pubmed_client import (
    PubMedMCPClient,
    EvidenceSnapshot,
    sample_evidence_for_query,
    instantiate_query_template
)
from question_generator import (
    generate_question_from_evidence,
    generate_pagination_question,
    QuestionSample
)
from rubric_generator import (
    generate_training_sample,
    TrainingSample
)


class PubMedDatasetGenerator:
    """PubMed 训练数据集生成器"""
    
    def __init__(
        self,
        num_clusters: int = NUM_TOPIC_CLUSTERS,
        queries_per_cluster: int = QUERIES_PER_CLUSTER,
        samples_per_query: int = SAMPLES_PER_QUERY,
        pagination_ratio: float = 0.2,  # 20% 样本需要分页
        language_ratio: Dict[str, float] = None  # 语言分布
    ):
        self.num_clusters = num_clusters
        self.queries_per_cluster = queries_per_cluster
        self.samples_per_query = samples_per_query
        self.pagination_ratio = pagination_ratio
        self.language_ratio = language_ratio or {"zh": 0.7, "en": 0.3}
        
        self.pubmed_client = PubMedMCPClient()
        self.samples: List[TrainingSample] = []
        self.evidence_cache: Dict[str, EvidenceSnapshot] = {}
        
    def _choose_language(self) -> str:
        """根据比例随机选择语言"""
        r = random.random()
        cumulative = 0
        for lang, ratio in self.language_ratio.items():
            cumulative += ratio
            if r < cumulative:
                return lang
        return "zh"
    
    async def generate_topic_clusters_and_queries(self) -> Dict[str, Any]:
        """Step 1: 生成主题簇和查询模板"""
        print("=" * 60)
        print("Step 1: 生成主题簇和查询模板")
        print("=" * 60)
        
        topic_clusters = await generate_topic_clusters(self.num_clusters)
        print(f"✓ 生成了 {len(topic_clusters)} 个主题簇")
        
        result = {"topic_clusters": []}
        
        for i, cluster in enumerate(topic_clusters):
            print(f"\n[{i+1}/{len(topic_clusters)}] 主题: {cluster['name']}")
            queries = await generate_query_templates(cluster, self.queries_per_cluster)
            cluster["query_templates"] = queries
            result["topic_clusters"].append(cluster)
            print(f"  ✓ 生成了 {len(queries)} 个查询模板")
        
        return result
    
    async def sample_evidence_for_all_queries(
        self, 
        topic_clusters: List[Dict]
    ) -> Dict[str, EvidenceSnapshot]:
        """Step 2: 为所有查询采样证据库"""
        print("\n" + "=" * 60)
        print("Step 2: 采样证据库")
        print("=" * 60)
        
        evidence_cache = {}
        total_queries = sum(len(c.get("query_templates", [])) for c in topic_clusters)
        processed = 0
        
        for cluster in topic_clusters:
            cluster_name = cluster["name"]
            print(f"\n主题簇: {cluster_name}")
            
            for query_template in cluster.get("query_templates", []):
                processed += 1
                template = query_template["template"]
                
                # 实例化查询模板
                query = await instantiate_query_template(template)
                
                print(f"  [{processed}/{total_queries}] 查询: {query[:50]}...")
                
                try:
                    # 采样证据
                    evidence = await self.pubmed_client.search(query, limit=5, offset=0)
                    
                    if evidence and evidence.papers:
                        evidence_cache[query] = evidence
                        print(f"    ✓ 找到 {len(evidence.papers)} 篇论文")
                    else:
                        print(f"    ⚠ 未找到结果")
                        
                except Exception as e:
                    print(f"    ✗ 搜索失败: {e}")
                
                # 避免 API 限流
                await asyncio.sleep(0.5)
        
        print(f"\n✓ 完成证据采样，共 {len(evidence_cache)} 个有效查询")
        self.evidence_cache = evidence_cache
        return evidence_cache
    
    async def generate_samples_for_evidence(
        self,
        query: str,
        evidence: EvidenceSnapshot,
        sample_index: int
    ) -> Optional[TrainingSample]:
        """Step 3 & 4: 为单个证据生成问题和 rubric"""
        
        language = self._choose_language()
        is_pagination = random.random() < self.pagination_ratio
        
        # 生成问题
        question = await generate_question_from_evidence(
            evidence=evidence,
            language=language,
            question_id=f"pubmed_{sample_index:05d}"
        )
        
        if not question:
            return None
        
        # 如果是分页任务，获取更多页
        num_pages = 1
        if is_pagination and evidence.total > 5:
            try:
                # 获取第二页
                page2 = await self.pubmed_client.search(
                    query, limit=5, offset=5
                )
                if page2 and page2.papers:
                    # 合并论文列表
                    all_papers = evidence.papers + page2.papers
                    evidence = EvidenceSnapshot(
                        query=evidence.query,
                        limit=10,
                        offset=0,
                        papers=all_papers,
                        total=evidence.total,
                        snapshot_time=evidence.snapshot_time
                    )
                    num_pages = 2
                    
                    # 重新生成问题以包含更多论文
                    question = await generate_pagination_question(
                        evidence_pages=[evidence, page2],
                        language=language,
                        question_id=f"pubmed_pag_{sample_index:05d}"
                    )
                    
                    if not question:
                        # fallback 到普通问题
                        question = await generate_question_from_evidence(
                            evidence=evidence,
                            language=language,
                            question_id=f"pubmed_{sample_index:05d}"
                        )
            except Exception as e:
                print(f"    分页失败: {e}")
                is_pagination = False
        
        if not question:
            return None
        
        # 生成完整训练样本
        sample = generate_training_sample(
            question=question,
            evidence=evidence,
            is_pagination_task=is_pagination and num_pages > 1,
            num_pages=num_pages,
            use_cache=True
        )
        
        return sample
    
    async def generate_dataset(self) -> List[TrainingSample]:
        """生成完整数据集"""
        print("\n" + "=" * 60)
        print("PubMed 训练数据生成器")
        print("=" * 60)
        print(f"配置: {self.num_clusters} 主题簇 × {self.queries_per_cluster} 查询/簇")
        print(f"分页任务比例: {self.pagination_ratio * 100}%")
        print(f"语言分布: {self.language_ratio}")
        
        # Step 1: 生成主题簇和查询
        topic_data = await self.generate_topic_clusters_and_queries()
        
        # Step 2: 采样证据库
        evidence_cache = await self.sample_evidence_for_all_queries(
            topic_data["topic_clusters"]
        )
        
        # Step 3 & 4: 生成问题和 rubric
        print("\n" + "=" * 60)
        print("Step 3 & 4: 生成问题和评分 Rubrics")
        print("=" * 60)
        
        samples = []
        sample_index = 0
        
        for query, evidence in evidence_cache.items():
            for _ in range(self.samples_per_query):
                sample_index += 1
                print(f"\n[{sample_index}] 生成样本...")
                
                sample = await self.generate_samples_for_evidence(
                    query=query,
                    evidence=evidence,
                    sample_index=sample_index
                )
                
                if sample:
                    samples.append(sample)
                    print(f"  ✓ 问题: {sample.user_question[:50]}...")
                    print(f"    类型: {sample.metadata.get('question_type')}")
                    print(f"    PMID: {sample.evidence_pmids}")
                else:
                    print(f"  ⚠ 生成失败")
                
                await asyncio.sleep(0.5)
        
        self.samples = samples
        print(f"\n✓ 完成！共生成 {len(samples)} 个训练样本")
        
        return samples
    
    def save_dataset(self, output_dir: str = OUTPUT_DIR):
        """保存数据集"""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存完整数据集 (JSONL 格式)
        jsonl_path = os.path.join(output_dir, f"pubmed_train_{timestamp}.jsonl")
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for sample in self.samples:
                f.write(json.dumps(sample.to_dict(), ensure_ascii=False) + '\n')
        print(f"✓ 保存 JSONL: {jsonl_path}")
        
        # 保存为 CSV 格式（兼容现有训练流程）
        csv_path = os.path.join(output_dir, f"pubmed_train_{timestamp}.csv")
        self._save_as_csv(csv_path)
        print(f"✓ 保存 CSV: {csv_path}")
        
        # 保存证据库快照（用于评测稳定性）
        cache_path = os.path.join(output_dir, f"evidence_cache_{timestamp}.json")
        cache_data = {
            query: snapshot.to_dict() 
            for query, snapshot in self.evidence_cache.items()
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存证据缓存: {cache_path}")
        
        # 保存统计信息
        stats = self._generate_stats()
        stats_path = os.path.join(output_dir, f"stats_{timestamp}.json")
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存统计: {stats_path}")
        
        return jsonl_path
    
    def _save_as_csv(self, csv_path: str):
        """保存为 CSV 格式（兼容现有训练流程）"""
        import csv
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'source', 'question_type', 'messages', 'ground_truth', 'dataset'
            ])
            writer.writeheader()
            
            for sample in self.samples:
                # 构造 messages
                messages = [{"content": sample.user_question, "role": "user"}]
                
                # 构造 ground_truth (rubric 格式)
                rubrics = []
                for item in sample.answer_rubric.rubric_items:
                    rubrics.append({
                        "title": item.title,
                        "description": item.description,
                        "weight": item.weight
                    })
                
                ground_truth = {
                    "query": sample.user_question,
                    "rubrics": rubrics,
                    "expected_tools": [t.to_dict() for t in sample.expected_tools],
                    "evidence_pmids": sample.evidence_pmids,
                    "stability_strategy": sample.answer_rubric.stability_strategy.to_dict()
                }
                
                writer.writerow({
                    'source': 'pubmed_data_generator',
                    'question_type': 'pubmed_search',
                    'messages': json.dumps(messages, ensure_ascii=False),
                    'ground_truth': json.dumps(ground_truth, ensure_ascii=False),
                    'dataset': 'pubmed_rubric'
                })
    
    def _generate_stats(self) -> Dict:
        """生成数据集统计信息"""
        if not self.samples:
            return {}
        
        question_types = {}
        languages = {}
        pagination_count = 0
        pmids_per_sample = []
        
        for sample in self.samples:
            # 问题类型统计
            qt = sample.metadata.get("question_type", "unknown")
            question_types[qt] = question_types.get(qt, 0) + 1
            
            # 语言统计
            lang = sample.metadata.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1
            
            # 分页统计
            if sample.metadata.get("is_pagination_task"):
                pagination_count += 1
            
            # PMID 数量
            pmids_per_sample.append(len(sample.evidence_pmids))
        
        return {
            "total_samples": len(self.samples),
            "question_types": question_types,
            "languages": languages,
            "pagination_samples": pagination_count,
            "pagination_ratio": pagination_count / len(self.samples) if self.samples else 0,
            "avg_pmids_per_sample": sum(pmids_per_sample) / len(pmids_per_sample) if pmids_per_sample else 0,
            "unique_queries": len(self.evidence_cache),
            "generation_time": datetime.now().isoformat()
        }


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="生成 PubMed 训练数据集")
    parser.add_argument("--clusters", type=int, default=5, help="主题簇数量")
    parser.add_argument("--queries", type=int, default=3, help="每个簇的查询数量")
    parser.add_argument("--samples", type=int, default=1, help="每个查询的样本数量")
    parser.add_argument("--pagination-ratio", type=float, default=0.2, help="分页任务比例")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="输出目录")
    
    args = parser.parse_args()
    
    generator = PubMedDatasetGenerator(
        num_clusters=args.clusters,
        queries_per_cluster=args.queries,
        samples_per_query=args.samples,
        pagination_ratio=args.pagination_ratio
    )
    
    await generator.generate_dataset()
    generator.save_dataset(args.output)
    
    print("\n" + "=" * 60)
    print("数据生成完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

