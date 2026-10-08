"""Build the dependency map and run the AI enrichment once (cached), so the app never waits on CPU inference.

Usage: backend/.venv/Scripts/python scripts/build_map.py [--model qwen2.5:7b] [--force]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config  # noqa: E402
from app.mapbuild.build import build_map  # noqa: E402
from app.mapbuild.enrich import run_enrichment  # noqa: E402
from app.mapbuild.mapcheck import check_map  # noqa: E402
from app.store import Store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.PRECOMPUTE_MODEL)
    ap.add_argument("--force", action="store_true", help="ignore cached AI answers")
    args = ap.parse_args()
    t0 = time.time()
    pm, report = build_map()
    print(f"Map built: {report['counts']}  ({time.time() - t0:.1f}s)", flush=True)
    before = check_map(pm)["overall"]
    res = run_enrichment(pm, report, Store(), args.model, "force" if args.force else "auto",
                         progress=lambda m: print(f"  ... {m}", flush=True))
    for r in res["resolved"]:
        print(f"  resolve {r['service']}.{r['function']}: {r.get('decision')} [{r.get('category')}] "
              f"verified={r['verified']} {r['issues'] or ''}  ({r['meta'].get('status')} {r['meta'].get('seconds')}s)", flush=True)
    for sid, s in res["services"].items():
        print(f"  describe {sid}: {s['meta'].get('status')} {s['meta'].get('seconds')}s  "
              f"endpoints={len(s.get('endpoints', {}))} links={len(s.get('links', {}))} dropped={s.get('dropped')}", flush=True)
    print(f"  tables: {res['tables']['meta']}  suggestions={len(res['tables'].get('suggestions', []))}", flush=True)
    print(f"  journeys: {res['journeys']['meta']}  named={len(res['journeys'].get('journeys', {}))}", flush=True)
    after = check_map(pm)["overall"]
    print(f"Accuracy before AI: {before}\nAccuracy after AI:  {after}\nTotal {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
