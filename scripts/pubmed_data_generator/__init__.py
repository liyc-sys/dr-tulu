"""
PubMed 训练数据生成器包
用于为 pubmed_search 工具生成训练/评测数据
"""

from .config import *
from .pubmed_client import PubMedMCPClient, EvidenceSnapshot, PaperEvidence
from .topic_generator import generate_topic_clusters, generate_query_templates
from .question_generator import generate_question_from_evidence, QuestionSample
from .rubric_generator import generate_training_sample, TrainingSample
from .generate_dataset import PubMedDatasetGenerator

__all__ = [
    'PubMedMCPClient',
    'EvidenceSnapshot', 
    'PaperEvidence',
    'generate_topic_clusters',
    'generate_query_templates',
    'generate_question_from_evidence',
    'QuestionSample',
    'generate_training_sample',
    'TrainingSample',
    'PubMedDatasetGenerator'
]

