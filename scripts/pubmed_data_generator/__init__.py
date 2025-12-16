"""
PubMed 训练数据生成器包
用于为 pubmed_search 工具生成训练/评测数据

两种生成模式：
1. 基于证据采样的生成（generate_dataset.py）
2. 基于 GPT-5 轨迹的生成（generate_trajectory_dataset.py）- 推荐
"""

from .config import *
from .pubmed_client import PubMedMCPClient, EvidenceSnapshot, PaperEvidence
from .topic_generator import generate_topic_clusters, generate_query_templates
from .question_generator import generate_question_from_evidence, QuestionSample
from .rubric_generator import generate_training_sample, TrainingSample
from .generate_dataset import PubMedDatasetGenerator
from .trajectory_generator import GPT5TrajectoryGenerator, Trajectory
from .generate_trajectory_dataset import TrajectoryDatasetGenerator, TrajectoryDataSample

__all__ = [
    # 基础组件
    'PubMedMCPClient',
    'EvidenceSnapshot', 
    'PaperEvidence',
    'generate_topic_clusters',
    'generate_query_templates',
    'generate_question_from_evidence',
    'QuestionSample',
    'generate_training_sample',
    'TrainingSample',
    # 数据集生成器
    'PubMedDatasetGenerator',  # 基于证据采样
    'TrajectoryDatasetGenerator',  # 基于 GPT-5 轨迹（推荐）
    'GPT5TrajectoryGenerator',
    'Trajectory',
    'TrajectoryDataSample'
]

