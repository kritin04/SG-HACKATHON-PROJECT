import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "demo_data"))


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    from generate_repo import generate
    from app.engine.core import Engine
    repo = generate(tmp_path_factory.mktemp("repo") / "demo_repo")
    return Engine(repo_path=repo)


@pytest.fixture(scope="session")
def truth():
    return yaml.safe_load((ROOT / "demo_data" / "ground_truth.yaml").read_text(encoding="utf-8"))
