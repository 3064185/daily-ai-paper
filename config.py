"""
Configuration for Daily AI News & Paper Digest.
"""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env"

# ── Date ──────────────────────────────────────────────────────────────
# Override with --date YYYY-MM-DD for backfill
RUN_DATE = None          # datetime.date, set by daily_pipeline

# ── OpenAI ────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Email (SMTP SSL) ──────────────────────────────────────────────────
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
MAX_EMAIL_ATTACHMENT_MB = int(os.getenv("MAX_EMAIL_ATTACHMENT_MB", "18"))

# ── Paper retrieval ───────────────────────────────────────────────────
MAX_PAPERS_PER_SOURCE = int(os.getenv("MAX_PAPERS_PER_SOURCE", "30"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "25"))
DOWNLOAD_OPEN_ACCESS_PDFS = os.getenv("DOWNLOAD_OPEN_ACCESS_PDFS", "true").lower() == "true"
MAX_PDF_ATTACHMENT_MB = int(os.getenv("MAX_PDF_ATTACHMENT_MB", "12"))

# ── API keys ──────────────────────────────────────────────────────────
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")

# ── Proxy ─────────────────────────────────────────────────────────────
USE_SYSTEM_PROXY = os.getenv("USE_SYSTEM_PROXY", "false").lower() == "true"

# ── Target journals / conferences ────────────────────────────────────
TARGET_JOURNALS = [
    "Nature", "Science", "Cell",
    "Nature Machine Intelligence",
    "Nature Computational Science",
    "Nature Communications",
    "Science Advances",
    "PNAS",
    "NeurIPS", "ICML", "ICLR",
    "CVPR", "ICCV", "ECCV",
    "ACL", "EMNLP", "NAACL",
    "AAAI", "IJCAI",
]

TARGET_KEYWORDS = [
    "large language model", "LLM",
    "artificial intelligence", "AI",
    "machine learning", "deep learning",
    "neural network", "transformer",
    "diffusion model", "generative AI",
    "reinforcement learning", "RLHF",
    "reasoning", "chain-of-thought",
    "multi-modal", "multimodal",
    "computer vision", "NLP",
    "agent", "autonomous",
    "robotics", "embodied",
    "quantum", "optimization",
    "benchmark", "dataset",
]
