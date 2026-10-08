"""Impact analysis: deterministic stages (no AI calls) + scoring of cached AI analyses against the answer key."""
import os

import pytest

from app.mapbuild.project import load_project

pytestmark = pytest.mark.skipif(not load_project().root.exists(), reason="run scripts/fetch_repo.ps1 first")


@pytest.fixture(scope="module")
def state(tmp_path_factory):
    os.environ["CAC_SEMANTIC"] = "0"
    from app import config
    config.SEMANTIC_SEARCH = False
    from app.state import AppState
    from app.store import Store
    s = AppState()
    s.store = Store(tmp_path_factory.mktemp("db") / "t.db")     # empty store -> no cached AI -> rules only
    s.ensure_map()
    return s


def _run(state, key):
    from app.engine.impact import analyze
    return analyze(state, key, mode="cache")


def test_daily_limit_reaches_ledgerwriter_and_triggers_payments_rule(state):
    a = _run(state, "BOA-101")
    ids = {i["id"] for i in a["items"]}
    assert "svc:ledgerwriter" in ids and "svc:frontend" in ids
    assert any(c["id"] == "CTRL-PAY" for c in a["controls"])
    assert all(i["by"] == "rules" for i in a["items"])          # no AI available in this test


def test_phone_number_flags_personal_data_and_outside_systems(state):
    a = _run(state, "BOA-105")
    assert any(d["label"] == "users" and any(c.startswith("Personal") for c in d["classifications"]) for d in a["data"])
    assert any(c["id"] == "CTRL-PII" for c in a["controls"])
    assert {"Customer Relationship Management (CRM)"} <= {e["label"] for e in a["externals"]}
    assert a["risk"]["level"] == "High"


def test_sms_alert_involves_new_vendor(state):
    a = _run(state, "BOA-107")
    assert "SMS / Email Provider" in {e["label"] for e in a["externals"]}
    assert any(c["id"] == "CTRL-VENDOR" for c in a["controls"])


def test_every_candidate_is_a_real_map_node_with_a_reason(state):
    pm = state.map
    for key in ("BOA-101", "BOA-103", "BOA-106"):
        for i in _run(state, key)["items"]:
            assert i["id"] in pm.nodes and (i["why"] or i["path"])


def test_cached_ai_analyses_meet_the_answer_key():
    from app.engine.evaluate import evaluate
    from app.engine.impact import load_issues
    from app.state import AppState
    s = AppState()
    pm = s.ensure_map()
    analyses = {k: s.store.get(f"analysis:{k}:{pm.sha}") for k in load_issues()}
    analyses = {k: v for k, v in analyses.items() if v and v["stages"].get("judge", {}).get("status") in ("generated", "cached")}
    if not analyses:
        pytest.skip("no AI analyses cached yet (run scripts/precompute_crs.py)")
    ev = evaluate(analyses)
    assert ev["affected_recall"] >= 0.8, ev
    assert ev["false_must_change"] <= 1, ev
