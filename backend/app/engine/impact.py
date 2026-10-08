"""Change Impact Analyzer: Jira change request -> ranked, evidence-backed impact report."""
from __future__ import annotations

import re
from collections import defaultdict

from .. import config
from .controls import evaluate_controls
from .core import Engine
from .graph import Reach, describe_path, propagate

ROUTE_RE = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s,;)]*)")
UPPER_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
MIN_SCORE = 0.25


def confidence_label(score: float) -> str:
    return "High" if score >= 0.6 else "Medium" if score >= 0.35 else "Low"


def find_seeds(engine: Engine, key: str, ref: str) -> tuple[dict[str, dict], list[str], str]:
    """Return seeds {node: {weight, reason, evidence}}, new config keys mentioned, jira evidence id."""
    G = engine.graph(ref)
    cat = engine.catalog
    text = engine.issue_text(key)
    jev = engine.issue_evidence(key)
    seeds: dict[str, dict] = {}

    def seed(nid, weight, reason, evidence):
        if nid in G and (nid not in seeds or seeds[nid]["weight"] < weight):
            seeds[nid] = {"weight": weight, "reason": reason, "evidence": [e for e in evidence if e]}

    for m, p in ROUTE_RE.findall(text):
        seed(f"route:{m} {p}", 1.0, f"Change request names API {m} {p}", [jev])
    new_config = []
    for tok in sorted(set(UPPER_RE.findall(text))):
        if f"cfg:{tok}" in G:
            seed(f"cfg:{tok}", 1.0, f"Change request names config key {tok}", [jev])
        else:
            new_config.append(tok)
    by_name = engine.index(ref).symbols_by_name()
    for tok in sorted(set(SNAKE_RE.findall(text))):
        for s in by_name.get(tok, []):
            seed(s.id, 1.0, f"Change request names function {tok}", [jev])
        for prefix in ("table:", "topic:"):
            seed(f"{prefix}{tok}", 1.0, f"Change request names {prefix[:-1]} {tok}", [jev])
    for term, word in cat.match_terms(text):
        for ent in term.entities:
            seed(ent, 0.8, f'Business term "{word}" maps to this via the glossary', [jev, cat.evidence.get(f"term:{term.term}")])
    return seeds, new_config, jev


def _tier(G, reach: Reach, seed_info: dict) -> str:
    if any(G.edges[u, v]["tier"] == "curated" for u, _, v in reach.path):
        return "curated"
    return "curated" if "glossary" in seed_info.get("reason", "") else "inferred"


def _item(G, reach: Reach, seeds: dict, extra: dict | None = None) -> dict:
    nd = G.nodes[reach.node]
    seed_info = seeds.get(reach.seed, {})
    steps = describe_path(G, reach.path)
    evidence = list(dict.fromkeys(seed_info.get("evidence", []) + [e for s in steps for e in s["evidence"]] + nd.get("evidence", [])))
    item = {
        "id": reach.node, "label": nd["label"], "kind": nd["kind"], "score": round(reach.score, 2),
        "confidence": confidence_label(reach.score), "tier": _tier(G, reach, seed_info),
        "seed": {"node": reach.seed, "label": G.nodes[reach.seed]["label"], "reason": seed_info.get("reason", "")},
        "why": steps, "evidence": [e for e in evidence if e],
    }
    if extra:
        item.update(extra)
    return item


