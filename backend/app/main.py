"""Change Assurance Copilot API."""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .engine.evidence import STORE
from .engine.graph import describe_path, propagate
from .llm.ollama_client import health as ollama_health
from .state import STATE

app = FastAPI(title="Change Assurance Copilot", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------- health
@app.get("/api/health")
def health():
    pm = STATE.ensure_map()
    p = STATE.project
    return {"ollama": ollama_health(),
            "project": {"name": p.name, "sha": pm.sha, "short": pm.sha[:7], "pinned_label": p.pinned_label},
            "map": STATE.report.get("counts", {}), "accuracy": STATE.accuracy.get("overall", {}),
            "enrichment": STATE.report.get("enrichment", {"status": "not_run"})}


# ---------------------------------------------------------------------------- dependency map
@app.get("/api/map")
def get_map():
    pm = STATE.ensure_map()
    return pm.to_dict() | {"report": {k: v for k, v in STATE.report.items() if k != "services"},
                           "accuracy": STATE.accuracy}


@app.get("/api/map/node/{nid:path}")
def get_node(nid: str):
    pm = STATE.ensure_map()
    n = pm.nodes.get(nid)
    if not n:
        raise HTTPException(404, f"Unknown node {nid}")

    def edge_view(e, other):
        o = pm.nodes[other]
        return e.to_dict() | {"other": {"id": o.id, "label": o.label, "type": o.type, "parent": o.parent}}

    children = [c.to_dict() for c in pm.nodes.values() if c.parent == nid]
    return {"node": n.to_dict(),
            "outgoing": [edge_view(e, e.target) for e in pm.out_edges(nid)],
            "incoming": [edge_view(e, e.source) for e in pm.in_edges(nid)],
            "children": children}


@app.get("/api/map/whatif/{nid:path}")
def what_if(nid: str):
    """If this node changes, what else is affected (blast radius)?"""
    pm = STATE.ensure_map()
    if nid not in pm.nodes:
        raise HTTPException(404, f"Unknown node {nid}")
    reach = propagate(pm, {nid: 1.0})
    items = [{"id": r.node, "label": pm.nodes[r.node].label, "type": pm.nodes[r.node].type,
              "score": round(r.score, 2), "why": describe_path(pm, r.path)}
             for r in sorted(reach.values(), key=lambda r: -r.score) if r.node != nid]
    return {"source": nid, "affected": items}


@app.post("/api/map/rebuild")
def rebuild_map():
    STATE.rebuild()
    return {"ok": True, "counts": STATE.report.get("counts"), "accuracy": STATE.accuracy.get("overall")}


# ---------------------------------------------------------------------------- change requests + impact analysis
STAGE_NAMES = {1: "Understanding the request", 2: "Finding entry points", 3: "Following the dependency map",
               4: "Judging what must change", 5: "Checking data, systems, rules and tests", 6: "Writing the summary"}


def _job(key: str) -> dict | None:
    """Live job status: in-memory (API-started) or from the database (started by any process, e.g. scripts)."""
    mem = STATE.jobs.get(key)
    if mem and mem["status"] in ("running", "error"):
        return mem
    db = STATE.store.get(f"job:{key}")
    if db and db["status"] == "running" and time.time() - db.get("updated", 0) > 20 * 60:
        db = db | {"status": "error", "error": "Analysis stopped responding (process ended?)"}
    return db or mem


def _analysis(key: str) -> dict | None:
    pm = STATE.ensure_map()
    a = STATE.store.get(f"analysis:{key}:{pm.sha}")
    return apply_edits(a, STATE.store.scope_edits(key)) if a else None


def apply_edits(a: dict, edits: list[dict]) -> dict:
    pm = STATE.map
    items = {i["id"]: i for i in a["items"]}
    for ed in edits:
        human = {"user": ed["user"], "at": ed["at"], "note": ed["note"]}
        if ed["action"] == "add" and ed["node_id"] in pm.nodes:
            n = pm.nodes[ed["node_id"]]
            it = items.setdefault(n.id, {"id": n.id, "label": n.label, "type": n.type, "path": [], "why": [],
                                         "service": n.parent.split(":", 1)[1] if n.parent else None, "evidence": n.evidence[:2],
                                         "score": None, "seed": False})
            it.update(verdict=ed["verdict"] or "must_change", how=ed["note"] or "Added to scope by a reviewer", by="human", human=human)
        elif ed["node_id"] in items:
            it = items[ed["node_id"]]
            it.update(verdict="not_impacted" if ed["action"] == "remove" else ed["verdict"], by="human", human=human,
                      ai_verdict=it.get("ai_verdict", it["verdict"]))
            if ed["note"]:
                it["how"] = ed["note"]
    a = a | {"items": list(items.values()), "edits": edits}
    counts = {v: sum(1 for i in a["items"] if i["verdict"] == v) for v in ("must_change", "likely_affected", "retest_only")}
    if edits:
        a["cards"]["technical"]["line"] = (f"{counts['must_change']} must change · {counts['likely_affected']} likely affected · "
                                           f"{counts['retest_only']} re-test (edited by reviewer)")
    return a


@app.get("/api/crs")
def list_crs():
    from .engine.impact import load_issues
    pm = STATE.ensure_map()
    out = []
    for key, issue in load_issues().items():
        f = issue["fields"]
        a = STATE.store.get(f"analysis:{key}:{pm.sha}")
        out.append({"key": key, "summary": f["summary"], "priority": f["priority"]["name"], "status": f["status"]["name"],
                    "type": f["issuetype"]["name"], "labels": f.get("labels", []),
                    "components": [c["name"] for c in f.get("components", [])],
                    "assignee": (f.get("assignee") or {}).get("displayName"), "url": issue.get("url"),
                    "analysis": {"risk": a["risk"]["level"], "size": a["assessment"].get("size"),
                                 "must_change": sum(1 for i in a["items"] if i["verdict"] == "must_change"),
                                 "externals": len(a["externals"]), "controls": len(a["controls"]),
                                 "open_questions": len(a["understanding"]["open_questions"])} if a else None,
                    "job": _job(key)})
    return out


@app.get("/api/crs/{key}")
def get_cr(key: str):
    from .engine.impact import load_issues
    issues = load_issues()
    if key not in issues:
        raise HTTPException(404, f"Unknown change request {key}")
    return {"key": key, "issue": issues[key], "analysis": _analysis(key), "job": _job(key),
            "published": STATE.store.get(f"published:{key}")}


@app.post("/api/crs/{key}/analyze")
def start_analysis(key: str, force: bool = False):
    import threading
    from .engine.impact import analyze, load_issues
    if key not in load_issues():
        raise HTTPException(404, f"Unknown change request {key}")
    job = _job(key)
    if job and job["status"] == "running":
        return job
    job = STATE.jobs[key] = {"status": "running", "stage": 0, "stage_name": "Starting", "started": time.time(), "error": None}

    def progress(stage, msg):
        job.update(stage=stage, stage_name=msg, elapsed=round(time.time() - job["started"], 1))

    def run():
        try:
            analyze(STATE, key, "force" if force else "auto", None, progress)
            job.update(status="done", elapsed=round(time.time() - job["started"], 1))
        except Exception as exc:  # surface any failure to the UI
            job.update(status="error", error=str(exc)[:300])

    threading.Thread(target=run, daemon=True).start()
    return job


class ScopeEdit(BaseModel):
    node_id: str
    action: str            # add | remove | override
    verdict: str | None = None
    note: str = ""
    user: str = "Priya Nair"


@app.post("/api/crs/{key}/scope")
def edit_scope(key: str, body: ScopeEdit):
    if body.action not in ("add", "remove", "override"):
        raise HTTPException(400, "action must be add, remove or override")
    STATE.store.add_scope_edit(key, body.node_id, body.action, body.verdict, body.note, body.user)
    return _analysis(key)


@app.get("/api/nodes/search")
def search_nodes(q: str = "", limit: int = 12):
    pm = STATE.ensure_map()
    ql = q.lower()
    hits = [n for n in pm.nodes.values() if n.type in ("service", "endpoint", "table", "external", "database")
            and not n.props.get("ops") and (ql in n.label.lower() or ql in (n.parent or "").lower())]
    return [{"id": n.id, "label": n.label, "type": n.type, "parent": n.parent} for n in hits[:limit]]


class NewCR(BaseModel):
    summary: str
    description: str = ""
    acceptance_criteria: list[str] = []
    priority: str = "Medium"


@app.post("/api/crs")
def create_cr(body: NewCR):
    import json
    from .engine.impact import load_issues
    from .jira import sync as jira
    if jira.connected():                      # create it in Jira, then pull it back in
        from .jira.adf import text_to_adf
        r = jira.client().create_issue({"project": {"key": config.JIRA_JQL.split("=")[1].split()[0].strip() if "project" in config.JIRA_JQL else "BOA"},
                                        "issuetype": {"name": "Change Request"}, "summary": body.summary,
                                        "description": text_to_adf(body.description, body.acceptance_criteria, "Acceptance criteria"),
                                        "priority": {"name": body.priority}, "labels": ["created-in-copilot"]})
        jira.add_to_active_sprint([r["key"]])
        jira.sync()
        STATE.store.audit("Priya Nair", "cr_created_in_jira", r["key"], {"summary": body.summary})
        return {"key": r["key"]}
    path = config.WORKSPACE / "new_crs.json"
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    key = f"BOA-{201 + len(items)}"
    while key in load_issues():
        key = f"BOA-{int(key.split('-')[1]) + 1}"
    items.append({"key": key, "fields": {
        "issuetype": {"name": "Change Request"}, "status": {"name": "To Do"}, "priority": {"name": body.priority},
        "summary": body.summary, "description": body.description, "acceptance_criteria": body.acceptance_criteria,
        "components": [], "labels": ["created-in-copilot"], "reporter": {"displayName": "Priya Nair"},
        "assignee": {"displayName": "Unassigned"}, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}})
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    STATE.store.audit("Priya Nair", "cr_created", key, {"summary": body.summary})
    return {"key": key}


# ---------------------------------------------------------------------------- Jira connection
@app.get("/api/jira/status")
def jira_status():
    from .jira import sync as jira
    return jira.status() | {"settings": jira.settings()}


@app.post("/api/jira/sync")
def jira_sync():
    from .jira import sync as jira
    from .jira.client import JiraError
    if not jira.connected():
        raise HTTPException(400, "Jira is not configured: set JIRA_BASE_URL in .env")
    try:
        res = jira.sync()
    except JiraError as exc:
        raise HTTPException(502, str(exc)) from exc
    STATE.store.audit("Priya Nair", "jira_sync", config.JIRA_BASE_URL, res)
    return res


@app.post("/api/crs/{key}/publish")
def publish_to_jira(key: str):
    from .jira import sync as jira
    from .jira.client import JiraError
    a = _analysis(key)
    if not a:
        raise HTTPException(400, "Analyse the change request first")
    if not jira.connected():
        raise HTTPException(400, "Jira is not configured")
    try:
        jira.publish(key, a, config.APP_URL)
    except JiraError as exc:
        raise HTTPException(502, str(exc)) from exc
    STATE.store.audit("Priya Nair", "jira_comment", key, {"risk": a["risk"]["level"]})
    STATE.store.put(f"published:{key}", {"at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return {"ok": True}


@app.get("/api/eval")
def evaluation():
    from .engine.evaluate import evaluate
    from .engine.impact import load_issues
    pm = STATE.ensure_map()
    analyses = {k: STATE.store.get(f"analysis:{k}:{pm.sha}") for k in load_issues()}
    return evaluate({k: v for k, v in analyses.items() if v})


@app.get("/api/audit")
def audit():
    return STATE.store.audit_log()


# ---------------------------------------------------------------------------- evidence
@app.get("/api/evidence/{eid}")
def get_evidence(eid: str):
    e = STORE.get(eid)
    if not e:
        raise HTTPException(404, "Unknown evidence id")
    return e.to_dict() | {"location": e.location}


@app.get("/api/evidence")
def get_evidence_many(ids: str):
    return [e.to_dict() | {"location": e.location} for e in STORE.many([i for i in ids.split(",") if i])]
