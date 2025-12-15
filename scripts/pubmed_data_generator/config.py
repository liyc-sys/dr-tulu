"""
PubMed 训练数据生成器配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API 配置
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# 使用 GPT-4o 或其他可用的高级模型
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o")

# MCP 服务器配置
MCP_HOST = os.getenv("MCP_TRANSPORT_HOST", "127.0.0.1")
MCP_PORT = os.getenv("MCP_TRANSPORT_PORT", "8003")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "StreamableHttpTransport")

# PubMed 搜索默认参数
DEFAULT_LIMIT = 5
DEFAULT_OFFSET = 0

# 数据生成配置
NUM_TOPIC_CLUSTERS = 30  # 主题簇数量
QUERIES_PER_CLUSTER = 10  # 每个主题簇的查询模板数量
SAMPLES_PER_QUERY = 1  # 每个查询生成的样本数量

# 输出路径
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../pubmed_training_data")

