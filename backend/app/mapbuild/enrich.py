"""Step 5 of the map: AI enrichment. The AI PROPOSES, code VERIFIES, and only verified results are applied.

Tasks (all cached per commit, so they run once with the 7B model via scripts/build_map.py):
  1. resolve   - decide unresolved calls (e.g. the HTTP method hidden in a helper); the decision must be one of the
                 code-derived candidates and the quoted line must exist in the evidence.
  2. describe  - plain-English summary per service and endpoint, business label per link.
  3. tables    - summary per table and sensitivity SUGGESTIONS for unlabelled columns (never auto-applied as fact).
  4. journeys  - name and narrate the code-computed customer journeys (cannot add or reorder steps).
"""
from __future__ import annotations

import time

from .. import config
from ..engine.evidence import STORE
from ..llm import prompts
from ..llm.service import ask, evidence_pack
from ..llm.verify import check_citations, check_quote
from ..store import Store
from .journeys import compute_journeys
from .model import ProjectMap


def _key(pm: ProjectMap) -> str:
    return f"enrich:{pm.sha}:{config.PROMPT_VERSION}"


# ------------------------------------------------------------------------------------------------- 1. resolve
def _helper_evidence(pm: ProjectMap, svc: str, code: str) -> list[str]:
    """Source of the files in this service that DEFINE a class used in the call (e.g. ApiRequest -> api_call.py)."""
    import re
    from .project import load_project
    project = load_project()
    names = {n for n in re.findall(r"\b([A-Z][A-Za-z0-9_]+)\s*\(", code)}
    src = pm.nodes[f"svc:{svc}"].props.get("path")
    out = []
    if not src or not names:
        return out
    for f in sorted((project.root / src).rglob("*.*")):
        if f.suffix not in (".py", ".java") or "/test" in f.as_posix():
            continue
        text = project.read(f)
        if any(re.search(rf"\bclass\s+{re.escape(nm)}\b", text) for nm in names):
            body = re.sub(r"^(#.*\n|\s*\n)+", "", text) if f.suffix == ".py" else text
            out.append(STORE.add("code", f"{svc}: helper file {f.name}", body.strip(), project.rel(f), 1,
                                 text.count("\n") + 1, pm.sha[:7]))
    return out[:3]


def resolve_calls(pm: ProjectMap, report: dict, store: Store, mode: str, model: str | None) -> list[dict]:
    results = []
    for u in report.get("unresolved", []):
        svc = u["service"]
        fn_id = f"fn:{svc}:{u.get('function')}"
        caller_ev = pm.nodes[fn_id].evidence[:1] if fn_id in pm.nodes else []
        code_line = u.get("code") or (STORE.get(u["evidence"][0]).text if u.get("evidence") else "")
        cands = u.get("candidates", [])
        cand_ev = [pm.nodes[f"fn:{c.split(':')[1]}:{pm.nodes[c].props['handler']}"].evidence[0]
                   for c in cands if c in pm.nodes and f"fn:{c.split(':')[1]}:{pm.nodes[c].props['handler']}" in pm.nodes]
        ids = [*(u.get("evidence") or []), *caller_ev, *_helper_evidence(pm, svc, code_line), *cand_ev]
        evidence, pack = evidence_pack(ids, max_chars=1200, max_blocks=8)
        options = "\n".join(f"- {c}: {pm.nodes[c].label} offered by {c.split(':')[1]}" for c in cands) or "(no internal candidates)"
        user = prompts.RESOLVE_USER.format(reason=u.get("reason", ""), evidence=evidence, options=options)
        resp, meta = ask(store, "map_resolve", prompts.RESOLVE_SYSTEM, user, prompts.resolve_schema(cands), mode, model)
        item = {"service": svc, "function": u.get("function"), "line": u.get("line"), "reason": u.get("reason"),
                "candidates": cands, "meta": meta, "verified": False, "issues": []}
        if resp:
            valid_ids, issues = check_citations(resp.get("evidence_ids", []), pack)
            quote_ok = check_quote(resp.get("quote", ""), valid_ids or list(pack), pack)
            if not quote_ok:
                issues.append("Quote not found verbatim in the evidence")
            if resp["decision"] != "NOT_INTERNAL" and resp["decision"] not in cands:
                issues.append("Decision is not one of the code-derived candidates")
            item.update(decision=resp["decision"], category=resp.get("category"), method=resp.get("method"),
                        explanation=resp.get("explanation"), quote=resp.get("quote"),
                        evidence_ids=valid_ids or list(pack)[:2], verified=quote_ok and not
                        (resp["decision"] != "NOT_INTERNAL" and resp["decision"] not in cands), issues=issues)
        results.append(item)
    return results


