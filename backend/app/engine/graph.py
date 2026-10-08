"""Change propagation over the dependency map ("if X changes, what else is affected?").

Each link type has two weights:
  forward = a change in the SOURCE affects the TARGET
  reverse = a change in the TARGET affects the SOURCE
Example: A --calls_api--> B. If B's API changes, the caller A is affected (reverse 0.8).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from ..mapbuild.model import EDGE_VERB, ProjectMap

IMPACT_RULES: dict[str, tuple[float, float]] = {
    "calls_api": (0.5, 0.85),          # callee changes -> caller affected; caller payload changes -> callee
    "handled_by": (0.9, 0.95),         # endpoint <-> its handler function
    "calls": (0.0, 0.8),               # function calls function
    "reads": (0.0, 0.85),              # table changes -> readers affected
    "writes": (0.8, 0.7),              # writer changes -> table data affected; table changes -> writer affected
    "needs_config": (0.0, 0.9),        # setting changes -> service affected
    "trusts_tokens_from": (0.0, 0.6),  # token issuer changes -> verifiers affected
    "tests": (0.0, 1.0),               # code changes -> its tests must be re-run
    "consumes": (0.0, 0.95),           # our table changes -> outside system affected
    "uses": (0.0, 0.9),                # website changes -> customer affected
    "part_of": (1.0, 0.0),             # endpoint/function/table changes -> its service/database affected
}
TERMINAL = {"test", "external", "user"}
DECAY = 0.9


@dataclass
class Reach:
    node: str
    score: float
    path: list[tuple[str, str, str]] = field(default_factory=list)   # (source, edge type, target) as stored
    seed: str = ""


def _neighbours(pm: ProjectMap):
    """Adjacency with weights, including implicit child -> parent 'part_of' links."""
    adj: dict[str, list[tuple[str, float, tuple[str, str, str]]]] = {}
    for e in pm.edges.values():
        fw, rv = IMPACT_RULES.get(e.type, (0.0, 0.0))
        if fw:
            adj.setdefault(e.source, []).append((e.target, fw * e.confidence, (e.source, e.type, e.target)))
        if rv:
            adj.setdefault(e.target, []).append((e.source, rv * e.confidence, (e.source, e.type, e.target)))
    for n in pm.nodes.values():
        if n.parent and n.type in ("endpoint", "function", "table"):
            adj.setdefault(n.id, []).append((n.parent, 1.0, (n.id, "part_of", n.parent)))
    return adj


def propagate(pm: ProjectMap, seeds: dict[str, float], max_depth: int = 4, min_score: float = 0.25) -> dict[str, Reach]:
    adj = _neighbours(pm)
    best: dict[str, Reach] = {}
    heap = []
    for nid, w in seeds.items():
        if nid in pm.nodes:
            best[nid] = Reach(nid, w, [], nid)
            heapq.heappush(heap, (-w, nid, 0))
    while heap:
        neg, nid, depth = heapq.heappop(heap)
        if -neg < best[nid].score - 1e-9 or depth >= max_depth or pm.nodes[nid].type in TERMINAL:
            continue
        for nb, w, step in adj.get(nid, []):
            s = -neg * w * DECAY
            if s >= min_score and (nb not in best or s > best[nb].score + 1e-9):
                best[nb] = Reach(nb, s, best[nid].path + [step], best[nid].seed)
                heapq.heappush(heap, (-s, nb, depth + 1))
    return best


def describe_path(pm: ProjectMap, path: list[tuple[str, str, str]]) -> list[dict]:
    out = []
    for s, t, d in path:
        e = pm.edges.get(f"{s}|{t}|{d}")
        out.append({"from": pm.nodes[s].label, "from_id": s, "to": pm.nodes[d].label, "to_id": d,
                    "relation": EDGE_VERB.get(t, "is part of" if t == "part_of" else t),
                    "origin": e.origin if e else "code", "confidence": e.confidence if e else 1.0,
                    "evidence": e.evidence if e else []})
    return out
