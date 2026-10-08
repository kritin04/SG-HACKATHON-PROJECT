import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# tests always use the fixed demo change requests, never a live Jira connection from .env
from app import config  # noqa: E402

config.JIRA_BASE_URL = ""
