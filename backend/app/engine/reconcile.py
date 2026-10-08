"""PR Reconciliation: compare the confirmed impact baseline with what the pull request actually changed."""
from __future__ import annotations

import fnmatch
from collections import defaultdict

from .controls import evaluate_controls
from .core import Engine
from .docdrift import detect_changes
from .evidence import STORE
from .gitrepo import hunks_for_lines
from .impact import analyze


def actual_changes(engine: Engine, base: str, head: str) -> dict:
    repo = engine.repo
    ix_b, ix_h = engine.index(base), engine.index(head)
    head_short = repo.rev(head)[:7]
    diffs = repo.diff(base, head)
    changed_syms: dict[str, dict] = {}
    files = {"code": [], "tests": [], "docs": [], "migrations": [], "other": []}
    modules: dict[str, dict] = {}

    for fd in diffs:
        p = fd.path
        bucket = ("tests" if p.startswith("tests/") else "docs" if p.startswith("docs/")
                  else "migrations" if p.endswith(".sql") else "code" if p.endswith(".py") else "other")
        ev = STORE.add("diff", f"Diff {p}", fd.patch, p, ref=head_short)
        files[bucket].append({"path": p, "status": fd.status, "evidence": ev,
                              "added": len(fd.added_lines), "removed": len(fd.removed_lines)})
        if bucket != "code":
            continue
        mid = "mod:" + p[:-3].replace("/", ".").removesuffix(".__init__")
        modules[mid] = {"id": mid, "path": p, "evidence": [ev], "symbols": []}
        for s in ix_h.symbols_in_lines(p, fd.added_lines):
            change = "added" if s.id not in ix_b.symbols else "modified"
            sev = STORE.add("diff", f"{s.module}.{s.qualname} ({change})", hunks_for_lines(fd.patch, s.start, s.end),
                            p, s.start, s.end, head_short)
            changed_syms[s.id] = {"sym": s, "change": change, "evidence": sev}
        for s in ix_b.symbols_in_lines(fd.old_path or p, fd.removed_lines):
            if s.id in changed_syms:
                continue
            if s.id in ix_h.symbols:
                hs = ix_h.symbols[s.id]
                sev = STORE.add("diff", f"{s.module}.{s.qualname} (modified)", hunks_for_lines(fd.patch, s.start, s.end, "old"),
                                p, hs.start, hs.end, head_short)
                changed_syms[s.id] = {"sym": hs, "change": "modified", "evidence": sev}
            else:
                sev = STORE.add("diff", f"{s.module}.{s.qualname} (removed)", hunks_for_lines(fd.patch, s.start, s.end, "old"),
                                p, s.start, s.end, head_short)
                changed_syms[s.id] = {"sym": s, "change": "removed", "evidence": sev}
    for sid, c in changed_syms.items():
        mid = f"mod:{c['sym'].module}"
        if mid in modules:
            modules[mid]["symbols"].append({"id": sid, "label": f"{c['sym'].module}.{c['sym'].qualname}",
                                            "change": c["change"], "evidence": c["evidence"]})
            modules[mid]["evidence"].append(c["evidence"])
    return {"files": files, "modules": modules, "symbols": changed_syms, "ix_b": ix_b, "ix_h": ix_h}