def analyze(engine: Engine, key: str, ref: str = config.MAIN_REF) -> dict:
    G = engine.graph(ref)
    ix = engine.index(ref)
    cat = engine.catalog
    issue = engine.jira[key]["fields"]
    seeds, new_config, jev = find_seeds(engine, key, ref)
    reach = propagate(G, {n: s["weight"] for n, s in seeds.items()})
    reach = {n: r for n, r in reach.items() if r.score >= MIN_SCORE}

    def kind(n):
        return G.nodes[n]["kind"]

    # ---- code: modules (aggregate their symbols) -----------------------
    module_best: dict[str, Reach] = {}
    module_syms: dict[str, list[dict]] = defaultdict(list)
    for n, r in reach.items():
        if kind(n) == "symbol":
            mod = "mod:" + ix.symbols[n].module
            module_syms[mod].append({"id": n, "label": G.nodes[n]["label"], "score": round(r.score, 2),
                                     "signature": G.nodes[n].get("signature")})
            if mod not in module_best or r.score > module_best[mod].score:
                module_best[mod] = r if mod not in reach or reach[mod].score < r.score else reach[mod]
        elif kind(n) == "module":
            if n not in module_best or r.score > module_best[n].score:
                module_best[n] = r
    code = []
    for mod, r in module_best.items():
        if mod not in G or G.nodes[mod].get("system") == "platform":
            continue
        best = reach.get(mod) if mod in reach and reach[mod].score >= r.score else r
        item = _item(G, best, seeds, {"id": mod, "label": G.nodes[mod]["label"], "kind": "module",
                                      "path": G.nodes[mod]["path"], "system": G.nodes[mod].get("system"),
                                      "symbols": sorted(module_syms[mod], key=lambda s: -s["score"])})
        item["score"] = round(max(r.score, reach[mod].score if mod in reach else 0), 2)
        item["confidence"] = confidence_label(item["score"])
        code.append(item)
    code.sort(key=lambda i: -i["score"])

    interfaces = sorted((_item(G, r, seeds) for n, r in reach.items() if kind(n) == "route"), key=lambda i: -i["score"])

    # ---- systems (curated) ----------------------------------------------
    systems: dict[str, dict] = {}
    for it in code:
        sid = it.get("system")
        s = cat.system(sid) if sid else None
        if s and (sid not in systems or systems[sid]["score"] < it["score"]):
            systems[sid] = {"id": f"system:{sid}", "label": s.name, "kind": "system", "score": it["score"],
                            "confidence": it["confidence"], "tier": "curated", "criticality": s.criticality,
                            "owners": s.owners, "reason": f"Contains impacted module {it['label']}",
                            "evidence": [cat.evidence.get(f"system:{sid}")] + it["evidence"][:2]}
    for comp in issue.get("components", []):
        sid = cat.components.get(comp["name"])
        s = cat.system(sid) if sid else None
        if s and sid not in systems:
            systems[sid] = {"id": f"system:{sid}", "label": s.name, "kind": "system", "score": 0.5,
                            "confidence": "Medium", "tier": "curated", "criticality": s.criticality,
                            "owners": s.owners, "reason": f"Jira component {comp['name']}",
                            "evidence": [jev, cat.evidence.get(f"system:{sid}")]}
    external = sorted((_item(G, r, seeds, {"owners": G.nodes[n].get("owners", []),
                                           "criticality": G.nodes[n].get("criticality"),
                                           "description": G.nodes[n].get("description")})
                       for n, r in reach.items() if kind(n) == "ext"), key=lambda i: -i["score"])

    # ---- data -------------------------------------------------------------
    impacted_syms = [ix.symbols[n] for n, r in reach.items() if kind(n) == "symbol" and r.score >= 0.3]
    data = []
    for n, r in reach.items():
        if kind(n) in ("table", "topic", "config"):
            extra = {}
            if kind(n) == "table":
                t = G.nodes[n]["label"]
                cols = {c for s in impacted_syms for c in s.columns if c.startswith(t + ".")}
                classes = cat.classes_for_columns(cols)
                extra = {"classifications": sorted(set(classes.values())), "columns": sorted(cols),
                         "classified_columns": classes}
            data.append(_item(G, r, seeds, extra))
    for k in new_config:
        data.append({"id": f"cfg:{k}", "label": k, "kind": "config", "score": 0.9, "confidence": "High",
                     "tier": "inferred", "new": True, "why": [],
                     "seed": {"node": None, "label": k, "reason": "New configuration key named in the change request"},
                     "evidence": [jev]})
    data.sort(key=lambda i: -i["score"])

    # ---- docs --------------------------------------------------------------
    docs: dict[str, dict] = {}
    for n, r in reach.items():
        if kind(n) == "doc":
            it = _item(G, r, seeds)
            path = G.nodes[n]["path"]
            d = docs.setdefault(path, {"id": f"docfile:{path}", "label": path, "kind": "doc", "score": 0,
                                       "sections": [], "tier": "inferred", "evidence": []})
            d["sections"].append(it)
            d["score"] = max(d["score"], it["score"])
            d["evidence"] = list(dict.fromkeys(d["evidence"] + it["evidence"]))
    words = [w for _t, w in cat.match_terms(engine.issue_text(key))]
    for sec in ix.docs.values():
        if sec.level == 1 and any(w.lower() in sec.heading.lower() for w in words) and sec.path not in docs:
            docs[sec.path] = {"id": f"docfile:{sec.path}", "label": sec.path, "kind": "doc", "score": 0.5,
                              "sections": [], "tier": "inferred", "evidence": [sec.evidence_id, jev],
                              "reason": f'Document title "{sec.heading}" matches a business term in the change request'}
    doc_list = sorted(docs.values(), key=lambda d: -d["score"])
    for d in doc_list:
        d["score"] = round(d["score"], 2)
        d["confidence"] = confidence_label(d["score"])

    # ---- tests -------------------------------------------------------------
    test_files: dict[str, dict] = {}
    for n, r in reach.items():
        if kind(n) == "test":
            path = G.nodes[n]["path"]
            tf = test_files.setdefault(path, {"id": f"testfile:{path}", "label": path, "kind": "test_file",
                                              "score": 0, "tests": [], "evidence": [], "tier": "inferred"})
            tf["tests"].append({"id": n, "label": G.nodes[n]["label"].split("::")[-1], "score": round(r.score, 2),
                                "why": describe_path(G, r.path)})
            tf["score"] = round(max(tf["score"], r.score), 2)
            tf["evidence"] = list(dict.fromkeys(tf["evidence"] + G.nodes[n]["evidence"]))
    tests_to_run = sorted(test_files.values(), key=lambda t: -t["score"])
    for t in tests_to_run:
        t["confidence"] = confidence_label(t["score"])
    gaps: dict[str, dict] = {}
    for s in impacted_syms:
        if G.nodes[s.id].get("system") == "platform":
            continue
        covered = any(G.edges[u, s.id]["type"] == "covers" for u in G.predecessors(s.id))
        if not covered:
            mod = f"mod:{s.module}"
            g = gaps.setdefault(mod, {"id": mod, "label": s.module, "kind": "test_gap", "symbols": [],
                                      "score": 0, "evidence": []})
            g["symbols"].append(G.nodes[s.id]["label"])
            g["score"] = round(max(g["score"], reach[s.id].score), 2)
            g["evidence"].append(s.evidence_id)
    test_gaps = sorted(gaps.values(), key=lambda g: -g["score"])
    for g in test_gaps:
        g["confidence"] = confidence_label(g["score"])

    # ---- controls ------------------------------------------------------------
    paths = {it["path"] for it in code if it["score"] >= 0.35}
    data_classes: dict[str, list[str]] = defaultdict(list)
    for d in data:
        for col, cls in d.get("classified_columns", {}).items():
            data_classes[cls].append(col)
    externals = {e["id"].split(":", 1)[1] for e in external}
    controls = evaluate_controls(cat, paths=paths, data_classes=data_classes, externals=externals,
                                 text=engine.issue_text(key))

    # ---- owners --------------------------------------------------------------
    owners: dict[str, dict] = {}
    for s in systems.values():
        for o in s["owners"]:
            owners.setdefault(o, {"id": o, "label": o, "kind": "team", "reasons": [], "tier": "curated"})["reasons"].append(f"Owns {s['label']}")
    for e in external:
        for o in e.get("owners", []):
            owners.setdefault(o, {"id": o, "label": o, "kind": "team", "reasons": [], "tier": "curated"})["reasons"].append(f"Owns downstream {e['label']}")
    for c in controls:
        for login in c["approvers"]:
            p = cat.people.get(login)
            owners.setdefault(login, {"id": login, "label": p.name if p else login, "kind": "person", "reasons": [],
                                      "tier": "curated"})["reasons"].append(f"Required approver for {c['id']} {c['name']}")

    risk = assess_risk(code, external, data, controls, test_gaps, systems)
    return {
        "cr": {"key": key, "summary": issue["summary"], "description": issue.get("description", ""),
               "acceptance_criteria": issue.get("acceptance_criteria", []), "priority": issue["priority"]["name"],
               "status": issue["status"]["name"], "components": [c["name"] for c in issue.get("components", [])],
               "labels": issue.get("labels", []), "assignee": issue.get("assignee", {}).get("displayName"),
               "evidence": jev},
        "ref": ref, "sha": engine.repo.rev(ref)[:7],
        "seeds": [{"id": n, "label": G.nodes[n]["label"], **s} for n, s in sorted(seeds.items(), key=lambda kv: -kv[1]["weight"])],
        "risk": risk,
        "code": code, "interfaces": interfaces, "systems": sorted(systems.values(), key=lambda s: -s["score"]),
        "external": external, "data": data, "docs": doc_list,
        "tests": {"to_run": tests_to_run, "gaps": test_gaps},
        "owners": list(owners.values()), "controls": controls,
        "stats": {"modules": len(code), "systems": len(systems), "external": len(external), "tests": sum(len(t["tests"]) for t in tests_to_run),
                  "test_gaps": len(test_gaps), "docs": len(doc_list), "controls": len(controls)},
    }


def assess_risk(code, external, data, controls, test_gaps, systems) -> dict:
    points, reasons = 0, []
    classes = {c for d in data for c in d.get("classifications", [])}
    if "PII" in classes:
        points += 3
        reasons.append("Touches personal data (PII)")
    if "Financial" in classes:
        points += 1
        reasons.append("Touches financial records")
    if external:
        points += min(2 * len(external), 4)
        reasons.append(f"{len(external)} downstream system(s) outside this codebase: " + ", ".join(e["label"] for e in external))
    if controls:
        points += len(controls)
        reasons.append(f"{len(controls)} change control(s) triggered: " + ", ".join(c["id"] for c in controls))
    if test_gaps:
        points += 1
        reasons.append(f"{len(test_gaps)} impacted module(s) without automated tests")
    high_crit = [s["label"] for s in systems.values() if s.get("criticality") == "high"]
    if high_crit:
        points += 1
        reasons.append("High-criticality systems: " + ", ".join(high_crit))
    level = "High" if points >= 6 else "Medium" if points >= 3 else "Low"
    return {"level": level, "points": points, "reasons": reasons}
