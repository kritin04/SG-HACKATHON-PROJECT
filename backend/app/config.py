"""Runtime configuration (overridable via environment variables)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA = Path(os.getenv("CAC_DEMO_DATA", ROOT / "demo_data"))
WORKSPACE = Path(os.getenv("CAC_WORKSPACE", ROOT / "workspace"))
REPO_PATH = Path(os.getenv("CAC_REPO", WORKSPACE / "demo_repo"))
DB_PATH = Path(os.getenv("CAC_DB", WORKSPACE / "copilot.db"))
MAIN_REF = os.getenv("CAC_MAIN_REF", "main")

OLLAMA_URL = os.getenv("CAC_OLLAMA_URL", "http://localhost:11434")
LIVE_MODEL = os.getenv("CAC_LIVE_MODEL", "qwen2.5:3b")
PRECOMPUTE_MODEL = os.getenv("CAC_PRECOMPUTE_MODEL", "qwen2.5:7b")
LLM_TIMEOUT_SECONDS = float(os.getenv("CAC_LLM_TIMEOUT", "300"))
PROMPT_VERSION = "v1"