def reconcile(engine: Engine, number: int, baseline: dict | None = None) -> dict:
    pr = engine.prs[number]
    base, head = pr["base"]["rev"], pr["head"]["rev"]
    key = pr["jira_key"]
    cat = engine.catalog
    G_h = engine.graph(head)
    pr_ev = engine.pr_evidence(number)

    if baseline:
        report = baseline["report"]
        included = set(baseline["included"]) | set(baseline.get("added", []))
        source = "baseline"
    else:
        report = analyze(engine, key, base)
        included = {i["id"] for grp in ("code", "data", "external") for i in report[grp]}
        source = "prediction"
    predicted_code = {i["id"]: i for i in report["code"] if i["id"] in included}
    for extra in baseline.get("added", []) if baseline else []:
        if extra.startswith("mod:") and extra not in predicted_code:
            predicted_code[extra] = {"id": extra, "label": extra[4:], "score": 1.0, "path": None, "evidence": []}
    predicted_data = {i["id"]: i for i in report["data"] if i["id"] in included}

    act = actual_changes(engine, base, head)
    ix_h = act["ix_h"]

    def system_of(mid):
        return G_h.nodes[mid].get("system") if mid in G_h else None

    # ---- actual data / classes / external --------------------------------
    touched_tables, written_tables, cols = set(), set(), defaultdict(set)  # cols: module -> columns
    for sid, c in act["symbols"].items():
        s = c["sym"]
        touched_tables |= s.tables_read | s.tables_written
        written_tables |= s.tables_written
        cols[f"mod:{s.module}"] |= s.columns
    for f in act["files"]["migrations"]:
        sf = ix_h.sql_files.get(f"file:{f['path']}")
        if sf:
            touched_tables |= sf.tables_written
            written_tables |= sf.tables_written
            cols["migrations"] |= sf.columns
    all_cols = set().union(*cols.values()) if cols else set()
    classes = cat.classes_for_columns(all_cols)
    data_classes: dict[str, list[str]] = defaultdict(list)
    for col, cls in classes.items():
        data_classes[cls].append(col)

    consumed_targets = {f"mod:{m[4:]}" for m in act["modules"]} | {f"table:{t}" for t in written_tables}
    consumed_targets |= {f"topic:{t}" for c in act["symbols"].values() for t in c["sym"].topics_pub}
    externals = {}
    for x in cat.external_systems:
        hit = sorted(set(x.consumes) & consumed_targets)
        if hit:
            externals[x.id] = {"id": f"ext:{x.id}", "label": x.name, "via": hit,
                               "evidence": [cat.evidence.get(f"ext:{x.id}")]}

    # ---- compare code -------------------------------------------------------
    actual_mods = {m: v for m, v in act["modules"].items() if system_of(m) != "platform"}
    supporting = [v | {"label": m[4:]} for m, v in act["modules"].items() if system_of(m) == "platform"]
    confirmed, surprises, missed = [], [], []
    for mid, v in actual_mods.items():
        entry = {"id": mid, "label": mid[4:], "path": v["path"], "system": system_of(mid),
                 "symbols": v["symbols"], "evidence": list(dict.fromkeys(v["evidence"]))}
        if mid in predicted_code:
            confirmed.append(entry | {"predicted_score": predicted_code[mid].get("score")})
        else:
            mcols = cat.classes_for_columns(cols.get(mid, set()))
            reasons, severity = [], "medium"
            if mcols:
                reasons += [f"Touches {cls} column {col}" for col, cls in sorted(mcols.items())]
                severity = "high" if "PII" in mcols.values() else severity
            reasons.append("Not in the confirmed impact baseline")
            surprises.append(entry | {"severity": severity, "reasons": reasons,
                                      "evidence": entry["evidence"] + [cat.evidence.get(f"column:{c}") for c in mcols]})
    for mid, item in predicted_code.items():
        if mid in actual_mods:
            continue
        mod_tables = {f"table:{t}" for sid in G_h.successors(mid) if sid in ix_h.symbols
                      for t in (ix_h.symbols[sid].tables_read | ix_h.symbols[sid].tables_written)} if mid in G_h else set()
        ext_linked = [x.name for x in cat.external_systems if mid in x.consumes or mod_tables & set(x.consumes)]
        likely = bool(ext_linked) and item.get("score", 0) >= 0.5
        reasons = []
        if ext_linked:
            reasons.append(f"Feeds downstream {', '.join(ext_linked)}")
        if item.get("seed", {}).get("reason"):
            reasons.append(f"Predicted because: {item['seed']['reason']}")
        missed.append({"id": mid, "label": item["label"], "path": item.get("path"), "score": item.get("score"),
                       "severity": "likely_miss" if likely else "review", "reasons": reasons,
                       "evidence": item.get("evidence", [])[:4]})
    missed.sort(key=lambda m: (m["severity"] != "likely_miss", -(m["score"] or 0)))

    # ---- data comparison -----------------------------------------------------
    predicted_tables = {d["label"] for d in predicted_data.values() if d["kind"] == "table"}
    data_rows = []
    for t in sorted(touched_tables | predicted_tables):
        tcols = sorted(c for c in all_cols if c.startswith(t + "."))
        tclasses = sorted(set(cat.classes_for_columns(tcols).values()))
        status = "confirmed" if t in touched_tables and t in predicted_tables else "surprise" if t in touched_tables else "missed"
        data_rows.append({"id": f"table:{t}", "label": t, "status": status, "columns": tcols, "classifications": tclasses,
                          "written": t in written_tables})

    # ---- tests -----------------------------------------------------------------
    changed_tests = [f["path"] for f in act["files"]["tests"]]
    untested = []
    for sid, c in act["symbols"].items():
        s = c["sym"]
        if c["change"] == "removed" or system_of(f"mod:{s.module}") == "platform" or s.kind == "test":
            continue
        covered = sid in G_h and any(G_h.edges[u, sid]["type"] == "covers" for u in G_h.predecessors(sid))
        if not covered:
            untested.append({"id": sid, "label": f"{s.module}.{s.qualname}", "change": c["change"], "evidence": [c["evidence"]]})

    # ---- controls ----------------------------------------------------------------
    changed_paths = {f["path"] for grp in act["files"].values() for f in grp}
    controls = evaluate_controls(cat, paths=changed_paths, data_classes=data_classes, externals=set(externals))
    approvers = {r["user"]["login"] for r in pr.get("reviews", []) if r["state"] == "APPROVED"}
    approver_roles = {role for login in approvers for role in cat.roles_of(login)}
    changed_docs = [f["path"] for f in act["files"]["docs"]]
    predicted_controls = {c["id"] for c in report.get("controls", [])}
    for c in controls:
        checks = []
        for req in c["required_evidence"]:
            t = req["type"]
            if t == "approver_role":
                ok = req["role"] in approver_roles
                who = ", ".join(cat.people[p].name for p in cat.people_with_role(req["role"])) or req["role"]
                checks.append({"requirement": f"Approval from {req['role']} ({who})", "satisfied": ok,
                               "detail": "Approved" if ok else f"No approval from {req['role']} on PR #{number}",
                               "evidence": [pr_ev]})
            elif t == "test_change":
                pats = req.get("paths") or ["tests/*"]
                hits = [p for p in changed_tests if any(fnmatch.fnmatch(p, pat) for pat in pats)]
                checks.append({"requirement": "Test changes" + (f" in {', '.join(pats)}" if req.get("paths") else ""),
                               "satisfied": bool(hits), "detail": ", ".join(hits) or "No matching test changes in PR",
                               "evidence": [f["evidence"] for f in act["files"]["tests"] if f["path"] in hits]})
            elif t == "doc_change":
                pats = req.get("paths") or ["docs/*"]
                hits = [p for p in changed_docs if any(fnmatch.fnmatch(p, pat) for pat in pats)]
                checks.append({"requirement": f"Documentation updated ({', '.join(pats)})", "satisfied": bool(hits),
                               "detail": ", ".join(hits) or "No documentation changes in PR", "evidence": []})
        c["checks"] = checks
        c["satisfied"] = all(ch["satisfied"] for ch in checks)
        c["predicted"] = c["id"] in predicted_controls

    # ---- doc follow-ups (self-healing docs on the PR range) -------------------------
    doc_findings = detect_changes(engine, base, head, docs_ref=head, story=key, pr_number=number)

    # ---- verdict -----------------------------------------------------------------------
    actions = []
    for m in missed:
        if m["severity"] == "likely_miss":
            actions.append({"type": "missed", "severity": "high", "text": f"{m['label']} was predicted but not changed. "
                            + "; ".join(m["reasons"][:1]), "target": m["id"]})
    for s in surprises:
        if s["severity"] == "high":
            actions.append({"type": "surprise", "severity": "high", "text": f"Unplanned change in {s['label']}: {s['reasons'][0]}",
                            "target": s["id"]})
    for c in controls:
        for ch in c["checks"]:
            if not ch["satisfied"]:
                actions.append({"type": "control", "severity": "high", "text": f"{c['id']} {c['name']}: {ch['detail']}",
                                "target": c["id"]})
    if untested:
        actions.append({"type": "tests", "severity": "medium",
                        "text": f"{len(untested)} changed function(s) have no automated test: "
                                + ", ".join(u["label"].split(".")[-1] for u in untested), "target": "tests"})
    if doc_findings:
        actions.append({"type": "docs", "severity": "medium",
                        "text": f"{len(doc_findings)} documentation update(s) needed", "target": "docs"})

    predicted_n, actual_n = len(predicted_code), len(actual_mods)
    return {
        "pr": {"number": number, "title": pr["title"], "author": pr["user"]["login"], "state": pr["state"],
               "base": base, "head": head, "head_ref": pr["head"]["ref"], "jira_key": key,
               "approvers": sorted(approvers), "labels": [l["name"] for l in pr.get("labels", [])],
               "commits": engine.repo.log(base, head), "evidence": pr_ev},
        "compared_against": source,
        "baseline_confirmed_by": baseline.get("confirmed_by") if baseline else None,
        "verdict": {"ready": not any(a["severity"] == "high" for a in actions), "actions": actions,
                    "high": sum(a["severity"] == "high" for a in actions)},
        "code": {"confirmed": confirmed, "surprise": surprises, "missed": missed, "supporting": supporting},
        "data": data_rows, "external": list(externals.values()),
        "tests": {"changed": changed_tests, "untested": untested},
        "controls": controls, "doc_findings": doc_findings, "files": act["files"],
        "accuracy": {"predicted": predicted_n, "actual": actual_n, "confirmed": len(confirmed),
                     "precision": round(len(confirmed) / predicted_n, 2) if predicted_n else None,
                     "recall": round(len(confirmed) / actual_n, 2) if actual_n else None},
    }
