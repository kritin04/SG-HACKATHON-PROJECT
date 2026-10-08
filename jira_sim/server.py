"""Demo issue tracker with a Jira-compatible REST API (v3 subset) and a simple web board.

Why: to demo the full "Jira -> Copilot -> comment back in Jira" loop without needing a Jira Cloud account.
The copilot talks to this server exactly as it would to real Jira (same endpoints, same JSON, ADF text).
It is NOT Atlassian Jira; it only implements the handful of endpoints the copilot uses.

Run:  backend/.venv/Scripts/python -m uvicorn jira_sim.server:app --port 8090
Then: set JIRA_BASE_URL=http://localhost:8090 in .env and click "Sync from Jira" in the copilot.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "workspace" / "jira_sim.json"
SEED = ROOT / "demo_data" / "jira" / "issues.json"
PROJECT = {"key": "BOA", "name": "Bank of Anthos", "id": "10000"}
LOCK = threading.Lock()

app = FastAPI(title="Demo Tracker (Jira-compatible API)")


# ------------------------------------------------------------------------------------------------ storage
def _adf(text: str, bullets: list[str] | None = None, heading: str | None = None) -> dict:
    content = [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in text.split("\n\n") if p.strip()]
    if bullets:
        if heading:
            content.append({"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": heading}]})
        content.append({"type": "bulletList", "content": [{"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": b}]}]} for b in bullets]})
    return {"type": "doc", "version": 1, "content": content}


def load() -> dict:
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    db = {"issues": {}, "next": 110}
    for i in json.loads(SEED.read_text(encoding="utf-8")):
        f = i["fields"]
        db["issues"][i["key"]] = {
            "id": str(len(db["issues"]) + 10001), "key": i["key"], "comments": [],
            "fields": {"summary": f["summary"], "issuetype": {"name": f["issuetype"]["name"]},
                       "status": {"name": f["status"]["name"]}, "priority": {"name": f["priority"]["name"]},
                       "labels": f.get("labels", []), "components": f.get("components", []),
                       "assignee": f.get("assignee"), "reporter": f.get("reporter"), "created": f.get("created"),
                       "project": PROJECT,
                       "description": _adf(f.get("description", ""), f.get("acceptance_criteria"), "Acceptance criteria")}}
    save(db)
    return db


def save(db: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(db, indent=2), encoding="utf-8")


def _public(issue: dict, request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    f = dict(issue["fields"])
    f["comment"] = {"comments": issue["comments"], "total": len(issue["comments"])}
    return {"id": issue["id"], "key": issue["key"], "self": f"{base}/rest/api/3/issue/{issue['id']}", "fields": f}


def _match(issue: dict, jql: str) -> bool:
    f = issue["fields"]
    for field, val in re.findall(r'(\w+)\s*=\s*"?([^"\s]+(?: [^"\s]+)*?)"?(?=\s+(?:AND|ORDER|$)|$)', jql, re.I):
        field, val = field.lower(), val.strip()
        if field == "project" and f["project"]["key"].lower() != val.lower():
            return False
        if field == "key" and issue["key"].lower() != val.lower():
            return False
        if field == "status" and f["status"]["name"].lower() != val.lower():
            return False
        if field in ("issuetype", "type") and f["issuetype"]["name"].lower() != val.lower():
            return False
        if field == "labels" and val not in f.get("labels", []):
            return False
    return True


def _search(jql: str, request: Request) -> list[dict]:
    db = load()
    issues = [i for i in db["issues"].values() if _match(i, jql or "")]
    issues.sort(key=lambda i: i["fields"].get("created") or "", reverse="desc" in (jql or "").lower())
    return [_public(i, request) for i in issues]


# ------------------------------------------------------------------------------------------------ REST API (Jira v3 subset)
@app.get("/rest/api/3/myself")
def myself():
    return {"accountId": "demo-admin", "displayName": "Demo Tracker Admin", "emailAddress": "admin@demo.local"}


@app.get("/rest/api/3/project")
def projects():
    return [PROJECT]


@app.get("/rest/api/3/field")
def fields():
    return []


@app.post("/rest/api/3/search/jql")
def search_jql(request: Request, body: dict = Body(...)):
    return {"issues": _search(body.get("jql", ""), request), "isLast": True}


@app.get("/rest/api/3/search")
def search(request: Request, jql: str = ""):
    issues = _search(jql, request)
    return {"issues": issues, "total": len(issues), "startAt": 0, "maxResults": len(issues)}


@app.get("/rest/api/3/issue/{key}")
def get_issue(key: str, request: Request):
    db = load()
    if key not in db["issues"]:
        raise HTTPException(404, {"errorMessages": ["Issue does not exist"]})
    return _public(db["issues"][key], request)


@app.post("/rest/api/3/issue", status_code=201)
def create_issue(request: Request, body: dict = Body(...)):
    f = body.get("fields", {})
    if not f.get("summary"):
        raise HTTPException(400, {"errors": {"summary": "You must specify a summary of the issue."}})
    with LOCK:
        db = load()
        key = f"{PROJECT['key']}-{db['next']}"
        db["next"] += 1
        db["issues"][key] = {"id": str(10001 + len(db["issues"])), "key": key, "comments": [], "fields": {
            "summary": f["summary"], "issuetype": f.get("issuetype") or {"name": "Change Request"},
            "status": {"name": "To Do"}, "priority": f.get("priority") or {"name": "Medium"},
            "labels": f.get("labels", []), "components": f.get("components", []),
            "assignee": f.get("assignee") or {"displayName": "Unassigned"},
            "reporter": {"displayName": "Demo Tracker Admin"}, "created": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "project": PROJECT, "description": f.get("description") or _adf("")}}
        save(db)
    base = str(request.base_url).rstrip("/")
    return {"id": db["issues"][key]["id"], "key": key, "self": f"{base}/rest/api/3/issue/{key}"}


@app.get("/rest/api/3/issue/{key}/comment")
def comments(key: str):
    db = load()
    if key not in db["issues"]:
        raise HTTPException(404)
    c = db["issues"][key]["comments"]
    return {"comments": c, "total": len(c)}


@app.post("/rest/api/3/issue/{key}/comment", status_code=201)
def add_comment(key: str, body: dict = Body(...)):
    with LOCK:
        db = load()
        if key not in db["issues"]:
            raise HTTPException(404)
        c = {"id": str(int(time.time() * 1000)), "author": {"displayName": "Change Impact Copilot"},
             "body": body.get("body"), "created": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")}
        db["issues"][key]["comments"].append(c)
        save(db)
    return c


@app.post("/sim/issue/{key}/status")
def set_status(key: str, body: dict = Body(...)):
    with LOCK:
        db = load()
        db["issues"][key]["fields"]["status"] = {"name": body["status"]}
        save(db)
    return {"ok": True}


@app.post("/sim/reset")
def reset():
    if DATA.exists():
        DATA.unlink()
    load()
    return {"ok": True}


# ------------------------------------------------------------------------------------------------ web pages
PAGE = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def board():
    return PAGE


@app.get("/browse/{key}", response_class=HTMLResponse)
def browse(key: str):
    return PAGE
