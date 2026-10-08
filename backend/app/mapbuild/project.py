"""Project settings (demo_data/project.yaml) and file helpers for the analysed repository."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import config


@dataclass
class Project:
    name: str
    root: Path
    manifests_dir: Path
    source_dir: Path
    pinned_sha: str
    pinned_label: str
    exclude: list[str] = field(default_factory=list)
    ops_endpoints: list[str] = field(default_factory=list)

    @property
    def sha(self) -> str:
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True,
                                  text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return self.pinned_sha

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def excluded(self, path: Path) -> bool:
        r = self.rel(path)
        return any(r == e or r.startswith(e.rstrip("/") + "/") for e in self.exclude)

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")


def load_project(path: Path | None = None) -> Project:
    path = path or (config.DEMO_DATA / "project.yaml")
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    root = (config.ROOT / d["local_path"]).resolve()
    if config.REPO_OVERRIDE:
        root = Path(config.REPO_OVERRIDE).resolve()
    return Project(d["name"], root, root / d["manifests_dir"], root / d["source_dir"], d["pinned_sha"],
                   d.get("pinned_label", ""), d.get("exclude", []), d.get("ops_endpoints", []))
