#!/usr/bin/env python3
"""
分析评估结果，生成统计报告
"""

import json
import os
from pathlib import Path
from typing import Dict, List
import statistics

class ResultAnalyzer:
    def __init__(self, result_file: str):
        self.result_file = result_file
        self.results = self.load_results()
    
    def load_results(self) -> List[Dict]:
        """加载评估结果"""
        results = []
        if Path(self.result_file).exists():
            with open(self.result_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        results.append(data)
                    except json.JSONDecodeError:
                        continue
        return results
    
    def generate_statistics(self) -> Dict:
        """生成统计信息"""
        if not self.results:
            return {"error": "没有结果数据"}
        
        successful = [r for r in self.results if r.get('success', False)]
        failed = [r for r in self.results if not r.get('success', False)]
        
        stats = {
            "total_count": len(self.results),
            "successful_count": len(successful),
            "failed_count": len(failed),
            "success_rate": len(successful) / len(self.results) * 100 if self.results else 0,
        }
        
        if successful:
            total_scores = [r.get('total_score', 0) for r in successful]
            max_scores = [r.get('max_score', 1) for r in successful]
            
            stats.update({
                "score_stats": {
                    "min": min(total_scores),
                    "max": max(total_scores),
                    "mean": statistics.mean(total_scores),
                    "median": statistics.median(total_scores),
                    "stdev": statistics.stdev(total_scores) if len(total_scores) > 1 else 0,
                },
                "max_score_stats": {
                    "min": min(max_scores),
                    "max": max(max_scores),
                    "mean": statistics.mean(max_scores),
                },
                "average_score_percentage": statistics.mean([
                    s/m * 100 if m > 0 else 0 
                    for s, m in zip(total_scores, max_scores)
                ])
            })
            
            # Rubric级别统计
            rubric_stats = {}
            for result in successful:
                rubric_scores = result.get('rubric_scores', [])
                for rubric in rubric_scores:
                    rubric_id = rubric.get('rubric_id', 'unknown')
                    if rubric_id not in rubric_stats:
                        rubric_stats[rubric_id] = {
                            "title": rubric.get('title', ''),
                            "category": rubric.get('category', ''),
                            "scores": [],
                            "max_scores": []
                        }
                    rubric_stats[rubric_id]["scores"].append(rubric.get('score', 0))
                    rubric_stats[rubric_id]["max_scores"].append(rubric.get('max_score', 1))
            
            # 计算每个rubric的统计
            for rubric_id, data in rubric_stats.items():
                scores = data["scores"]
                max_scores = data["max_scores"]
                data["count"] = len(scores)
                data["avg_score"] = statistics.mean(scores)
                data["avg_max_score"] = statistics.mean(max_scores)
                data["success_rate"] = statistics.mean([
                    s/m * 100 if m > 0 else 0 
                    for s, m in zip(scores, max_scores)
                ])
            
            stats["rubric_stats"] = rubric_stats
        
        return stats
    
    def generate_report(self) -> str:
        """生成文本报告"""
        stats = self.generate_statistics()
        
        if "error" in stats:
            return f"❌ 错误: {stats['error']}"
        
        report = []
        report.append("="*60)
        report.append("📊 评估结果统计报告")
        report.append("="*60)
        report.append(f"📁 文件: {self.result_file}")
        report.append(f"📈 总条目数: {stats['total_count']}")
        report.append(f"✅ 成功评估: {stats['successful_count']}")
        report.append(f"❌ 评估失败: {stats['failed_count']}")
        report.append(f"📊 成功率: {stats['success_rate']:.1f}%")
        
        if 'score_stats' in stats:
            score_stats = stats['score_stats']
            report.append("\n📊 分数统计:")
            report.append(f"  最低分: {score_stats['min']:.1f}")
            report.append(f"  最高分: {score_stats['max']:.1f}")
            report.append(f"  平均分: {score_stats['mean']:.1f}")
            report.append(f"  中位数: {score_stats['median']:.1f}")
            report.append(f"  标准差: {score_stats['stdev']:.1f}")
            report.append(f"  平均得分率: {stats['average_score_percentage']:.1f}%")
        
        if 'rubric_stats' in stats:
            report.append("\n📋 Rubric级别统计:")
            for rubric_id, rubric_data in sorted(stats['rubric_stats'].items()):
                report.append(f"\n  [{rubric_id}] {rubric_data['title']} ({rubric_data['category']})")
                report.append(f"    评估次数: {rubric_data['count']}")
                report.append(f"    平均得分: {rubric_data['avg_score']:.1f}/{rubric_data['avg_max_score']:.1f}")
                report.append(f"    平均得分率: {rubric_data['success_rate']:.1f}%")
        
        if stats['failed_count'] > 0:
            report.append(f"\n❌ 失败条目:")
            failed = [r for r in self.results if not r.get('success', False)]
            for result in failed[:10]:  # 只显示前10个
                sample_id = result.get('sample_id', 'unknown')
                error = result.get('error', 'unknown error')
                report.append(f"  {sample_id}: {error}")
            
            if len(failed) > 10:
                report.append(f"  ... 还有 {len(failed)-10} 个失败条目")
        
        report.append("\n" + "="*60)
        
        return "\n".join(report)
    
    def save_report(self, output_file: str):
        """保存报告到文件"""
        report = self.generate_report()
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"📄 报告已保存到: {output_file}")

