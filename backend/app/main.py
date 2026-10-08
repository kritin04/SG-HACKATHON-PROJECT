"""Change Assurance Copilot API."""
from __future__ import annotations

import difflib
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .engine.core import Engine
from .engine.docdrift import apply_fix, required_tokens, rule_based_draft, scan_completed_work
from .engine.evidence import STORE
from .engine.impact import analyze
from .engine.reconcile import reconcile
from .llm.ollama_client import health as ollama_health
from .llm.service import LLMService
from .store import Store

app = FastAPI(title="Change Assurance Copilot", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

engine = Engine()
store = Store()
llm = LLMService(store)
_cache: dict[tuple, dict] = {}
_lock = threading.Lock()


def _cached(key: tuple, fn):
    with _lock:
        if key not in _cache:
            _cache[key] = fn()
        return _cache[key]


def _known_names() -> set[str]:
    return {d["label"] for _, d in engine.graph().nodes(data=True)}


def _impact(key: str) -> dict:
    if key not in engine.jira:
        raise HTTPException(404, f"Unknown change request {key}")
    return _cached(("impact", key, engine.repo.rev(config.MAIN_REF)), lambda: analyze(engine, key))


def _findings() -> list[dict]:
    return _cached(("docs", engine.repo.rev(config.MAIN_REF)), lambda: scan_completed_work(engine))


def _diff(old: str, new: str) -> list[dict]:
    out = []
    for line in difflib.ndiff(old.split("\n"), new.split("\n")):
        tag = line[:2]
        if tag == "? ":
            continue
        out.append({"type": {"  ": "same", "- ": "del", "+ ": "add"}[tag], "text": line[2:]})
    return out


# ---------------------------------------------------------------------------- health
@app.get("/api/health")
def health():
    main = engine.repo.commit_info(config.MAIN_REF)
    cat = engine.catalog
    return {"ollama": ollama_health(), "repo": {"path": str(engine.repo.path), "main": main},
            "catalog": {"systems": len(cat.systems), "external_systems": len(cat.external_systems),
                        "controls": len(cat.controls), "terms": len(cat.terms), "classified_columns": len(cat.columns)},
            "graph": {"nodes": engine.graph().number_of_nodes(), "edges": engine.graph().number_of_edges()}}


# ---------------------------------------------------------------------------- change requests
@app.get("/api/crs")
def list_crs():
    out = []
    for key, issue in engine.jira.items():
        f = issue["fields"]
        out.append({"key": key, "summary": f["summary"], "type": f["issuetype"]["name"], "status": f["status"]["name"],
                    "priority": f["priority"]["name"], "components": [c["name"] for c in f.get("components", [])],
                    "linked_prs": f.get("linked_prs", []), "baseline": bool(store.baseline(key))})
    out.sort(key=lambda x: (x["type"] != "Change Request", x["key"]))
    return out


@app.get("/api/crs/{key}/impact")
def get_impact(key: str):
    report = _impact(key)
    return report | {"ai": llm.impact_brief(report, _known_names(), mode="cache"), "baseline": store.baseline(key)}


@app.post("/api/crs/{key}/ai")
def run_impact_ai(key: str, force: bool = False):
    return llm.impact_brief(_impact(key), _known_names(), mode="force" if force else "auto")


class BaselineIn(BaseModel):
    included: list[str]
    excluded: list[str] = []
    added: list[str] = []
    user: str = "priya.nair"


@app.post("/api/crs/{key}/baseline")
def confirm_baseline(key: str, body: BaselineIn):
    report = _impact(key)
    return store.save_baseline(key, report["ref"], report["sha"], body.included, body.excluded, body.added, report, body.user)


@app.get("/api/crs/{key}/baseline")
def get_baseline(key: str):
    return store.baseline(key)


# ---------------------------------------------------------------------------- pull requests
@app.get("/api/prs")
def list_prs():
    out = []
    for n, pr in engine.prs.items():
        out.append({"number": n, "title": pr["title"], "state": pr["state"], "jira_key": pr.get("jira_key"),
                    "author": pr["user"]["login"], "baseline": bool(store.baseline(pr.get("jira_key", "")))})
    out.sort(key=lambda x: (x["state"] != "open", -x["number"]))
    return out


def _reconcile(n: int) -> dict:
    if n not in engine.prs:
        raise HTTPException(404, f"Unknown PR {n}")
    baseline = store.baseline(engine.prs[n].get("jira_key", ""))
    stamp = baseline["confirmed_at"] if baseline else "none"
    return _cached(("reconcile", n, stamp, engine.repo.rev(engine.prs[n]["head"]["rev"])),
                   lambda: reconcile(engine, n, baseline))


@app.get("/api/prs/{n}/reconcile")
def get_reconcile(n: int):
    rec = _reconcile(n)
    return rec | {"ai": llm.review_brief(rec, mode="cache")}


@app.post("/api/prs/{n}/ai")
def run_review_ai(n: int, force: bool = False):
    return llm.review_brief(_reconcile(n), mode="force" if force else "auto")


# ---------------------------------------------------------------------------- self-healing docs
def _finding(fid: str) -> dict:
    f = next((x for x in _findings() if x["id"] == fid), None)
    if not f:
        raise HTTPException(404, f"Unknown finding {fid}")
    return f


def _finding_view(f: dict, decisions: dict) -> dict:
    draft = rule_based_draft(f)
    rm, ad = required_tokens(f)
    ai = llm.doc_fix(f, draft, rm, ad, mode="cache")
    proposed = ai["updated_section"] if ai.get("updated_section") and ai.get("verified") else draft
    d = decisions.get(f["id"])
    return f | {"rule_draft": draft, "ai": ai, "proposed": proposed,
                "proposed_source": "ai" if proposed is not draft else "rules",
                "diff": _diff(f["section_text"], proposed), "status": d["action"] if d else "open", "decision": d}


@app.get("/api/docs/findings")
def list_findings():
    decisions = store.decisions()
    return [_finding_view(f, decisions) for f in _findings()]


@app.get("/api/docs/stats")
def doc_stats():
    decisions = store.decisions()
    fs = _findings()
    sections = [d for d in engine.index().docs.values() if d.level > 1]
    open_ = [f for f in fs if f["id"] not in decisions]
    affected_open = {f["section_id"] for f in open_}
    return {"sections": len(sections), "documents": len({d.path for d in sections}),
            "affected_sections": len(affected_open),
            "health": round(100 * (1 - len(affected_open) / len(sections))) if sections else 100,
            "health_before": round(100 * (1 - len({f["section_id"] for f in fs}) / len(sections))) if sections else 100,
            "open": len(open_), "stale": sum(f["kind"] == "stale" for f in open_), "missing": sum(f["kind"] == "missing" for f in open_),
            "approved": sum(d["action"] == "approved" for d in decisions.values()),
            "rejected": sum(d["action"] == "rejected" for d in decisions.values()),
            "stories_without_doc_updates": sorted({f["story"] for f in fs if not f.get("docs_touched_in_pr")})}


@app.post("/api/docs/findings/{fid}/ai")
def run_doc_ai(fid: str, force: bool = False):
    f = _finding(fid)
    draft = rule_based_draft(f)
    rm, ad = required_tokens(f)
    llm.doc_fix(f, draft, rm, ad, mode="force" if force else "auto")
    return _finding_view(f, store.decisions())


class DecisionIn(BaseModel):
    action: str  # approve | reject
    text: str | None = None
    reason: str | None = None
    user: str = "priya.nair"


@app.post("/api/docs/findings/{fid}/decision")
def decide(fid: str, body: DecisionIn):
    f = _finding(fid)
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    commit = None
    if body.action == "approve":
        text = body.text or _finding_view(f, {})["proposed"]
        try:
            commit = apply_fix(engine, f, text, body.user)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        store.save_decision(fid, "approved", text, body.reason, body.user, commit)
    else:
        store.save_decision(fid, "rejected", None, body.reason, body.user, None)
    return _finding_view(f, store.decisions())


# ---------------------------------------------------------------------------- evidence & audit
@app.get("/api/evidence/{eid}")
def get_evidence(eid: str):
    e = STORE.get(eid)
    if not e:
        raise HTTPException(404, "Unknown evidence id")
    return e.to_dict() | {"location": e.location}


@app.get("/api/evidence")
def get_evidence_many(ids: str):
    return [e.to_dict() | {"location": e.location} for e in STORE.many(ids.split(","))]


@app.get("/api/audit")
def audit():
    return store.audit_log()


@app.post("/api/admin/refresh")
def refresh():
    engine.refresh()
    _cache.clear()
    return {"ok": True}
