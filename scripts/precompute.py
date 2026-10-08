"""Warm the local-AI cache for the demo scenarios so the live demo never waits on CPU inference.

Usage: backend/.venv/Scripts/python scripts/precompute.py [--model qwen2.5:7b] [--only impact,review,docs]
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.engine.core import Engine  # noqa: E402
from app.engine.docdrift import required_tokens, rule_based_draft, scan_completed_work  # noqa: E402
from app.engine.impact import analyze  # noqa: E402
from app.engine.reconcile import reconcile  # noqa: E402
from app.llm.service import LLMService  # noqa: E402
from app.store import Store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.PRECOMPUTE_MODEL)
    ap.add_argument("--only", default="docs,impact,review")
    args = ap.parse_args()
    only = set(args.only.split(","))
    engine, store = Engine(), Store()
    llm = LLMService(store)
    names = {d["label"] for _, d in engine.graph().nodes(data=True)}

    def run(label, fn):
        t = time.time()
        out = fn()
        ok = out.get("verified", out.get("verified_count"))
        print(f"{label:<45} {out.get('status'):<11} {time.time() - t:6.1f}s  verified={ok}", flush=True)
        return out

    if "docs" in only:
        for f in scan_completed_work(engine):
            draft = rule_based_draft(f)
            rm, ad = required_tokens(f)
            run(f"doc_fix {f['id']} {f['detector']}", lambda: llm.doc_fix(f, draft, rm, ad, mode="force", model=args.model))
    if "impact" in only:
        for key, issue in engine.jira.items():
            if issue["fields"]["issuetype"]["name"] == "Change Request":
                rep = analyze(engine, key)
                run(f"impact_brief {key}", lambda: llm.impact_brief(rep, names, mode="force", model=args.model))
    if "review" in only:
        for n, pr in engine.prs.items():
            if pr["state"] == "open":
                rec = reconcile(engine, n, store.baseline(pr["jira_key"]))
                run(f"review_brief PR #{n}", lambda: llm.review_brief(rec, mode="force", model=args.model))


if __name__ == "__main__":
    main()
