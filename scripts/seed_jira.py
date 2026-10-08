"""Create the 9 demo change requests in a Jira project (real Jira Cloud or the local demo tracker).

Uses the connection in .env (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN).
Usage: backend/.venv/Scripts/python scripts/seed_jira.py --project BOA [--issuetype Task]

Notes for real Jira Cloud:
- Create a free site (atlassian.com/software/jira/free) and a project, e.g. key "BOA".
- Jira picks the issue keys (BOA-1, BOA-2, ...). The demo tracker keeps BOA-101..109 instead.
- If your project has no "Change Request" issue type, use --issuetype Task (or Story).
- Acceptance criteria are written into the description under an "Acceptance criteria" heading; the copilot's
  parser reads them back from there (or from a custom field if you set JIRA_AC_FIELD).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.jira.adf import text_to_adf  # noqa: E402
from app.jira.client import JiraClient  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="BOA")
    ap.add_argument("--issuetype", default="Task")
    args = ap.parse_args()
    if not config.JIRA_BASE_URL:
        sys.exit("Set JIRA_BASE_URL (and JIRA_EMAIL / JIRA_API_TOKEN for Jira Cloud) in .env first")
    jira = JiraClient(config.JIRA_BASE_URL, config.JIRA_EMAIL, config.JIRA_API_TOKEN)
    print("Connected as", jira.myself().get("displayName"))
    for issue in json.loads((ROOT / "demo_data" / "jira" / "issues.json").read_text(encoding="utf-8")):
        f = issue["fields"]
        fields = {"project": {"key": args.project}, "issuetype": {"name": args.issuetype}, "summary": f["summary"],
                  "description": text_to_adf(f["description"], f.get("acceptance_criteria"), "Acceptance criteria"),
                  "labels": f.get("labels", []), "priority": {"name": f["priority"]["name"]}}
        try:
            r = jira.create_issue(fields)
        except Exception as exc:          # e.g. priority field not on the screen -> retry without it
            fields.pop("priority", None)
            r = jira.create_issue(fields)
            print("  (created without priority:", str(exc)[:80], ")")
        print(f"{issue['key']} -> {r['key']}: {f['summary']}")


if __name__ == "__main__":
    main()
