"""Measure the map's accuracy against the hand-checked answer key (demo_data/map_truth.yaml)."""
from __future__ import annotations

from pathlib import Path

import yaml

from .. import config
from .model import ProjectMap


def _score(expected: set, found: set) -> dict:
    hit = expected & found
    return {"expected": len(expected), "found": len(hit), "missing": sorted(expected - found),
            "extra": sorted(found - expected),
            "recall": round(len(hit) / len(expected), 3) if expected else 1.0,
            "precision": round(len(hit) / len(found), 3) if found else 1.0}


def check_map(pm: ProjectMap, truth_path: Path | None = None) -> dict:
    t = yaml.safe_load(Path(truth_path or config.DEMO_DATA / "map_truth.yaml").read_text(encoding="utf-8"))
    E = pm.edges.values()
    res = {
        "services": _score(set(t["services"]), {n.label for n in pm.of_type("service")}),
        "databases": _score(set(t["databases"]), {n.label for n in pm.of_type("database")}),
        "tables": _score({f"{db}.{tb}" for db, tbs in t["tables"].items() for tb in tbs},
                         {n.id.removeprefix("table:") for n in pm.of_type("table")}),
        "api_calls": _score({(c["from"], c["to"]) for c in t["api_calls"]},
                            {(e.source.removeprefix("svc:"), e.target) for e in E
                             if e.type == "calls_api" and e.source.startswith("svc:") and e.target.startswith("ep:")}),
        "data_access": _score(
            {(d["service"], d["table"], m) for d in t["data_access"]
             for m in (("read", "write") if d["mode"] == "read_write" else (d["mode"],))},
            {(e.source.removeprefix("svc:"), e.target.removeprefix("table:"), e.type.rstrip("s")) for e in E
             if e.type in ("reads", "writes") and e.source.startswith("svc:") and e.target.startswith("table:")}),
        "token_trust": _score({(v, t["token_issuer"]) for v in t["token_verifiers"]},
                              {(e.source.removeprefix("svc:"), e.target.removeprefix("svc:")) for e in E
                               if e.type == "trusts_tokens_from"}),
        "endpoints": _score({f"{s}:{ep}" for s, eps in t["endpoints"].items() for ep in eps},
                            {f"{n.parent.removeprefix('svc:')}:{n.label}" for n in pm.of_type("endpoint")
                             if not n.props.get("ops")}),
    }
    exp = sum(v["expected"] for v in res.values())
    hit = sum(v["found"] for v in res.values())
    res["overall"] = {"expected": exp, "found": hit, "recall": round(hit / exp, 3) if exp else 1.0,
                      "precision": round(hit / max(1, hit + sum(len(v["extra"]) for v in res.values())), 3)}
    return res
