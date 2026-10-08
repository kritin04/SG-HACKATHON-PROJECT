"""Customer journeys: the ordered chain of calls behind each thing a customer does on the website.

The chain is computed from VERIFIED map links only, walking each function's calls in source-line order.
The AI later just names the journey and describes the steps in plain words; it cannot add or reorder steps.
"""
from __future__ import annotations

from .model import ProjectMap

STEP_TYPES = ("calls", "calls_api", "reads", "writes")


def _events(pm: ProjectMap, fn_id: str, seen: set[str], depth: int = 0) -> list:
    """Ordered (by line) outgoing API/data edges of a function, expanding the functions it calls."""
    if fn_id in seen or depth > 4:
        return []
    seen.add(fn_id)
    out = []
    for e in sorted((e for e in pm.out_edges(fn_id) if e.type in STEP_TYPES), key=lambda e: e.props.get("line", 0)):
        if e.type == "calls":
            out.extend(_events(pm, e.target, seen, depth + 1))
        else:
            out.append(e)
    return out


def _steps_for_endpoint(pm: ProjectMap, ep_id: str, steps: list, seen_edges: set, depth: int) -> None:
    ep = pm.nodes[ep_id]
    handler = pm.out_edges(ep_id, "handled_by")
    if not handler or depth > 3:
        return
    data_found = False
    for e in _events(pm, handler[0].target, set()):
        if e.type == "calls_api":
            tgt = pm.nodes[e.target]
            key = f"{ep.parent}|calls_api|{e.target}"
            if key in seen_edges:
                continue
            seen_edges.add(key)
            steps.append({"from": ep.parent, "to": tgt.parent, "endpoint": e.target, "detail": tgt.label, "kind": "api",
                          "edge": f"{ep.parent}|calls_api|{tgt.parent}", "evidence": e.evidence[:2]})
            _steps_for_endpoint(pm, e.target, steps, seen_edges, depth + 1)
        elif e.target.startswith("table:"):
            data_found = True
            key = f"{ep.parent}|{e.type}|{e.target}"
            if key in seen_edges:
                continue
            seen_edges.add(key)
            steps.append({"from": ep.parent, "to": e.target, "detail": f"{e.type} {pm.nodes[e.target].label}",
                          "kind": e.type, "edge": key, "evidence": e.evidence[:2]})
    if not data_found:
        # e.g. balancereader answers from an in-memory cache that a background job keeps filled from the table
        for e in pm.out_edges(ep.parent):
            key = f"{ep.parent}|{e.type}|{e.target}"
            if e.type in ("reads", "writes") and e.target.startswith("table:") and key not in seen_edges:
                seen_edges.add(key)
                steps.append({"from": ep.parent, "to": e.target, "detail": f"{e.type} {pm.nodes[e.target].label}",
                              "kind": e.type, "background": True, "edge": key, "evidence": e.evidence[:2]})


def compute_journeys(pm: ProjectMap) -> list[dict]:
    journeys = []
    for svc in [e.target for e in pm.out_edges("user:customer", "uses")]:
        for ep in [n for n in pm.nodes.values() if n.type == "endpoint" and n.parent == svc and not n.props.get("ops")]:
            steps = [{"from": "user:customer", "to": svc, "endpoint": ep.id, "detail": ep.label, "kind": "user",
                      "edge": f"user:customer|uses|{svc}", "evidence": ep.evidence[:1]}]
            _steps_for_endpoint(pm, ep.id, steps, set(), 0)
            if len(steps) > 1:
                journeys.append({"id": f"journey:{ep.id}", "entry": ep.id, "name": ep.label, "steps": steps})
    # GET pages that show exactly the same chain (e.g. "/" redirects to "/home"): keep the more specific one
    keep = {}
    for j in journeys:
        key = (j["entry"].split(":")[-1].split()[0], tuple(s["edge"] for s in j["steps"][1:]))
        if key[0] != "GET" or key not in keep or len(j["entry"]) > len(keep[key]["entry"]):
            keep[key if key[0] == "GET" else j["id"]] = j
    return list(keep.values())