def main():
    # 分析DPO结果
    print("🔍 分析 DPO Rollout 评估结果...")
    dporollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    
    if Path(dporollout_file).exists():
        dpo_analyzer = ResultAnalyzer(dporollout_file)
        dpo_report = dpo_analyzer.generate_report()
        print(dpo_report)
        
        # 保存报告
        dpo_analyzer.save_report('/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_report.txt')
    else:
        print(f"❌ DPO结果文件不存在: {dporollout_file}")
    
    print("\n")
    
    # 分析Tulu结果
    print("🔍 分析 Tulu Rollout 评估结果...")
    tulurollout_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    
    if Path(tulurollout_file).exists():
        tulu_analyzer = ResultAnalyzer(tulurollout_file)
        tulu_report = tulu_analyzer.generate_report()
        print(tulu_report)
        
        # 保存报告
        tulu_analyzer.save_report('/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_report.txt')
    else:
        print(f"❌ Tulu结果文件不存在: {tulurollout_file}")
    
    # 对比分析
    if Path(dporollout_file).exists() and Path(tulurollout_file).exists():
        print("\n" + "="*60)
        print("📊 对比分析")
        print("="*60)
        
        dpo_stats = dpo_analyzer.generate_statistics()
        tulu_stats = tulu_analyzer.generate_statistics()
        
        if 'score_stats' in dpo_stats and 'score_stats' in tulu_stats:
            dpo_avg = dpo_stats['score_stats']['mean']
            tulu_avg = tulu_stats['score_stats']['mean']
            dpo_pct = dpo_stats['average_score_percentage']
            tulu_pct = tulu_stats['average_score_percentage']
            
            print(f"DPO平均分: {dpo_avg:.1f} ({dpo_pct:.1f}%)")
            print(f"Tulu平均分: {tulu_avg:.1f} ({tulu_pct:.1f}%)")
            
            if dpo_avg > tulu_avg:
                diff = ((dpo_avg - tulu_avg) / tulu_avg) * 100
                print(f"🏆 DPO表现更好，高出 {diff:.1f}%")
            elif tulu_avg > dpo_avg:
                diff = ((tulu_avg - dpo_avg) / dpo_avg) * 100
                print(f"🏆 Tulu表现更好，高出 {diff:.1f}%")
            else:
                print(f"🤝 两者表现相当")

if __name__ == "__main__":
    main()
