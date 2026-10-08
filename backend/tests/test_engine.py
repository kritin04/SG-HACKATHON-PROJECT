from app.engine.docdrift import (_merge_into_changed_section, required_tokens, rule_based_draft,
                                 scan_completed_work)
from app.engine.impact import analyze
from app.engine.reconcile import reconcile


def test_indexer_detects_wiring(engine):
    ix = engine.index("main")
    routes = ix.routes()
    assert "POST /transfers" in routes and "GET /fees/quote" in routes and "POST /entries" in routes
    assert "MAX_DAILY_LIMIT" in ix.config_keys()
    rec = ix.symbols["sym:ledger_service.ledger.record_entry"]
    assert "ledger_entries" in rec.tables_written and "ledger.entry.posted" in rec.topics_pub
    assert ix.config_default("MAX_DAILY_LIMIT") == "200000"
    assert any("calculate_fee" in d.names for d in ix.docs.values())
    G = engine.graph("main")
    assert G.has_edge("sym:payments_service.transfers.create_transfer", "route:POST /entries")  # cross-service http


def test_impact_pay142_matches_ground_truth(engine, truth):
    t = truth["impact"]["PAY-142"]
    r = analyze(engine, "PAY-142")
    mods = {i["label"] for i in r["code"]}
    recall = len(set(t["modules"]) & mods) / len(t["modules"])
    assert recall >= 0.8, mods
    assert set(t["external_systems"]) <= {e["id"].split(":", 1)[1] for e in r["external"]}
    assert set(t["tables"]) <= {d["label"] for d in r["data"] if d["kind"] == "table"}
    ctrl = {c["id"] for c in r["controls"]}
    assert set(t["controls"]) <= ctrl and not (set(t["not_controls"]) & ctrl)
    assert set(t["tests_to_run"]) <= {x["label"] for x in r["tests"]["to_run"]}
    assert set(t["test_gap_modules"]) <= {g["label"] for g in r["tests"]["gaps"]}
    assert set(t["docs"]) <= {d["label"] for d in r["docs"]}
    assert r["risk"]["level"] == "High"
    for item in r["code"]:
        assert item["evidence"], f"{item['label']} has no evidence"


def test_impact_pay150_is_low_risk(engine, truth):
    r = analyze(engine, "PAY-150")
    assert r["risk"]["level"] == truth["impact"]["PAY-150"]["risk"]
    assert {i["label"] for i in r["code"]} >= set(truth["impact"]["PAY-150"]["modules"])


def test_reconcile_pr57(engine, truth):
    t = truth["reconcile"]["57"]
    r = reconcile(engine, 57)
    assert {s["label"] for s in r["code"]["surprise"]} == set(t["surprise_modules"])
    assert {m["label"] for m in r["code"]["missed"] if m["severity"] == "likely_miss"} == set(t["likely_missed_modules"])
    gaps = {c["id"] for c in r["controls"] if not c["satisfied"]}
    assert gaps == set(t["controls_with_gaps"])
    assert r["verdict"]["ready"] is False
    assert any(d["label"] == "customer_profile" and "PII" in d["classifications"] for d in r["data"])


def test_docdrift_finds_seeded_problems_without_false_positives(engine, truth):
    fs = scan_completed_work(engine)
    stale = {(f["doc_path"], f["token"]) for f in fs if f["kind"] == "stale"}
    missing = {f["token"] for f in fs if f["kind"] == "missing"}
    for s in truth["docs"]["stale"]:
        assert (s["doc"], s["token"]) in stale
    assert {m["name"] for m in truth["docs"]["missing"]} <= missing
    assert not {f["doc_path"] for f in fs} & set(truth["docs"]["clean_docs"])
    assert len(fs) == len(truth["docs"]["stale"]) + len(truth["docs"]["missing"])


def test_rule_drafts_fix_the_problem(engine):
    from app.llm.verify import verify_doc_fix
    for f in scan_completed_work(engine):
        draft = rule_based_draft(f)
        rm, ad = required_tokens(f)
        assert verify_doc_fix(f["section_text"], draft, rm, ad) == [], f["id"]


def test_merge_second_fix_into_already_edited_section():
    doc = "# Config\n\n## Keys\n\n| Key | Default |\n|---|---|\n| `A` | 1 |\n\n## Other\n\ntext\n"
    old = "## Keys\n\n| Key | Default |\n|---|---|\n| `A` | 1 |"
    first = doc.replace(old, old + "\n| `B` | 2 |")
    merged = _merge_into_changed_section(first, old, old + "\n| `C` | 3 |")
    assert "| `B` | 2 |" in merged and "| `C` | 3 |" in merged and merged.index("`C`") < merged.index("## Other")
