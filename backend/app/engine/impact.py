"""Jira CR impact analysis: a 6-stage hybrid pipeline. The map gives recall, the AI judges, code verifies.

  1 Understand  (AI)    what the CR wants, likely parts, new data, outside systems, open questions
  2 Entry points        glossary words + names in the text + AI-named parts + meaning-based search (embeddings)
  3 Blast radius (map)  follow verified dependency links from the entry points
  4 Judge       (AI)    per candidate: must change / likely affected / retest only / not impacted + HOW
  5 Assess   (rules+AI) data sensitivity, API contract changes, outside systems, controls, tests, owners, risk;
                        AI writes the summary, business impact, test scenarios, size
  6 Verify + assemble   unverifiable AI answers fall back to rule-based results and are flagged
"""
from __future__ import annotations

import json
import re
import time

from .. import config
from ..llm import prompts
from ..llm.service import ask, evidence_pack
from ..llm.verify import check_citations, strip_inline_citations
from .cochange import coupled_with, service_cochange
from .graph import describe_path, propagate

VERDICTS = ["must_change", "likely_affected", "retest_only", "not_impacted"]
RANK = {v: i for i, v in enumerate(VERDICTS)}
JUDGE_TYPES = ("service", "endpoint", "table", "external")


def load_issues() -> dict[str, dict]:
    items = json.loads((config.DEMO_DATA / "jira" / "issues.json").read_text(encoding="utf-8"))
    extra = config.WORKSPACE / "new_crs.json"
    if extra.exists():
        items += json.loads(extra.read_text(encoding="utf-8"))
    return {i["key"]: i for i in items}


def issue_text(issue: dict) -> str:
    f = issue["fields"]
    return f"{f['summary']}\n{f.get('description', '')}\n" + "\n".join(f.get("acceptance_criteria", []))


def _label_index(pm):
    idx = {}
    for n in pm.nodes.values():
        if n.type in ("service", "database", "external"):
            idx[n.label.lower()] = n.id
        if n.type == "table":
            idx[n.label.lower()] = n.id
            idx[n.id.removeprefix("table:").lower()] = n.id
    return idx


