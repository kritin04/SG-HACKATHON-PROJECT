"""Put the app (and Jira) into the "start of demo video" state. Safe to run before every rehearsal / take.

What it does:
  1. Syncs the change requests from Jira.
  2. Removes reviewer edits and "posted to Jira" markers from earlier rehearsals.
  3. Deletes the copilot's comments from the Jira tickets (so the live "Post summary to Jira" is the only one).
  4. Puts the hero ticket(s) back in "To analyse". The AI answers stay cached, so clicking
     "Analyse impact" on camera runs the real pipeline in seconds instead of minutes.

Usage: backend/.venv/Scripts/python scripts/reset_demo.py [--fresh BOA-9]
       (run while the backend is stopped OR running - then refresh the browser)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.jira import sync as jira  # noqa: E402
from app.mapbuild.project import load_project  # noqa: E402
from app.store import Store  # noqa: E402

MARKER = "Impact analysis by Change Impact Copilot"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", default="BOA-9", help="comma-separated tickets to show as 'To analyse'")
    args = ap.parse_args()
    store, sha = Store(), load_project().sha
    fresh = [k.strip() for k in args.fresh.split(",") if k.strip()]

    if jira.connected():
        res = jira.sync()
        print(f"1. Synced {res['count']} change request(s) from Jira")
    else:
        print("1. Jira not configured - using demo files")

    store._exec("DELETE FROM scope_edits")
    store.delete_prefix("published:")
    print("2. Cleared reviewer edits and 'posted to Jira' markers")

    if jira.connected():
        c, removed = jira.client(), 0
        for issue in jira.cached_issues():
            for com in c._req("GET", f"/rest/api/3/issue/{issue['key']}/comment").get("comments", []):
                if MARKER in str(com.get("body")):
                    c._req("DELETE", f"/rest/api/3/issue/{issue['key']}/comment/{com['id']}")
                    removed += 1
        print(f"3. Removed {removed} copilot comment(s) from Jira")

    # check the AI answers are cached for the fresh tickets (so the on-camera run is fast), then hide the result
    from app.engine.impact import analyze
    from app.state import AppState
    state = AppState()
    state.ensure_map()
    for key in fresh:
        a = analyze(state, key, mode="cache")
        ai = {k: v.get("status") for k, v in a["stages"].items() if k in ("understand", "judge", "assess")}
        ok = all(s == "cached" for s in ai.values())
        store.delete_prefix(f"analysis:{key}:")
        store.delete_prefix(f"job:{key}")
        print(f"4. {key} is back in 'To analyse' - AI answers cached: {'yes, on-camera run takes seconds' if ok else 'NO ' + str(ai) + ' (run will take minutes)'}")
    print("\nReady. Refresh the browser tabs (copilot + Jira).")


if __name__ == "__main__":
    main()
