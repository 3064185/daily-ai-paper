"""
Configuration for Daily AI News & Paper Digest.
Auto-loads .env file on first import.
"""
import os
from pathlib import Path

# ── Auto-load .env ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key:  # only set if not already set by system env
            os.environ.setdefault(key, val)

# ── Paths ─────────────────────────────────────────────────────────────
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"

# ── Date ──────────────────────────────────────────────────────────────
# Override with --date YYYY-MM-DD for backfill
RUN_DATE = None          # datetime.date, set by daily_pipeline

# ── LLM (OpenAI-compatible, supports DeepSeek etc.) ──────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Email (SMTP SSL) ──────────────────────────────────────────────────
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "")
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
