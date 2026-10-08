"""Pull change requests from Jira into the copilot, and post impact summaries back as Jira comments.

Settings (in the project's .env file or environment variables):
  JIRA_BASE_URL   e.g. https://your-site.atlassian.net   or  http://localhost:8090 (local demo tracker)
  JIRA_EMAIL      Atlassian account e-mail (Jira Cloud only)
  JIRA_API_TOKEN  API token (Jira Cloud only)
  JIRA_JQL        which issues to pull (default: project = BOA ORDER BY created DESC)
  JIRA_AC_FIELD   optional custom field id holding acceptance criteria (e.g. customfield_10040)
"""
from __future__ import annotations

import json
import time

from .. import config
from .adf import text_to_adf
from .client import JiraClient
from .parse import parse_issue

CACHE = config.WORKSPACE / "jira_issues.json"


def settings() -> dict:
    return {"base_url": config.JIRA_BASE_URL, "email": config.JIRA_EMAIL, "has_token": bool(config.JIRA_API_TOKEN),
            "jql": config.JIRA_JQL, "ac_field": config.JIRA_AC_FIELD}


def connected() -> bool:
    return bool(config.JIRA_BASE_URL)


def client() -> JiraClient:
    return JiraClient(config.JIRA_BASE_URL, config.JIRA_EMAIL, config.JIRA_API_TOKEN)


def status() -> dict:
    if not connected():
        return {"connected": False, "source": "demo files (demo_data/jira/issues.json)"}
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None
    out = {"connected": True, "base_url": config.JIRA_BASE_URL, "jql": config.JIRA_JQL,
           "last_sync": cache.get("synced_at") if cache else None, "issues": len(cache["issues"]) if cache else 0}
    try:
        me = client().myself()
        out["user"] = me.get("displayName") or me.get("emailAddress")
        out["reachable"] = True
    except Exception as exc:  # show why in the UI
        out.update(reachable=False, error=str(exc)[:200])
    return out


def sync() -> dict:
    raw = client().search(config.JIRA_JQL)
    issues = [parse_issue(r, config.JIRA_AC_FIELD, config.JIRA_BASE_URL) for r in raw]
    data = {"synced_at": time.strftime("%Y-%m-%d %H:%M:%S"), "base_url": config.JIRA_BASE_URL, "jql": config.JIRA_JQL,
            "issues": issues}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"count": len(issues), "synced_at": data["synced_at"], "keys": [i["key"] for i in issues]}


def cached_issues() -> list[dict] | None:
    if not connected() or not CACHE.exists():
        return None
    return json.loads(CACHE.read_text(encoding="utf-8"))["issues"]


def publish(key: str, a: dict, app_url: str = "http://localhost:5173") -> dict:
    """Post a short impact summary as a comment on the Jira issue."""
    must = [i["label"] for i in a["items"] if i["verdict"] == "must_change"]
    likely = [i["label"] for i in a["items"] if i["verdict"] == "likely_affected"]
    bullets = [f"Risk: {a['risk']['level']}" + (f" · Size {a['assessment']['size']}" if a["assessment"].get("size") else ""),
               "Must change: " + (", ".join(must) or "none"),
               "Likely affected: " + (", ".join(likely) or "none"),
               "Outside systems: " + (", ".join(e["label"] for e in a["externals"]) or "none"),
               "Approvals needed: " + (", ".join(f"{c['id']} {c['name']}" for c in a["controls"]) or "none"),
               f"Tests: {sum(t['count'] for t in a['tests']['to_run'])} existing to re-run, {len(a['tests']['gaps'])} gap(s)"]
    bullets += [f"Open question: {q}" for q in a["understanding"]["open_questions"]]
    bullets.append(f"Full analysis with evidence: {app_url}/cr/{key}")
    body = text_to_adf(f"Impact analysis by Change Impact Copilot (local AI, verified against the code).\n\n"
                       f"{a['assessment']['summary']}", bullets, "Summary")
    return client().add_comment(key, body)
