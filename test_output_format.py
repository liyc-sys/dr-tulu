import json

# 模拟一个评估结果示例
example_output = {
  "sample_id": "port8000_eval_00013",
  "question": "In metastatic castration-resistant prostate cancer, how does sequencing an androgen receptor pathway inhibitor before versus after docetaxel influence subsequent treatment response and survival?",
  "final_answer_length": 3891,
  "evaluation_timestamp": "2026-01-02 15:30:45",
  "processing_duration_seconds": 12.3,
  "success": True,
  "total_score": 0.84,
  "final_score": 0.84,  # 新增的字段
  "rubric_scores": [
    {
      "title": "Correct pubmed_search usage",
      "description": "Model must call pubmed_search tool for literature search with correct parameter format",
      "weight": 0.2,
      "reasoning": "模型正确使用了pubmed_search工具，参数格式正确",
      "score": 0.2
    },
    {
      "title": "Cite correct PMIDs", 
      "description": "Output must contain correct PMIDs that align with tool return results",
      "weight": 0.2,
      "reasoning": "引用的PMID都正确，与工具返回结果一致",
      "score": 0.2
    },
    # ... 其他rubrics
  ],
  "overall_feedback": "整体表现良好，工具使用正确，内容覆盖全面",
  "suggestions": "无重大问题"
}

print("📋 评估结果输出格式示例:")
print(json.dumps(example_output, indent=2, ensure_ascii=False))

print(f"\n🔑 关键字段:")
print(f"   - sample_id: {example_output['sample_id']}")
print(f"   - final_score: {example_output['final_score']} (新增字段)")
print(f"   - total_score: {example_output['total_score']}")
print(f"   - success: {example_output['success']}")

print(f"\n💡 使用方式:")
print(f"   1. 直接读取final_score字段获取最终得分")
print(f"   2. 可以计算平均分: sum(r['final_score'] for r in results if r['final_score'] is not None) / len(results)")
print(f"   3. 可以对比不同模型的性能")
