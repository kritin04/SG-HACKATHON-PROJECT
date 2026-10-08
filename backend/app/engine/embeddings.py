"""Meaning-based search over the map: find the parts of the system a Jira CR talks about, even without exact words.

Each service / API / table / function / outside system becomes a short text, turned into a vector by the local
embedding model (nomic-embed-text via Ollama). Vectors are cached on disk per commit.
"""
from __future__ import annotations

import hashlib
import json

import httpx
import numpy as np

from .. import config
from ..engine.evidence import STORE
from ..mapbuild.model import ProjectMap

EMBED_TYPES = ("service", "endpoint", "table", "function", "external", "column")


def embed(texts: list[str], prefix: str) -> np.ndarray:
    r = httpx.post(f"{config.OLLAMA_URL}/api/embed", json={"model": config.EMBED_MODEL,
                                                           "input": [prefix + t for t in texts]}, timeout=300)
    r.raise_for_status()
    v = np.array(r.json()["embeddings"], dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def node_text(pm: ProjectMap, n) -> str:
    p = n.props
    svc = n.parent.split(":", 1)[1] if n.parent else ""
    if n.type == "service":
        return f"{n.label} service ({p.get('capability')}): {p.get('description', '')}"
    if n.type == "endpoint":
        return f"API {n.label} of {svc}: {p.get('description', '')} handled by {p.get('handler')}"
    if n.type == "table":
        return f"database table {n.label} in {svc}: {p.get('description', '')} columns {', '.join(p.get('columns', []))}"
    if n.type == "column":
        return f"column {n.label} of table {n.parent.split('.')[-1]}"
    if n.type == "external":
        return f"outside system {n.label}: {p.get('description', '')}"
    code = STORE.get(n.evidence[0]).text[:300] if n.evidence and STORE.get(n.evidence[0]) else ""
    return f"function {n.label} in {svc} ({p.get('file', '')}): {code}"


class SemanticIndex:
    def __init__(self, pm: ProjectMap):
        self.ids = [n.id for n in pm.nodes.values() if n.type in EMBED_TYPES]
        self.texts = [node_text(pm, pm.nodes[i]) for i in self.ids]
        digest = hashlib.sha1(json.dumps(self.texts).encode()).hexdigest()[:12]
        cache = config.WORKSPACE / "embeddings" / f"{pm.sha[:12]}_{digest}.npy"
        if cache.exists():
            self.vectors = np.load(cache)
        else:
            parts = [embed(self.texts[i:i + 64], "search_document: ") for i in range(0, len(self.texts), 64)]
            self.vectors = np.vstack(parts)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, self.vectors)

    def search(self, query: str, k: int = 10, types: tuple[str, ...] | None = None, pm: ProjectMap | None = None):
        q = embed([query], "search_query: ")[0]
        sims = self.vectors @ q
        order = np.argsort(-sims)
        out = []
        for i in order:
            nid = self.ids[i]
            if types and pm and pm.nodes[nid].type not in types:
                continue
            out.append((nid, float(sims[i])))
            if len(out) >= k:
                break
        return out
