"""Score impact analyses against the hand-written answer key (demo_data/ground_truth.yaml)."""
from __future__ import annotations

import yaml

from .. import config


def evaluate(analyses: dict[str, dict]) -> dict:
    truth = yaml.safe_load((config.DEMO_DATA / "ground_truth.yaml").read_text(encoding="utf-8"))
    # issues re-created in a real Jira get new keys: translate them back to the answer-key keys
    import json
    kmap = config.WORKSPACE / "jira_key_map.json"
    if kmap.exists():
        for new, old in json.loads(kmap.read_text(encoding="utf-8")).items():
            if new in analyses and old not in analyses:
                analyses = analyses | {old: analyses[new]}
    per, tot = {}, {"must_hit": 0, "must_total": 0, "aff_hit": 0, "aff_total": 0, "false_must": 0,
                    "ctrl_hit": 0, "ctrl_total": 0, "ext_hit": 0, "ext_total": 0}
    for key, t in truth.items():
        a = analyses.get(key)
        if not a:
            continue
        verdict = {i["label"]: i["verdict"] for i in a["items"]}
        must = {k for k, v in verdict.items() if v == "must_change"}
        aff = {k for k, v in verdict.items() if v in ("must_change", "likely_affected")} | {d["label"] for d in a["data"]
                                                                                            if d["verdict"] != "not_impacted"}
        ctrl = {c["id"] for c in a["controls"]}
        ext = {e["label"] for e in a["externals"]}
        r = {"must_missing": sorted(set(t.get("must", [])) - must), "affected_missing": sorted(set(t.get("affected", [])) - aff),
             "false_must": sorted(set(t.get("not", [])) & must), "controls_missing": sorted(set(t.get("controls", [])) - ctrl),
             "externals_missing": sorted(set(t.get("externals", [])) - ext),
             "open_questions_ok": (not t.get("expect_open_questions")) or bool(a["understanding"]["open_questions"])}
        per[key] = r
        tot["must_total"] += len(t.get("must", []))
        tot["must_hit"] += len(t.get("must", [])) - len(r["must_missing"])
        tot["aff_total"] += len(t.get("affected", []))
        tot["aff_hit"] += len(t.get("affected", [])) - len(r["affected_missing"])
        tot["false_must"] += len(r["false_must"])
        tot["ctrl_total"] += len(t.get("controls", []))
        tot["ctrl_hit"] += len(t.get("controls", [])) - len(r["controls_missing"])
        tot["ext_total"] += len(t.get("externals", []))
        tot["ext_hit"] += len(t.get("externals", [])) - len(r["externals_missing"])
    pct = lambda h, n: round(h / n, 2) if n else None
    return {"per_cr": per, "evaluated": len(per),
            "must_change_recall": pct(tot["must_hit"], tot["must_total"]),
            "affected_recall": pct(tot["aff_hit"], tot["aff_total"]),
            "controls_recall": pct(tot["ctrl_hit"], tot["ctrl_total"]),
            "externals_recall": pct(tot["ext_hit"], tot["ext_total"]),
            "false_must_change": tot["false_must"], "totals": tot}
