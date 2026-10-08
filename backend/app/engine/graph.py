"""Dependency graph built from an Index plus the curated Catalog.

Edge u -> v means "u uses / refers to v". Each edge carries type, confidence, tier and evidence.
IMPACT_RULES say how a change propagates along each edge type (forward = change in u impacts v,
reverse = change in v impacts u).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import networkx as nx

from .catalog import Catalog
from .indexer import Index

# edge type -> (forward weight, reverse weight)
IMPACT_RULES: dict[str, tuple[float, float]] = {
    "contains": (0.7, 1.0),
    "calls": (0.0, 0.8),
    "handled_by": (0.9, 0.95),
    "reads_config": (0.5, 0.9),
    "reads": (0.0, 0.8),
    "writes": (0.9, 0.6),
    "migrates": (0.9, 0.0),
    "publishes": (0.85, 0.0),
    "subscribes": (0.0, 0.85),
    "http_call": (0.8, 0.8),
    "covers": (0.0, 1.0),
    "mentions": (0.0, 0.9),
    "consumes": (0.0, 0.95),
}
TERMINAL_KINDS = {"test", "doc", "ext"}
DECAY = 0.9

EDGE_VERBS = {
    "contains": "contains", "calls": "calls", "handled_by": "is handled by", "reads_config": "reads config",
    "reads": "reads table", "writes": "writes table", "migrates": "alters schema of", "publishes": "publishes", "subscribes": "subscribes to",
    "http_call": "calls API", "covers": "tests", "mentions": "documents", "consumes": "consumes",
}


def build_graph(ix: Index, cat: Catalog) -> nx.DiGraph:
    G = nx.DiGraph()

    def node(nid, kind, label, tier="inferred", evidence=None, **attrs):
        if nid not in G or "kind" not in G.nodes[nid]:
            G.add_node(nid, kind=kind, label=label, tier=tier, evidence=[e for e in (evidence or []) if e], **attrs)
        return nid

    def edge(u, v, etype, confidence=0.95, tier="inferred", evidence=None):
        if u == v:
            return
        if G.has_edge(u, v):
            return
        G.add_edge(u, v, type=etype, confidence=confidence, tier=tier, evidence=[e for e in (evidence or []) if e])

    def system_of(path):
        s = cat.system_for_path(path)
        return s.id if s else None

    for mod in ix.modules.values():
        if mod.is_test:
            continue
        node(mod.id, "module", mod.name, path=mod.path, system=system_of(mod.path))

    for s in ix.symbols.values():
        if s.kind == "test":
            node(s.id, "test", f"{s.module}::{s.name}", path=s.path, evidence=[s.evidence_id])
            for callee in s.calls:
                edge(s.id, callee, "covers", 0.9, evidence=[s.evidence_id])
            continue
        node(s.id, "symbol", f"{s.module}.{s.qualname}", path=s.path, system=system_of(s.path),
             signature=s.signature, evidence=[s.evidence_id])
        G.nodes[s.id]["evidence"] = [s.evidence_id]
        edge(f"mod:{s.module}", s.id, "contains", 1.0, evidence=[s.evidence_id])
        for callee in s.calls:
            edge(s.id, callee, "calls", 0.95, evidence=[s.evidence_id])
        for (m, p) in s.routes:
            rid = node(f"route:{m} {p}", "route", f"{m} {p}", system=system_of(s.path), evidence=[s.evidence_id])
            edge(rid, s.id, "handled_by", 1.0, evidence=[s.evidence_id])
        for k in s.config_keys:
            edge(s.id, node(f"cfg:{k}", "config", k), "reads_config", 0.95, evidence=[s.evidence_id])
        for t in s.tables_read:
            edge(s.id, node(f"table:{t}", "table", t), "reads", 0.85, evidence=[s.evidence_id])
        for t in s.tables_written:
            edge(s.id, node(f"table:{t}", "table", t), "writes", 0.85, evidence=[s.evidence_id])
        for tp in s.topics_pub:
            edge(s.id, node(f"topic:{tp}", "topic", tp), "publishes", 0.9, evidence=[s.evidence_id])
        for tp in s.topics_sub:
            edge(s.id, node(f"topic:{tp}", "topic", tp), "subscribes", 0.9, evidence=[s.evidence_id])

    # cross-service HTTP calls matched by method + path (medium confidence: string matching)
    for s in ix.code_symbols():
        for (m, p) in s.http_calls:
            if f"route:{m} {p}" in G:
                edge(s.id, f"route:{m} {p}", "http_call", 0.7, evidence=[s.evidence_id])

    for sf in ix.sql_files.values():
        node(sf.id, "migration", sf.path, path=sf.path, system=system_of(sf.path), evidence=[sf.evidence_id])
        for t in sf.tables_written:
            edge(sf.id, node(f"table:{t}", "table", t), "migrates", 0.9, evidence=[sf.evidence_id])

    # docs: exact identifier mentions
    by_name = ix.symbols_by_name()
    for d in ix.docs.values():
        node(d.id, "doc", f"{d.path} § {d.heading}", path=d.path, evidence=[d.evidence_id])
        targets = set()
        for name in d.names:
            for s in by_name.get(name, []):
                targets.add(s.id)
            for prefix in ("cfg:", "table:", "topic:"):
                if f"{prefix}{name}" in G:
                    targets.add(f"{prefix}{name}")
        for r in d.routes:
            if f"route:{r}" in G:
                targets.add(f"route:{r}")
        for t in targets:
            edge(d.id, t, "mentions", 0.95, evidence=[d.evidence_id])

    # curated: systems and external consumers
    for sysm in cat.systems:
        sid = node(f"system:{sysm.id}", "system", sysm.name, tier="curated", owners=sysm.owners,
                   criticality=sysm.criticality, evidence=[cat.evidence.get(f"system:{sysm.id}")])
        for n, data in list(G.nodes(data=True)):
            if data.get("kind") == "module" and data.get("system") == sysm.id:
                G.add_edge(sid, n, type="system_contains", confidence=1.0, tier="curated",
                           evidence=[cat.evidence.get(f"system:{sysm.id}")])
    for x in cat.external_systems:
        xid = node(f"ext:{x.id}", "ext", x.name, tier="curated", owners=x.owners, criticality=x.criticality,
                   description=x.description, evidence=[cat.evidence.get(f"ext:{x.id}")])
        for target in x.consumes:
            if target in G:
                edge(xid, target, "consumes", 1.0, tier="curated", evidence=[cat.evidence.get(f"ext:{x.id}")])
    return G


@dataclass
class Reach:
    node: str
    score: float
    path: list[tuple[str, str, str]] = field(default_factory=list)  # (from, edge_type, to)
    seed: str = ""


def propagate(G: nx.DiGraph, seeds: dict[str, float], max_depth: int = 4, min_score: float = 0.2) -> dict[str, Reach]:
    """Best-first max-product propagation of change impact from seed nodes."""
    best: dict[str, Reach] = {}
    heap = []
    for nid, w in seeds.items():
        if nid in G:
            best[nid] = Reach(nid, w, [], nid)
            heapq.heappush(heap, (-w, nid, 0))
    while heap:
        neg, nid, depth = heapq.heappop(heap)
        score = -neg
        if score < best[nid].score - 1e-9 or depth >= max_depth:
            continue
        if G.nodes[nid].get("kind") in TERMINAL_KINDS:
            continue
        nbrs = []
        for _, v, d in G.out_edges(nid, data=True):
            fw = IMPACT_RULES.get(d["type"], (0, 0))[0]
            if fw:
                nbrs.append((v, fw * d["confidence"], d["type"], (nid, d["type"], v)))
        for u, _, d in G.in_edges(nid, data=True):
            rw = IMPACT_RULES.get(d["type"], (0, 0))[1]
            if rw:
                nbrs.append((u, rw * d["confidence"], d["type"], (u, d["type"], nid)))
        for v, w, _etype, step in nbrs:
            s = score * w * DECAY
            if s < min_score:
                continue
            if v not in best or s > best[v].score + 1e-9:
                best[v] = Reach(v, s, best[nid].path + [step], best[nid].seed)
                heapq.heappush(heap, (-s, v, depth + 1))
    return best


def describe_path(G: nx.DiGraph, path: list[tuple[str, str, str]]) -> list[dict]:
    out = []
    for u, etype, v in path:
        d = G.edges[u, v]
        out.append({
            "from": G.nodes[u]["label"], "from_id": u, "to": G.nodes[v]["label"], "to_id": v,
            "relation": EDGE_VERBS.get(etype, etype), "tier": d["tier"], "confidence": d["confidence"],
            "evidence": d["evidence"],
        })
    return out
