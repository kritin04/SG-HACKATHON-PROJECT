"""Turn a raw Jira issue (REST API v3) into the simple shape the impact analyzer uses.

What we read from each issue:
  key, summary, description (ADF -> text), acceptance criteria, issue type, status, priority, components,
  labels, assignee, reporter, created, resolution date.
Acceptance criteria: from a custom field if configured (JIRA_AC_FIELD, e.g. customfield_10040), otherwise
from an "Acceptance criteria" heading/bullet list inside the description (a very common team convention).
"""
from __future__ import annotations

import re

from .adf import adf_to_text

AC_HEADING = re.compile(r"(?im)^\s*(acceptance criteria|ac)\s*:?\s*$")


def split_acceptance_criteria(text: str) -> tuple[str, list[str]]:
    m = AC_HEADING.search(text)
    if not m:
        return text.strip(), []
    body, rest = text[:m.start()].strip(), text[m.end():]
    items = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l).strip() for l in rest.splitlines()]
    return body, [i for i in items if i]


def parse_issue(raw: dict, ac_field: str | None = None, base_url: str = "") -> dict:
    f = raw.get("fields", {}) or {}
    desc = adf_to_text(f.get("description"))
    ac: list[str] = []
    if ac_field and f.get(ac_field):
        ac_raw = adf_to_text(f[ac_field])
        ac = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l).strip() for l in ac_raw.splitlines() if l.strip()]
    if not ac:
        desc, ac = split_acceptance_criteria(desc)
    name = lambda x: (x or {}).get("name") if isinstance(x, dict) else x
    person = lambda x: (x or {}).get("displayName") if isinstance(x, dict) else x
    return {
        "key": raw["key"],
        "source": "jira",
        "url": f"{base_url.rstrip('/')}/browse/{raw['key']}" if base_url else None,
        "fields": {
            "issuetype": {"name": name(f.get("issuetype")) or "Task"},
            "status": {"name": name(f.get("status")) or "To Do"},
            "priority": {"name": name(f.get("priority")) or "Medium"},
            "summary": f.get("summary", ""),
            "description": desc,
            "acceptance_criteria": ac,
            "components": [{"name": name(c)} for c in f.get("components", []) or []],
            "labels": f.get("labels", []) or [],
            "assignee": {"displayName": person(f.get("assignee")) or "Unassigned"},
            "reporter": {"displayName": person(f.get("reporter")) or ""},
            "created": f.get("created"),
            "resolutiondate": f.get("resolutiondate"),
        },
    }
