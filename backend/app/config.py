"""Runtime configuration (overridable via environment variables or a .env file in the project root)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# load KEY=VALUE lines from ROOT/.env (never committed) without overriding real environment variables
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

DEMO_DATA = Path(os.getenv("CAC_DEMO_DATA", ROOT / "demo_data"))
WORKSPACE = Path(os.getenv("CAC_WORKSPACE", ROOT / "workspace"))
REPO_OVERRIDE = os.getenv("CAC_REPO")          # analyse a different local checkout
DB_PATH = Path(os.getenv("CAC_DB", WORKSPACE / "copilot.db"))

OLLAMA_URL = os.getenv("CAC_OLLAMA_URL", "http://localhost:11434")
LIVE_MODEL = os.getenv("CAC_LIVE_MODEL", "qwen2.5:3b")
PRECOMPUTE_MODEL = os.getenv("CAC_PRECOMPUTE_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("CAC_EMBED_MODEL", "nomic-embed-text")
LLM_TIMEOUT_SECONDS = float(os.getenv("CAC_LLM_TIMEOUT", "600"))
PROMPT_VERSION = "v2"
SEMANTIC_SEARCH = os.getenv("CAC_SEMANTIC", "1") == "1"   # meaning-based search (needs the embedding model)

# Jira connection (empty JIRA_BASE_URL = use the demo files in demo_data/jira)
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_JQL = os.getenv("JIRA_JQL", "project = BOA ORDER BY created DESC")
JIRA_AC_FIELD = os.getenv("JIRA_AC_FIELD", "")
APP_URL = os.getenv("CAC_APP_URL", "http://localhost:5173")
