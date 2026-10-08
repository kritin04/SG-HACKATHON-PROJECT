"""Engine facade: repo + catalog + fixtures, with index/graph cached per commit SHA."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from .. import config
from .catalog import Catalog, load_catalog
from .evidence import STORE
from .gitrepo import GitRepo
from .graph import build_graph
from .indexer import Index, build_index


class Engine:
    def __init__(self, repo_path: Path = config.REPO_PATH, data_dir: Path = config.DEMO_DATA):
        self.repo = GitRepo(repo_path)
        self.data_dir = Path(data_dir)
        self.catalog: Catalog = load_catalog(self.data_dir / "catalog")
        self.jira = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.data_dir / "jira").glob("*.json"))}
        self.prs = {int(p.stem): json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.data_dir / "prs").glob("*.json"))}
        self._index: dict[str, Index] = {}
        self._graph: dict[str, nx.DiGraph] = {}

    def index(self, ref: str = config.MAIN_REF) -> Index:
        sha = self.repo.rev(ref)
        if sha not in self._index:
            self._index[sha] = build_index(self.repo, sha)
        return self._index[sha]

    def graph(self, ref: str = config.MAIN_REF) -> nx.DiGraph:
        sha = self.repo.rev(ref)
        if sha not in self._graph:
            self._graph[sha] = build_graph(self.index(sha), self.catalog)
        return self._graph[sha]

    def refresh(self) -> None:
        """Drop caches (e.g. after the demo repo was regenerated or new commits arrived)."""
        self._index.clear()
        self._graph.clear()
        self.repo = GitRepo(self.repo.path)

    # ---- fixtures -------------------------------------------------------
    def issue_text(self, key: str) -> str:
        f = self.jira[key]["fields"]
        ac = "\n".join(f"- {a}" for a in f.get("acceptance_criteria", []))
        return f"{f['summary']}\n\n{f.get('description', '')}\n\nAcceptance criteria:\n{ac}"

    def issue_evidence(self, key: str) -> str:
        return STORE.add("jira", f"Jira {key}", self.issue_text(key), path=f"jira/{key}")

    def pr_for_issue(self, key: str) -> dict | None:
        return next((pr for pr in self.prs.values() if pr.get("jira_key") == key), None)

    def pr_evidence(self, number: int) -> str:
        pr = self.prs[number]
        reviews = ", ".join(f"{r['user']['login']} ({r['state']})" for r in pr.get("reviews", [])) or "none"
        text = f"PR #{number}: {pr['title']}\nAuthor: {pr['user']['login']}\nApproved reviews: {reviews}\n{pr.get('body', '')}"
        return STORE.add("pr", f"PR #{number}", text, path=f"pr/{number}")
