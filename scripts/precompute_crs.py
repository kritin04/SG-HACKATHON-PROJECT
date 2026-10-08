"""Run the impact analysis for every demo change request with the better (slower) local model and cache it.

Usage: backend/.venv/Scripts/python scripts/precompute_crs.py [--model qwen2.5:7b] [--only BOA-101,BOA-105] [--force]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config  # noqa: E402
from app.engine.impact import analyze, load_issues  # noqa: E402
from app.state import AppState  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.PRECOMPUTE_MODEL)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    state = AppState()
    state.ensure_map()
    keys = [k for k in load_issues() if not args.only or k in args.only.split(",")]
    for key in keys:
        t0 = time.time()
        r = analyze(state, key, "force" if args.force else "auto", args.model,
                    progress=lambda s, m: print(f"   {key} step {s}: {m}", flush=True))
        must = [i["label"] for i in r["items"] if i["verdict"] == "must_change"]
        likely = [i["label"] for i in r["items"] if i["verdict"] == "likely_affected"]
        print(f"{key} risk={r['risk']['level']} size={r['assessment'].get('size')} must={must} likely={likely} "
              f"ext={[e['label'] for e in r['externals']]} controls={[c['id'] for c in r['controls']]} "
              f"stages={ {k: v.get('status') for k, v in r['stages'].items()} } ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