def analyze(state, key: str, mode: str = "auto", model: str | None = None, progress=lambda stage, msg: None) -> dict:
    pm, cat, store = state.ensure_map(), state.catalog, state.store
    issue = load_issues()[key]
    f = issue["fields"]
    text = issue_text(issue)
    t0 = time.time()
    # share live progress through the database, so the board sees jobs started by ANY process (API or scripts)
    outer = progress

    def progress(stage, msg):
        store.put(f"job:{key}", {"status": "running", "stage": stage, "stage_name": msg, "started": t0,
                                 "updated": time.time(), "elapsed": round(time.time() - t0, 1), "model": model})
        outer(stage, msg)
    stages: dict[str, dict] = {}
    labels = _label_index(pm)

    # ------------------------------------------------------------------ 1. understand (AI)
    progress(1, "Understanding the change request")
    parts = [f"- {n.label} ({n.type}): {n.props.get('description') or n.props.get('capability') or ''}".strip()
             for n in pm.nodes.values() if n.type in ("service", "database", "external")]
    parts += [f"- {n.label} (table in {n.parent.split(':')[1]}): {n.props.get('description', '')}" for n in pm.of_type("table")]
    u_resp, meta = ask(store, "impact_understand", prompts.UNDERSTAND_SYSTEM, prompts.UNDERSTAND_USER.format(
        key=key, summary=f["summary"], description=f.get("description", ""),
        ac="\n".join(f"- {a}" for a in f.get("acceptance_criteria", [])),
        components=", ".join(c["name"] for c in f.get("components", [])), labels=", ".join(f.get("labels", [])),
        parts="\n".join(parts)), prompts.UNDERSTAND_SCHEMA, mode, model)
    stages["understand"] = meta
    understanding = {"change_type": None, "intent": f["summary"], "business_terms": [], "likely_parts": [],
                     "new_data": [], "outside_systems": [], "open_questions": [], "assumptions": [], "dropped": []}
    if u_resp:
        understanding.update({k: u_resp.get(k, understanding[k]) for k in understanding if k != "dropped"})
        known = [p for p in u_resp.get("likely_parts", []) if p.lower() in labels]
        understanding["dropped"] = [p for p in u_resp.get("likely_parts", []) if p.lower() not in labels]
        understanding["likely_parts"] = known
        understanding["outside_systems"] = [x for x in u_resp.get("outside_systems", []) if x.lower() in labels]
        understanding["new_data"] = [d for d in u_resp.get("new_data", [])
                                     if d.get("table", "").lower() in labels or d.get("table", "").lower() == "new"]

    # ------------------------------------------------------------------ 2. entry points
    progress(2, "Finding where the change starts in the code")
    seeds: dict[str, dict] = {}

    def seed(nid, w, reason, source):
        if nid not in pm.nodes:
            return
        s = seeds.setdefault(nid, {"weight": 0.0, "reasons": [], "sources": []})
        s["weight"] = max(s["weight"], w)
        if reason not in s["reasons"]:
            s["reasons"].append(reason)
        if source not in s["sources"]:
            s["sources"].append(source)

    for term, word in cat.match_terms(text):
        for t in term.targets:
            seed(t, 0.8, f'Business word "{word}" (glossary)', "glossary")
    low = text.lower()
    for lbl, nid in labels.items():
        if len(lbl) > 4 and re.search(rf"(?<![a-z]){re.escape(lbl)}(?![a-z])", low) and pm.nodes[nid].type != "external":
            seed(nid, 0.9, f'The request names "{pm.nodes[nid].label}"', "text")
    for p in understanding["likely_parts"]:
        seed(labels[p.lower()], 0.75, "AI: likely needs to change", "ai")
    for x in understanding["outside_systems"]:
        seed(labels[x.lower()], 0.7, "AI: involves this outside system", "ai")
    for d in understanding["new_data"]:
        if d["table"].lower() in labels:
            seed(labels[d["table"].lower()], 0.85, f'Needs new field "{d["field"]}"', "ai")
    semantic = []
    try:
        if not config.SEMANTIC_SEARCH:
            raise RuntimeError("semantic search disabled")
        idx = state.semantic_index()
        query = f"{f['summary']}. {f.get('description', '')} {understanding['intent']} {' '.join(understanding['business_terms'])}"
        hits = idx.search(query, k=12, types=("service", "endpoint", "table", "external", "function"), pm=pm)
        top = hits[0][1] if hits else 0
        for nid, sim in hits[:6]:
            if sim >= max(0.6, top - 0.06):
                semantic.append({"id": nid, "label": pm.nodes[nid].label, "similarity": round(sim, 3)})
                seed(nid, min(0.8, sim), f"Meaning match with the request ({sim:.2f})", "semantic")
        stages["semantic"] = {"status": "ok", "hits": semantic}
    except Exception as exc:  # embeddings model unavailable -> keep going without it
        stages["semantic"] = {"status": "unavailable", "error": str(exc)[:160]}

    # ------------------------------------------------------------------ 3. blast radius (map)
    progress(3, "Following the dependency map")
    reach = propagate(pm, {n: s["weight"] for n, s in seeds.items()}, max_depth=3, min_score=0.3)
    cands: dict[str, dict] = {}
    for nid, r in sorted(reach.items(), key=lambda kv: -kv[1].score):
        n = pm.nodes[nid]
        if n.type == "function" and n.parent:                       # judge at service/endpoint level
            continue
        if n.type not in JUDGE_TYPES or n.props.get("ops"):
            continue
        why = seeds[nid]["reasons"] if nid in seeds else [
            "; ".join(f"{s['from']} {s['relation']} {s['to']}" for s in describe_path(pm, r.path)[-2:])]
        cands[nid] = {"id": nid, "label": n.label, "type": n.type, "service": n.parent.split(":", 1)[1] if n.parent else None,
                      "score": round(r.score, 2), "seed": nid in seeds, "why": why,
                      "path": describe_path(pm, r.path), "evidence": n.evidence[:2]}
    for nid in list(seeds):                                         # functions -> their service as candidate
        n = pm.nodes[nid]
        if n.type == "function" and n.parent not in cands:
            cands[n.parent] = {"id": n.parent, "label": pm.nodes[n.parent].label, "type": "service", "service": None,
                               "score": round(seeds[nid]["weight"], 2), "seed": True,
                               "why": [f"Contains {n.label}() which matches the request"], "path": [], "evidence": n.evidence[:1]}
    cc = service_cochange(state.project, pm)
    for sid in [c for c in cands if c.startswith("svc:") and cands[c]["seed"]]:
        for other, n_commits, ratio in coupled_with(cc, sid):
            if other in pm.nodes and other not in cands:
                cands[other] = {"id": other, "label": pm.nodes[other].label, "type": pm.nodes[other].type, "service": None,
                                "score": 0.4, "seed": False, "path": [], "evidence": [],
                                "why": [f"Changed together with {pm.nodes[sid].label} in {n_commits} past commits (git history)"]}
    stages["cochange"] = {"commits_with_code_changes": cc["commits"], "pairs": len(cc["pairs"])}
    ordered = sorted(cands.values(), key=lambda c: (-c["seed"], -c["score"]))[:24]
    cands = {c["id"]: c for c in ordered}

    # ------------------------------------------------------------------ 4. judge (AI)
    progress(4, "Judging what must change and how")
    lines, ev_ids = [], []
    for c in ordered:
        n = pm.nodes[c["id"]]
        desc = n.props.get("description") or ""
        lines.append(f"- [{c['id']}] {n.type} {n.label}{' of ' + c['service'] if c['service'] else ''}: {desc[:140]} "
                     f"| candidate because: {'; '.join(c['why'])[:200]}")
        if n.type == "endpoint":
            h = f"fn:{c['service']}:{n.props.get('handler')}"
            if h in pm.nodes:
                ev_ids.extend(pm.nodes[h].evidence[:1])
        elif n.type == "table":
            ev_ids.extend(n.evidence[:1])
    evidence, pack = evidence_pack(ev_ids, max_chars=650, max_blocks=7)
    j_resp, meta = ask(store, "impact_judge", prompts.JUDGE_SYSTEM, prompts.JUDGE_USER.format(
        key=key, summary=f["summary"], intent=understanding["intent"], candidates="\n".join(lines), evidence=evidence),
        prompts.JUDGE_SCHEMA, mode, model)
    stages["judge"] = meta
    judged = {}
    if j_resp:
        for it in j_resp.get("items", []):
            if it.get("id") in cands and it.get("verdict") in VERDICTS:
                ids, _ = check_citations(it.get("evidence_ids", []), pack)
                judged[it["id"]] = {"verdict": it["verdict"], "how": strip_inline_citations(it.get("how", "")),
                                    "evidence": ids, "by": "ai"}
    items = []
    ai_named = {labels[p.lower()] for p in understanding["likely_parts"]}
    for c in ordered:
        j = judged.get(c["id"])
        if not j:                                                   # rule-based fallback, flagged
            v = ("must_change" if c["id"] in ai_named else "likely_affected" if c["score"] >= 0.7
                 else "retest_only" if c["score"] >= 0.45 else "not_impacted")
            j = {"verdict": v, "how": "; ".join(c["why"]), "evidence": [], "by": "rules"}
        items.append(c | j | {"evidence": list(dict.fromkeys(j["evidence"] + c["evidence"]))})
    # consistency: a service is at least as affected as its most affected endpoint/table writer
    by_id = {i["id"]: i for i in items}
    for i in items:
        parent = pm.nodes[i["id"]].parent
        if i["type"] == "endpoint" and parent in by_id and RANK[i["verdict"]] < RANK[by_id[parent]["verdict"]]:
            by_id[parent]["verdict"] = i["verdict"]
            by_id[parent]["how"] += f" (because {i['label']} {i['verdict'].replace('_', ' ')})"

    # ------------------------------------------------------------------ 5. assess (rules)
    progress(5, "Checking data, outside systems, controls and tests")
    impacted = [i for i in items if i["verdict"] in ("must_change", "likely_affected")]
    changing = [i for i in items if i["verdict"] == "must_change"]
    data = []
    classes: dict[str, list[str]] = {}
    for i in items:
        if i["type"] != "table" or i["verdict"] == "not_impacted":
            continue
        cols = [n for n in pm.nodes.values() if n.type == "column" and n.parent == i["id"]]
        cls = sorted({c.props["classification"] for c in cols if c.props.get("classification")})
        writers = sorted({e.source.split(":")[1] for e in pm.in_edges(i["id"], "writes") if e.source.startswith("svc:")})
        readers = sorted({e.source.split(":")[1] for e in pm.in_edges(i["id"], "reads") if e.source.startswith("svc:")})
        data.append({"id": i["id"], "label": i["label"], "verdict": i["verdict"], "classifications": cls,
                     "writers": writers, "readers": readers, "new_fields": []})
        if i["verdict"] == "must_change" or (i["by"] == "rules" and i["verdict"] == "likely_affected"):   # AI: only data that changes; rules: stay cautious
            for c in cls:
                classes.setdefault(c, []).append(i["label"])
    for d in understanding["new_data"]:
        tid = labels.get(d["table"].lower())
        row = next((x for x in data if x["id"] == tid), None)
        if row is None and tid:
            row = {"id": tid, "label": pm.nodes[tid].label, "verdict": "must_change", "classifications": [],
                   "writers": [], "readers": [], "new_fields": []}
            data.append(row)
        if row is not None:
            row["new_fields"].append(d)
        if d.get("sensitivity") in ("Personal", "Financial"):
            classes.setdefault(d["sensitivity"], []).append(f"new field {d['field']}")
    contract = []
    for i in changing:
        if i["type"] == "endpoint":
            callers = [e.source.split(":")[1] for e in pm.in_edges(i["id"], "calls_api") if e.source.startswith("svc:")]
            if callers:
                contract.append({"api": i["label"], "service": i["service"], "callers": callers})
        if i["type"] == "service":
            callers = sorted({e.source.split(":")[1] for e in pm.in_edges(i["id"], "calls_api") if e.source.startswith("svc:")
                              and by_id.get(e.source, {}).get("verdict") in ("must_change", "likely_affected")})
            if callers and not any(c["service"] == i["label"] for c in contract):
                contract.append({"api": f"{i['label']} API", "service": i["label"], "callers": callers})
    # an outside system is only affected if data it reads actually CHANGES (a writer of that table changes,
    # or the table gains fields). Read-only changes on our side cannot affect what it receives.
    changed_tables = {d["id"] for d in data if d["new_fields"]}
    for d in data:
        if any(by_id.get(f"svc:{w}", {}).get("verdict") in ("must_change", "likely_affected") for w in d["writers"]):
            changed_tables.add(d["id"])
    for i in items:
        if i["type"] != "external" or i["verdict"] == "not_impacted":
            continue
        reads = {e.target for e in pm.out_edges(i["id"], "consumes") if e.target.startswith("table:")}
        if reads and not reads & changed_tables:
            i.update(verdict="not_impacted", by="rules", ai_verdict=i["verdict"],
                     how=f"Only reads {', '.join(pm.nodes[t].label for t in reads)}, which this change does not modify")
    externals = [i for i in items if i["type"] == "external" and i["verdict"] != "not_impacted"]
    for x in understanding["outside_systems"]:
        xid = labels[x.lower()]
        if xid not in {e["id"] for e in externals}:
            externals.append({"id": xid, "label": pm.nodes[xid].label, "type": "external", "verdict": "likely_affected",
                              "how": "Named by the AI as involved in this request", "by": "ai", "evidence": pm.nodes[xid].evidence})
    for e in externals:
        n = pm.nodes[e["id"]]
        e.update(owner=n.props.get("owner"), description=n.props.get("description"),
                 actions=["Notify the owner", "Test the data feed / interface", "Get sign-off"] if n.props.get("criticality") == "high"
                 else ["Notify the owner", "Test the interface"])
    # controls
    ext_ids = {e["id"].split(":", 1)[1] for e in externals}
    svc_names = {i["label"] for i in impacted if i["type"] == "service"}
    controls = []
    for c in cat.controls:
        t, why = c.triggers, []
        hit_cls = [k for k in t.get("data_classes", []) if k in classes]
        if hit_cls:
            why.append(f"Touches {', '.join(hit_cls)} data ({', '.join(sorted({x for k in hit_cls for x in classes[k]}))})")
        hit_svc = [s for s in t.get("services", []) if s in svc_names]
        if hit_svc:
            why.append(f"Changes {', '.join(hit_svc)}")
        if t.get("api_contract_change") and contract:
            why.append("API used by another service changes: " + "; ".join(f"{x['api']} used by {', '.join(x['callers'])}" for x in contract))
        hit_ext = [x for x in t.get("external_systems", []) if x in ext_ids]
        if hit_ext:
            why.append(f"Affects outside system {', '.join(pm.nodes['ext:' + x].label for x in hit_ext)}")
        if why:
            controls.append({"id": c.id, "name": c.name, "when": c.when, "requires": c.requires, "reasons": why,
                             "evidence": [cat.evidence.get(f"control:{c.id}")]})
    # tests: per service, the existing automated tests that cover the impacted APIs / code, and the gaps
    per_svc: dict[str, set] = {}
    gaps = []
    for i in impacted:
        if i["type"] not in ("service", "endpoint"):
            continue
        svc = i["label"] if i["type"] == "service" else i["service"]
        eps = [n for n in pm.nodes.values() if n.type == "endpoint" and n.parent == f"svc:{svc}"
               and (i["type"] == "service" or n.id == i["id"]) and not n.props.get("ops")]
        targets = [x for ep in eps for x in (ep.id, f"fn:{svc}:{ep.props.get('handler')}")]
        tested = {e.source for t in targets for e in pm.in_edges(t, "tests")}
        if tested:
            per_svc.setdefault(svc, set()).update(tested)
        elif i["verdict"] == "must_change":
            gaps.append({"for": i["label"], "service": svc, "reason": "No automated test covers this today"})
    tests_to_run = [{"for": svc, "service": svc, "count": len(t), "tests": sorted(pm.nodes[x].label for x in t)[:12]}
                    for svc, t in sorted(per_svc.items())]
    # owners / people
    people = {}
    for i in impacted:
        n = pm.nodes[i["id"]]
        if n.type == "external":
            continue                                   # outside systems are listed below with "notify"
        owner = n.props.get("owner") or (pm.nodes[n.parent].props.get("owner") if n.parent else None)
        if owner:
            what = i["label"] if i["type"] in ("service", "database") or not n.parent else n.parent.split(":")[1]
            people.setdefault(owner, set()).add(f"owns {what}")
    for e in externals:
        if e.get("owner"):
            people.setdefault(e["owner"], set()).add(f"owns outside system {e['label']}: notify")
    for c in controls:
        for r in c["requires"]:
            if "approval" in r.lower() or "sign-off" in r.lower() or "review" in r.lower():
                people.setdefault(r.replace(" approval", "").replace(" sign-off", ""), set()).add(f"{c['id']}: {r}")
    people_list = [{"who": k, "why": sorted(v)} for k, v in people.items()]
    # risk
    pts, reasons = 0, []
    if any(k.startswith("Personal") or k == "Secret" for k in classes):
        pts += 3; reasons.append("Personal or secret customer data is involved")
    if "Financial" in classes:
        pts += 1; reasons.append("Financial data is involved")
    if externals:
        pts += min(4, 2 * len(externals)); reasons.append(f"{len(externals)} outside system(s) affected: " + ", ".join(e["label"] for e in externals))
    if controls:
        pts += len(controls); reasons.append(f"{len(controls)} approval rule(s) apply: " + ", ".join(c["id"] for c in controls))
    if gaps:
        pts += 1; reasons.append(f"{len(gaps)} part(s) to change have no automated tests")
    if contract:
        pts += 1; reasons.append("An API used by another service changes")
    if understanding["open_questions"]:
        pts += 1; reasons.append(f"{len(understanding['open_questions'])} open question(s): the request is not fully clear")
    crit = [i["label"] for i in changing if pm.nodes[i["id"]].props.get("criticality") == "high"]
    if crit:
        pts += 1; reasons.append("High-criticality parts change: " + ", ".join(crit))
    risk = {"level": "High" if pts >= 6 else "Medium" if pts >= 3 else "Low", "points": pts, "reasons": reasons}

    # ------------------------------------------------------------------ 5b. assess (AI writes from verified facts)
    progress(6, "Writing the impact summary")
    facts = [f"- Risk {risk['level']}: {'; '.join(reasons) or 'no special risk factors'}"]
    for v in VERDICTS[:3]:
        facts += [f"- {v.replace('_', ' ')}: {i['label']} ({i['type']}): {i['how']}" for i in items if i["verdict"] == v]
    facts += [f"- outside system {e['label']}: {e.get('description')}" for e in externals]
    facts += [f"- data {d['label']}: {', '.join(d['classifications']) or 'not sensitive'}"
              + (f"; new fields {', '.join(x['field'] for x in d['new_fields'])}" if d["new_fields"] else "") for d in data]
    facts += [f"- approval rule {c['id']} {c['name']}: {'; '.join(c['reasons'])}" for c in controls]
    facts += [f"- tests exist for {t['for']} ({t['count']})" for t in tests_to_run] + [f"- NO tests for {g['for']}" for g in gaps]
    facts += [f"- open question: {q}" for q in understanding["open_questions"]]
    a_resp, meta = ask(store, "impact_assess", prompts.ASSESS_SYSTEM, prompts.ASSESS_USER.format(
        key=key, summary=f["summary"], intent=understanding["intent"], facts="\n".join(facts)), prompts.ASSESS_SCHEMA, mode, model)
    stages["assess"] = meta
    must_n, likely_n = len(changing), len([i for i in items if i["verdict"] == "likely_affected"])
    assessment = {
        "summary": strip_inline_citations(a_resp["summary"]) if a_resp else
        f"{f['summary']}: {must_n} part(s) must change and {likely_n} are likely affected. Risk is {risk['level']}.",
        "business_impact": strip_inline_citations(a_resp.get("business_impact", "")) if a_resp else "",
        "test_scenarios": a_resp.get("test_scenarios", []) if a_resp else [],
        "size": a_resp.get("size") if a_resp else None, "size_reason": a_resp.get("size_reason", "") if a_resp else "",
        "risks": a_resp.get("risks", []) if a_resp else [], "by": "ai" if a_resp else "rules"}

    # ------------------------------------------------------------------ 6. cards
    customer_facing = any(i["label"] == "frontend" for i in impacted) or "customer-facing" in f.get("labels", [])
    sens = sorted(classes)

    def card(status, line, count=None):
        return {"status": status, "line": line, "count": count}

    cards = {
        "business": card("amber" if customer_facing else "green",
                         assessment["business_impact"] or ("Customers will see a change" if customer_facing else "No visible change for customers")),
        "technical": card("red" if must_n >= 3 or contract else "amber" if must_n else "green",
                          f"{must_n} must change · {likely_n} likely affected · "
                          f"{len([i for i in items if i['verdict'] == 'retest_only'])} re-test" + (" · API contract changes" if contract else ""),
                          must_n + likely_n),
        "data": card("red" if any(s.startswith("Personal") or s == "Secret" for s in sens) else "amber" if data else "green",
                     (f"{', '.join(sens)} data · " if sens else "") + (f"{len(data)} table(s) involved" if data else "No database change"),
                     len(data)),
        "integrations": card("red" if any(pm.nodes[e["id"]].props.get("criticality") == "high" for e in externals) else
                             "amber" if externals else "green",
                             ", ".join(e["label"] for e in externals) if externals else "No outside systems affected", len(externals)),
        "testing": card("red" if gaps else "amber" if tests_to_run else "green",
                        f"{sum(t['count'] for t in tests_to_run)} existing tests to re-run · {len(gaps)} gap(s) · "
                        f"{len(assessment['test_scenarios'])} new scenarios suggested", len(gaps)),
        "compliance": card("red" if len(controls) >= 2 else "amber" if controls else "green",
                           ", ".join(f"{c['id']} {c['name']}" for c in controls) if controls else "No approval rules triggered",
                           len(controls)),
    }
    result = {
        "key": key, "sha": pm.sha, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seconds": round(time.time() - t0, 1),
        "ai_seconds": round(sum(m.get("seconds") or 0 for m in stages.values() if isinstance(m, dict)
                                and m.get("status") in ("generated", "cached")), 1),
        "model": next((m.get("model") for m in stages.values() if isinstance(m, dict) and m.get("model")), None),
        "cr": {"key": key, "summary": f["summary"], "description": f.get("description", ""),
               "acceptance_criteria": f.get("acceptance_criteria", []), "priority": f["priority"]["name"],
               "status": f["status"]["name"], "components": [c["name"] for c in f.get("components", [])],
               "labels": f.get("labels", []), "assignee": (f.get("assignee") or {}).get("displayName"),
               "reporter": (f.get("reporter") or {}).get("displayName")},
        "understanding": understanding, "entry_points": [{"id": k, "label": pm.nodes[k].label, "type": pm.nodes[k].type, **v}
                                                         for k, v in sorted(seeds.items(), key=lambda kv: -kv[1]["weight"])],
        "items": items, "data": data, "contract_changes": contract, "externals": externals, "controls": controls,
        "tests": {"to_run": tests_to_run, "gaps": gaps}, "people": people_list, "risk": risk,
        "assessment": assessment, "cards": cards, "stages": stages,
    }
    store.put(f"analysis:{key}:{pm.sha}", result)
    store.put(f"job:{key}", {"status": "done", "stage": 6, "stage_name": "Done", "started": t0, "updated": time.time(),
                             "elapsed": round(time.time() - t0, 1), "model": model})
    return result