# ------------------------------------------------------------------------------------------------- 2. describe
def describe_services(pm: ProjectMap, store: Store, mode: str, model: str | None) -> dict:
    out = {}
    for svc in [n for n in pm.of_type("service")]:
        eps = [n for n in pm.nodes.values() if n.type == "endpoint" and n.parent == svc.id and not n.props.get("ops")]
        links = [e for e in pm.out_edges(svc.id) if e.type in ("calls_api", "reads", "writes", "trusts_tokens_from")
                 and pm.nodes[e.target].type in ("service", "database")]
        facts = ["Endpoints:"] + [f"- [{n.id}] {n.label} (handled by {n.props.get('handler')})" for n in eps]
        facts += ["Links:"] + [f"- [{e.id}] {svc.label} {e.verb} {pm.nodes[e.target].label}"
                               + (f" ({', '.join(e.details)})" if e.details else "") for e in links]
        handler_ev = []
        for n in eps:
            h = f"fn:{svc.label}:{n.props.get('handler')}"
            if h in pm.nodes:
                handler_ev.extend(pm.nodes[h].evidence[:1])
        evidence, pack = evidence_pack(handler_ev, max_chars=700, max_blocks=6)
        user = prompts.DESCRIBE_USER.format(service=svc.label, language=svc.props.get("language"),
                                            capability=svc.props.get("capability"), facts="\n".join(facts),
                                            evidence=evidence)
        resp, meta = ask(store, "map_describe", prompts.DESCRIBE_SYSTEM, user, prompts.DESCRIBE_SCHEMA, mode, model)
        if not resp:
            out[svc.id] = {"meta": meta}
            continue
        valid_eps = {n.id for n in eps}
        valid_links = {e.id for e in links}
        out[svc.id] = {
            "meta": meta, "summary": resp.get("service_summary", "").strip(),
            "endpoints": {x["id"]: x["summary"].strip() for x in resp.get("endpoints", []) if x.get("id") in valid_eps},
            "links": {x["id"]: x["business_label"].strip() for x in resp.get("links", []) if x.get("id") in valid_links},
            "evidence_ids": check_citations(resp.get("evidence_ids", []), pack)[0] or list(pack)[:3],
            "dropped": len([x for x in resp.get("endpoints", []) if x.get("id") not in valid_eps])
                       + len([x for x in resp.get("links", []) if x.get("id") not in valid_links])}
    return out


# ------------------------------------------------------------------------------------------------- 3. tables
def describe_tables(pm: ProjectMap, store: Store, mode: str, model: str | None) -> dict:
    tables = pm.of_type("table")
    facts = []
    for t in tables:
        cols = [n for n in pm.nodes.values() if n.type == "column" and n.parent == t.id]
        facts.append(f"[{t.id}] " + ", ".join(
            f"{c.label} [{c.id}]" + (f" = {c.props['classification']}" if c.props.get("classification") else " UNLABELLED")
            for c in cols))
    evidence, pack = evidence_pack([t.evidence[0] for t in tables if t.evidence])
    user = prompts.TABLES_USER.format(facts="\n".join(facts), evidence=evidence)
    resp, meta = ask(store, "map_tables", prompts.TABLES_SYSTEM, user, prompts.TABLES_SCHEMA, mode, model)
    if not resp:
        return {"meta": meta}
    valid_t = {t.id for t in tables}
    unlabelled = {n.id for n in pm.of_type("column") if not n.props.get("classification")}
    fix = lambda i, prefix: i if i in pm.nodes else f"{prefix}{i}"      # model sometimes drops the id prefix
    tbl = {fix(x.get("id", ""), "table:"): x["summary"].strip() for x in resp.get("tables", [])}
    sugg = [x | {"id": fix(x.get("id", ""), "col:")} for x in resp.get("column_suggestions", [])]
    return {"meta": meta,
            "tables": {k: v for k, v in tbl.items() if k in valid_t},
            "suggestions": [x for x in sugg if x["id"] in unlabelled],
            "evidence_ids": check_citations(resp.get("evidence_ids", []), pack)[0] or list(pack)}


