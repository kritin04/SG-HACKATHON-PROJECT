"""Sync from Jira, then reuse existing analyses for issues that Jira gave new keys (matched by title).

Why: the demo analyses were computed for BOA-101..109. When the same change requests are created in a real Jira,
Jira numbers them itself (e.g. BOA-5..13). This copies each analysis to its new key so nothing is re-analysed.
Also writes workspace/jira_key_map.json so accuracy scoring still finds the answer key.

Usage: backend/.venv/Scripts/python scripts/link_jira_keys.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.jira import sync as jira  # noqa: E402
from app.mapbuild.project import load_project  # noqa: E402
from app.store import Store  # noqa: E402


def main():
    res = jira.sync()
    print(f"Synced {res['count']} issue(s) from {config.JIRA_BASE_URL}")
    demo = {i["fields"]["summary"].strip().lower(): i["key"]
            for i in json.loads((ROOT / "demo_data" / "jira" / "issues.json").read_text(encoding="utf-8"))}
    store, sha = Store(), load_project().sha
    mapping = {}
    for issue in jira.cached_issues():
        old = demo.get(issue["fields"]["summary"].strip().lower())
        if not old or old == issue["key"]:
            continue
        mapping[issue["key"]] = old
        a = store.get(f"analysis:{old}:{sha}")
        if a:
            a = a | {"key": issue["key"], "cr": a["cr"] | {"key": issue["key"]}, "linked_from": old}
            store.put(f"analysis:{issue['key']}:{sha}", a)
            store.put(f"job:{issue['key']}", {"status": "done", "stage": 6, "stage_name": "Done"})
        print(f"  {issue['key']} <- {old}  ({'analysis copied' if a else 'no analysis yet'})")
    (config.WORKSPACE / "jira_key_map.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
