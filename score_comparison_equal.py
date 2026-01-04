import json
from pathlib import Path
from typing import Dict, List
import statistics

class ScoreComparisonEqual:
    def __init__(self, dpo_file: str, tulu_file: str):
        self.dpo_file = dpo_file
        self.tulu_file = tulu_file
        
    def load_results(self, file_path: str) -> List[Dict]:
        """加载评估结果"""
        results = []
        if Path(file_path).exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get('success', False):
                            results.append(data)
                    except json.JSONDecodeError:
                        continue
        return results
    
    def calculate_equal_weight_score(self, result: Dict) -> float:
        """计算等权重总分（每个rubric的weight都视为1）"""
        rubric_scores = result.get('rubric_scores', [])
        total_score = 0.0
        
        for rubric in rubric_scores:
            weight = rubric.get('weight', 0)
            score = rubric.get('score', 0)
            
            if weight > 0:
                # 将得分归一化到weight=1的情况
                normalized_score = (score / weight) * 1
                total_score += normalized_score
            else:
                total_score += score
                
        return total_score
    
    def calculate_max_possible_score(self, result: Dict) -> int:
        """计算可能的最高分（rubric数量）"""
        rubric_scores = result.get('rubric_scores', [])
        return len(rubric_scores)
    
    def calculate_total_scores(self, results: List[Dict]) -> Dict:
        """计算总分（所有样本的总得分和总可能分）"""
        if not results:
            return {}
        
        actual_total = sum(self.calculate_equal_weight_score(r) for r in results)
        max_possible_total = sum(self.calculate_max_possible_score(r) for r in results)
        
        return {
            'actual_total': actual_total,
            'max_possible_total': max_possible_total,
            'achievement_rate': (actual_total / max_possible_total * 100) if max_possible_total > 0 else 0
        }

    def calculate_statistics(self, results: List[Dict]) -> Dict:
        """计算统计数据"""
        if not results:
            return {}
        
        # 使用等权重重新计算得分
        scores = [self.calculate_equal_weight_score(r) for r in results]
        max_scores = [self.calculate_max_possible_score(r) for r in results]
        
        if not scores:
            return {}
        
        return {
            'count': len(scores),
            'total': sum(scores),
            'mean': statistics.mean(scores),
            'median': statistics.median(scores),
            'stdev': statistics.stdev(scores) if len(scores) > 1 else 0,
            'min': min(scores),
            'max': max(scores),
            'max_possible': max(max_scores) if max_scores else 0
        }
    
    def generate_comparison_report(self) -> str:
        """生成对比报告"""
        # 加载结果
        dpo_results = self.load_results(self.dpo_file)
        tulu_results = self.load_results(self.tulu_file)
        
        # 计算统计数据
        dpo_stats = self.calculate_statistics(dpo_results)
        tulu_stats = self.calculate_statistics(tulu_results)
        
        # 计算总分
        dpo_total_scores = self.calculate_total_scores(dpo_results)
        tulu_total_scores = self.calculate_total_scores(tulu_results)
        
        # 生成报告
        report = []
        report.append("=" * 70)
        report.append("📊 DPO vs Tulu 评估结果对比报告 (等权重模式)")
        report.append("=" * 70)
        
        # 基本信息
        report.append(f"\n📁 文件信息:")
        report.append(f"   DPO结果: {self.dpo_file}")
        report.append(f"   Tulu结果: {self.tulu_file}")
        
        # 数据量统计
        report.append(f"\n📈 评估数量:")
        report.append(f"   DPO: {len(dpo_results)} 个成功评估")
        report.append(f"   Tulu: {len(tulu_results)} 个成功评估")
        
        if dpo_stats and tulu_stats and dpo_total_scores and tulu_total_scores:
            # 对比统计
            report.append(f"\n🎯 得分统计 (等权重模式):")
            report.append(f"   {'指标':<15} {'DPO':<15} {'Tulu':<15} {'差异':<15}")
            report.append(f"   {'-'*60}")
            
            # 总分信息
            report.append(f"\n📊 总分统计:")
            report.append(f"   DPO实际得分: {dpo_total_scores['actual_total']:.1f} / {dpo_total_scores['max_possible_total']:.0f}")
            report.append(f"   Tulu实际得分: {tulu_total_scores['actual_total']:.1f} / {tulu_total_scores['max_possible_total']:.0f}")
            report.append(f"   DPO达成率: {dpo_total_scores['achievement_rate']:.1f}%")
            report.append(f"   Tulu达成率: {tulu_total_scores['achievement_rate']:.1f}%")
            
            total_diff = dpo_total_scores['actual_total'] - tulu_total_scores['actual_total']
            total_winner = "DPO" if total_diff > 0 else "Tulu" if total_diff < 0 else "平手"
            report.append(f"   总分差异: {total_diff:+.1f} ({total_winner})")
            
            # 平均分
            dpo_mean = dpo_stats['mean']
            tulu_mean = tulu_stats['mean']
            diff = dpo_mean - tulu_mean
            winner = "DPO" if diff > 0 else "Tulu" if diff < 0 else "平手"
            report.append(f"   {'平均分':<15} {dpo_mean:<15.4f} {tulu_mean:<15.4f} {diff:+.4f} ({winner})")
            
            # 中位数
            dpo_median = dpo_stats['median']
            tulu_median = tulu_stats['median']
            diff_median = dpo_median - tulu_median
            winner_median = "DPO" if diff_median > 0 else "Tulu" if diff_median < 0 else "平手"
            report.append(f"   {'中位数':<15} {dpo_median:<15.4f} {tulu_median:<15.4f} {diff_median:+.4f} ({winner_median})")
            
            # 总分
            dpo_total = dpo_stats['total']
            tulu_total = tulu_stats['total']
            diff_total = dpo_total - tulu_total
            winner_total = "DPO" if diff_total > 0 else "Tulu" if diff_total < 0 else "平手"
            report.append(f"   {'总分':<15} {dpo_total:<15.2f} {tulu_total:<15.2f} {diff_total:+.2f} ({winner_total})")
            
            # 标准差
            report.append(f"   {'标准差':<15} {dpo_stats['stdev']:<15.4f} {tulu_stats['stdev']:<15.4f} {'DPO较稳定' if dpo_stats['stdev'] < tulu_stats['stdev'] else 'Tulu较稳定' if tulu_stats['stdev'] < dpo_stats['stdev'] else '稳定性相似'}")
            
            # 范围
            report.append(f"   {'得分范围':<15} [{dpo_stats['min']:.3f}, {dpo_stats['max']:.3f}]     [{tulu_stats['min']:.3f}, {tulu_stats['max']:.3f}]")
            
            # 最高可能分数
            report.append(f"   {'最高可能分':<15} {dpo_stats['max_possible']:.0f}              {tulu_stats['max_possible']:.0f}")
            
            # 性能对比
            report.append(f"\n🏆 性能对比:")
            improvement = ((dpo_mean - tulu_mean) / tulu_mean) * 100 if tulu_mean > 0 else 0
            if abs(diff) < 0.01:
                report.append(f"   两者表现相当，差异不显著")
            elif diff > 0:
                report.append(f"   DPO表现更好，平均高出 {abs(improvement):.1f}%")
            else:
                report.append(f"   Tulu表现更好，平均高出 {abs(improvement):.1f}%")
            
            # 分数分布
            report.append(f"\n📊 分数分布:")
            dpo_ranges = self.get_score_distribution(dpo_results)
            tulu_ranges = self.get_score_distribution(tulu_results)
            
            for range_name in sorted(dpo_ranges.keys()):
                dpo_count = dpo_ranges[range_name]
                tulu_count = tulu_ranges.get(range_name, 0)
                dpo_pct = (dpo_count / dpo_stats['count']) * 100
                tulu_pct = (tulu_count / tulu_stats['count']) * 100
                report.append(f"   {range_name}: DPO {dpo_count:3d} ({dpo_pct:5.1f}%) | Tulu {tulu_count:3d} ({tulu_pct:5.1f}%)")
        
        # 最佳和最差表现
        if dpo_results and tulu_results:
            report.append(f"\n🥇 最佳表现:")
            best_dpo = max(dpo_results, key=lambda x: self.calculate_equal_weight_score(x))
            best_tulu = max(tulu_results, key=lambda x: self.calculate_equal_weight_score(x))
            report.append(f"   DPO: {best_dpo['sample_id']} - {self.calculate_equal_weight_score(best_dpo):.3f}")
            report.append(f"   Tulu: {best_tulu['sample_id']} - {self.calculate_equal_weight_score(best_tulu):.3f}")
            
            report.append(f"\n📉 最差表现:")
            worst_dpo = min(dpo_results, key=lambda x: self.calculate_equal_weight_score(x))
            worst_tulu = min(tulu_results, key=lambda x: self.calculate_equal_weight_score(x))
            report.append(f"   DPO: {worst_dpo['sample_id']} - {self.calculate_equal_weight_score(worst_dpo):.3f}")
            report.append(f"   Tulu: {worst_tulu['sample_id']} - {self.calculate_equal_weight_score(worst_tulu):.3f}")
        
        report.append("\n" + "=" * 70)
        
        return "\n".join(report)
    
    def get_score_distribution(self, results: List[Dict]) -> Dict[str, int]:
        """获取分数分布"""
        # 首先确定最大可能的分数
        max_scores = [self.calculate_max_possible_score(r) for r in results]
        max_possible = max(max_scores) if max_scores else 1
        
        # 基于最大可能分数创建分布区间
        distribution = {
            '0.0-20%': 0,
            '20-40%': 0, 
            '40-60%': 0,
            '60-80%': 0,
            '80-100%': 0
        }
        
        for result in results:
            score = self.calculate_equal_weight_score(result)
            if max_possible > 0:
                percentage = (score / max_possible) * 100
            else:
                percentage = 0
                
            if percentage < 20:
                distribution['0.0-20%'] += 1
            elif percentage < 40:
                distribution['20-40%'] += 1
            elif percentage < 60:
                distribution['40-60%'] += 1
            elif percentage < 80:
                distribution['60-80%'] += 1
            else:
                distribution['80-100%'] += 1
        
        return distribution
    
    def save_comparison_to_file(self, output_file: str):
        """保存对比报告到文件"""
        report = self.generate_comparison_report()
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"📄 对比报告已保存到: {output_file}")
    
    def print_summary(self):
        """打印简要总结"""
        dpo_results = self.load_results(self.dpo_file)
        tulu_results = self.load_results(self.tulu_file)
        
        dpo_stats = self.calculate_statistics(dpo_results)
        tulu_stats = self.calculate_statistics(tulu_results)
        
        # 计算总分
        dpo_total_scores = self.calculate_total_scores(dpo_results)
        tulu_total_scores = self.calculate_total_scores(tulu_results)
        
        print("\n" + "=" * 50)
        print("🎯 快速总结 (等权重模式)")
        print("=" * 50)
        
        if dpo_stats and tulu_stats and dpo_total_scores and tulu_total_scores:
            print(f"DPO:  {dpo_stats['count']}个评估, 平均分 {dpo_stats['mean']:.3f}")
            print(f"Tulu: {tulu_stats['count']}个评估, 平均分 {tulu_stats['mean']:.3f}")
            
            print(f"\n总分统计:")
            print(f"DPO:  {dpo_total_scores['actual_total']:.1f} / {dpo_total_scores['max_possible_total']:.0f} ({dpo_total_scores['achievement_rate']:.1f}%)")
            print(f"Tulu: {tulu_total_scores['actual_total']:.1f} / {tulu_total_scores['max_possible_total']:.0f} ({tulu_total_scores['achievement_rate']:.1f}%)")
            
            diff = dpo_stats['mean'] - tulu_stats['mean']
            total_diff = dpo_total_scores['actual_total'] - tulu_total_scores['actual_total']
            
            if abs(diff) < 0.01:
                print("结论: 两者表现相当")
            elif diff > 0:
                print(f"结论: DPO表现更好 (+{diff:.3f}, 总分+{total_diff:.1f})")
            else:
                print(f"结论: Tulu表现更好 ({diff:+.3f}, 总分{total_diff:+.1f})")
        else:
            print("无法计算统计数据，请检查评估结果文件")

def main():
    # 文件路径
    dpo_file = '/Users/liyc/Desktop/dr-tulu/交付数据/dporollout_evaluation_results.jsonl'
    tulu_file = '/Users/liyc/Desktop/dr-tulu/交付数据/tulurollout_evaluation_results.jsonl'
    output_file = '/Users/liyc/Desktop/dr-tulu/交付数据/score_comparison_equal_report.txt'
    
    # 创建对比分析器
    comparator = ScoreComparisonEqual(dpo_file, tulu_file)
    
    # 打印简要总结
    comparator.print_summary()
    
    # 生成详细报告
    print("\n正在生成详细对比报告...")
    comparator.save_comparison_to_file(output_file)
    
    # 显示报告
    print("\n" + comparator.generate_comparison_report())

if __name__ == "__main__":
    main()