# ------------------------------------------------------------------------------------------------- 4. journeys
def narrate_journeys(pm: ProjectMap, journeys: list[dict], store: Store, mode: str, model: str | None) -> dict:
    facts = []
    for j in journeys:
        facts.append(f"[{j['id']}] starts at website page {j['name']}")
        for i, s in enumerate(j["steps"], 1):
            frm, to = pm.nodes[s["from"]].label, pm.nodes[s["to"]].label
            facts.append(f"  step {i}: {frm} -> {to}: {s['detail']}" + (" (from a cache kept up to date in the background)"
                                                                          if s.get("background") else ""))
    user = prompts.JOURNEYS_USER.format(facts="\n".join(facts))
    resp, meta = ask(store, "map_journeys", prompts.JOURNEYS_SYSTEM, user, prompts.JOURNEYS_SCHEMA, mode, model)
    if not resp:
        return {"meta": meta}
    by_id = {j["id"]: j for j in journeys}
    out = {}
    for x in resp.get("journeys", []):
        jid = x.get("id", "")
        j = by_id.get(jid) or by_id.get(f"journey:{jid}")
        if j:      # step wording is used only if it matches the verified step count; names always come with it
            out[j["id"]] = {"name": x["name"].strip(), "summary": x["summary"].strip(),
                            "steps": x["steps"] if len(x.get("steps", [])) == len(j["steps"]) else None}
    return {"meta": meta, "journeys": out}


# ------------------------------------------------------------------------------------------------- run + apply
def run_enrichment(pm: ProjectMap, report: dict, store: Store, model: str | None = None, mode: str = "auto",
                   progress=lambda msg: None) -> dict:
    t0 = time.time()
    progress("Resolving calls the parser could not decide")
    resolved = resolve_calls(pm, report, store, mode, model)
    _apply_resolved(pm, resolved)
    progress("Describing services and their links")
    services = describe_services(pm, store, mode, model)
    progress("Describing tables and checking for sensitive data")
    tables = describe_tables(pm, store, mode, model)
    progress("Naming customer journeys")
    journeys = narrate_journeys(pm, compute_journeys(pm), store, mode, model)
    result = {"resolved": resolved, "services": services, "tables": tables, "journeys": journeys,
              "model": model or config.LIVE_MODEL, "seconds": round(time.time() - t0, 1)}
    store.put(_key(pm), result)
    return result


def _apply_resolved(pm: ProjectMap, resolved: list[dict]) -> None:
    for r in resolved:
        if not r.get("verified") or r.get("decision") in (None, "NOT_INTERNAL"):
            continue
        ep = pm.nodes[r["decision"]]
        src_svc, fn = f"svc:{r['service']}", f"fn:{r['service']}:{r['function']}"
        ev = r.get("evidence_ids", [])
        how = f"AI-resolved (verified quote: \"{r.get('quote')}\"): {r.get('explanation')}"
        pm.add_edge(src_svc, ep.id, "calls_api", "ai", 0.8, ep.label, ev, how=how)
        pm.add_edge(fn, ep.id, "calls_api", "ai", 0.8, ep.label, ev, how=how, line=r.get("line") or 0)
        e = pm.add_edge(src_svc, ep.parent, "calls_api", "code", 0.8, ep.label, ev)
        if e and e.origin == "code" and all(d == ep.label for d in e.details):
            e.origin = "ai"


def apply_enrichment(pm: ProjectMap, report: dict, store: Store) -> None:
    """Apply cached enrichment (if any) to a freshly built map. Never calls the model."""
    data = store.get(_key(pm))
    if data:
        _apply_resolved(pm, data.get("resolved", []))
        for sid, s in data.get("services", {}).items():
            if sid in pm.nodes and s.get("summary"):
                pm.nodes[sid].props.update(description=s["summary"], description_by="ai",
                                           description_evidence=s.get("evidence_ids", []))
                for eid, txt in s.get("endpoints", {}).items():
                    pm.nodes[eid].props.update(description=txt, description_by="ai")
                for edge_id, label in s.get("links", {}).items():
                    if edge_id in pm.edges:
                        pm.edges[edge_id].props["business_label"] = label
        for tid, txt in data.get("tables", {}).get("tables", {}).items():
            if tid in pm.nodes:
                pm.nodes[tid].props.update(description=txt, description_by="ai")
        for s in data.get("tables", {}).get("suggestions", []):
            if s["id"] in pm.nodes:
                pm.nodes[s["id"]].props.update(suggested_classification=s["classification"], suggestion_reason=s["reason"])
    journeys = compute_journeys(pm)
    names = (data or {}).get("journeys", {}).get("journeys", {})
    for j in journeys:
        if j["id"] in names:
            j.update(name=names[j["id"]]["name"], summary=names[j["id"]]["summary"], narrated_by="ai")
            for s, text in zip(j["steps"], names[j["id"]]["steps"] or []):
                s["text"] = text
    report["journeys"] = journeys
    report["enrichment"] = ({"status": "applied", "model": data.get("model"), "seconds": data.get("seconds"),
                             "resolved": [{k: r.get(k) for k in ("service", "function", "decision", "category",
                                                                   "explanation", "quote", "verified", "issues")}
                                          for r in data.get("resolved", [])]}
                            if data else {"status": "not_run"})
