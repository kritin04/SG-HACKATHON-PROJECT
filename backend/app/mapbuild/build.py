"""Build the dependency map: inventory -> code facts -> config/schema -> link resolution -> catalog.

Steps 1-4 are exact (parsers + config). Step 5 (AI enrichment) lives in enrich.py and only ADDS
descriptions, labels and verified extra links on top of this map.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..engine.catalog import Catalog, load_catalog
from ..engine.evidence import STORE
from .. import config
from .facts import ServiceFacts
from .java_extract import extract_java
from .k8s import Manifests, read_manifests
from .model import ProjectMap, norm_path
from .project import Project, load_project
from .python_extract import extract_python
from .schema import read_schemas

NOISE_CALLS = {"assertEquals", "assertNotNull", "assertTrue", "assertFalse", "assertThrows", "assert_called_once",
               "getBody", "getStatusCode", "doReturn", "when", "thenReturn", "verify", "mock", "get", "post"}


def find_source_dir(project: Project, name: str) -> Path | None:
    for d in sorted(project.source_dir.rglob(name)):
        if d.is_dir() and not project.excluded(d) and ((d / "Dockerfile").exists() or (d / "pom.xml").exists()):
            return d
    return None


def build_map(project: Project | None = None, catalog: Catalog | None = None) -> tuple[ProjectMap, dict]:
    project = project or load_project()
    catalog = catalog or load_catalog(config.DEMO_DATA / "catalog")
    sha = project.sha
    pm = ProjectMap(project.name, sha)
    man: Manifests = read_manifests(project)
    report = {"unresolved": [], "services": {}, "steps": []}

    # ---- 1. inventory -------------------------------------------------------------------------
    pm.add_node("user:customer", "user", "Customer", description="A bank customer using the website in a browser.")
    facts: dict[str, ServiceFacts] = {}
    for name, wl in sorted(man.workloads.items()):
        info = catalog.service(name)
        wl_ev = STORE.add("config", f"Kubernetes {wl.kind} {name}", f"kind: {wl.kind}\nname: {name}", wl.path, wl.line,
                          ref=sha[:7])
        src = find_source_dir(project, name)
        cat_ev = catalog.evidence.get(f"service:{name}")
        if wl.is_database:
            pm.add_node(f"db:{name}", "database", name, evidence=[wl_ev, cat_ev], engine="PostgreSQL",
                        path=project.rel(src) if src else None, owner=info.owner, capability=info.capability,
                        criticality=info.criticality)
            continue
        lang = "Java" if src and (src / "pom.xml").exists() else "Python"
        pm.add_node(f"svc:{name}", "service", name, evidence=[wl_ev, cat_ev], language=lang,
                    path=project.rel(src) if src else None, owner=info.owner, capability=info.capability,
                    criticality=info.criticality)
        if src:
            facts[name] = extract_java(project, name, src) if lang == "Java" else extract_python(project, name, src)
    report["steps"].append(f"Inventory: {len(facts)} services, {len(pm.of_type('database'))} databases from Kubernetes manifests")

    # ---- 2. schema: tables + columns ---------------------------------------------------------
    tables = read_schemas(project, [n.label for n in pm.of_type("database")])
    for key, t in tables.items():
        tid = f"table:{key}"
        pm.add_node(tid, "table", t.name, parent=f"db:{t.db}", evidence=[t.evidence], columns=[c for c, _ in t.columns])
        for col, typ in t.columns:
            cls = catalog.columns.get(f"{key}.{col}")
            pm.add_node(f"col:{key}.{col}", "column", col, parent=tid, sql_type=typ, classification=cls,
                        evidence=[t.evidence, catalog.evidence.get(f"column:{key}.{col}")])
    report["steps"].append(f"Schema: {len(tables)} tables from database init scripts")

    # ---- 3. per-service code facts -> nodes -----------------------------------------------------
    for svc, f in facts.items():
        sid = f"svc:{svc}"
        pm.nodes[sid].props.update(files=len(f.files), functions=len(f.functions), tests=len(f.tests))
        for fn in f.functions:
            pm.add_node(f"fn:{svc}:{fn.name}", "function", fn.name, parent=sid, evidence=[fn.evidence],
                        file=fn.file, lines=f"{fn.start}-{fn.end}")
        for ep in f.endpoints:
            eid = f"ep:{svc}:{ep.method} {ep.path}"
            pm.add_node(eid, "endpoint", f"{ep.method} {ep.path}", parent=sid, evidence=[ep.evidence],
                        method=ep.method, path=ep.path, handler=ep.function, file=ep.file,
                        ops=ep.path in project.ops_endpoints)
            pm.add_edge(eid, f"fn:{svc}:{ep.function}", "handled_by", "code", evidence=[ep.evidence])
        for tc in f.tests:
            pm.add_node(f"test:{svc}:{tc.name}", "test", tc.name, parent=sid, evidence=[tc.evidence], file=tc.file)
        report["services"][svc] = {"language": f.language, "files": len(f.files), "functions": len(f.functions),
                                   "endpoints": len(f.endpoints), "tests": len(f.tests)}

    # customer -> frontend (the only service exposed outside the cluster)
    for svc in facts:
        wl = man.workloads[svc]
        if svc == "frontend" or any(e.path in ("/", "/home") for e in facts[svc].endpoints):
            pm.add_edge("user:customer", f"svc:{svc}", "uses", "config",
                        evidence=[STORE.add("config", f"{svc} is the public website", f"Deployment {svc}", wl.path, wl.line,
                                            ref=sha[:7])])

    # ---- 4. resolve links ----------------------------------------------------------------------
    for svc, f in facts.items():
        sid = f"svc:{svc}"
        wl = man.workloads[svc]
        # settings
        for env in f.env:
            val, cfg_ev = wl.env.get(env.name, ("(not set in manifests)", None))
            pm.add_node(f"cfg:{env.name}", "config", env.name, value=val, evidence=[cfg_ev])
            pm.add_edge(sid, f"cfg:{env.name}", "needs_config", "code", evidence=[env.evidence, cfg_ev])
        # API calls
        for call in f.outbound:
            val, cfg_ev = wl.env.get(call.env_var, (None, None))
            tgt = man.target_of(val) if val else None
            if not tgt or tgt[0] != "service":
                report["unresolved"].append({"service": svc, "reason": f"{call.env_var} not wired to a service",
                                             "line": call.line, "file": call.file})
                continue
            target_svc = tgt[1]
            candidates = [n for n in pm.nodes.values() if n.type == "endpoint" and n.parent == f"svc:{target_svc}"
                          and norm_path(n.props["path"]) == norm_path(call.path)]
            exact = [n for n in candidates if call.method and n.props["method"] == call.method]
            match = exact or (candidates if call.method is None and len(candidates) == 1 else [])
            if not match:
                kind = "ambiguous_method" if call.method is None and len(candidates) > 1 else "no_matching_endpoint"
                report["unresolved"].append({
                    "service": svc, "kind": kind, "function": call.function, "file": call.file, "line": call.line,
                    "reason": (f"Calls {target_svc} at {call.path}, but the HTTP method is hidden inside a helper, and "
                               f"{target_svc} offers {', '.join(n.label for n in candidates)} on that path"
                               if kind == "ambiguous_method" else f"No endpoint {call.method} {call.path} on {target_svc}"),
                    "candidates": [n.id for n in candidates], "evidence": [call.evidence, cfg_ev], "how": call.how})
                continue
            ep = match[0]
            conf = 1.0 if exact else 0.85
            how = call.how + (" | method inferred: the only endpoint with this path" if not exact else "")
            evid = [call.evidence, cfg_ev, ep.evidence[0] if ep.evidence else None]
            pm.add_edge(sid, ep.id, "calls_api", "code", conf, ep.label, evid, how=how)
            pm.add_edge(f"fn:{svc}:{call.function}", ep.id, "calls_api", "code", conf, ep.label, evid, how=how)
            pm.add_edge(sid, f"svc:{target_svc}", "calls_api", "code", conf, ep.label, evid)
        # database access: which database does this service connect to?
        dbs = []
        for env in f.env:
            val, cfg_ev = wl.env.get(env.name, (None, None))
            tgt = man.target_of(val) if val else None
            if tgt and tgt[0] == "database":
                dbs.append((tgt[1], [env.evidence, cfg_ev]))
        for var, (val, cfg_ev) in wl.env.items():           # Spring reads SPRING_DATASOURCE_URL implicitly
            tgt = man.target_of(val)
            if var.startswith("SPRING_DATASOURCE") and tgt and tgt[0] == "database" and f.language == "Java":
                dbs.append((tgt[1], [cfg_ev]))
        for use in f.tables:
            db = next((d for d, _ in dbs if f"{d}.{use.table}" in tables), None)
            if not db:
                report["unresolved"].append({"service": svc, "reason": f"table {use.table} not found in a connected database",
                                             "line": use.line, "file": use.file})
                continue
            db_ev = next(e for d, e in dbs if d == db)
            tid = f"table:{db}.{use.table}"
            ev = [use.evidence, *db_ev]
            pm.add_edge(sid, tid, use.mode + "s", "code", detail=use.function, evidence=ev)
            pm.add_edge(sid, f"db:{db}", use.mode + "s", "code", detail=use.table, evidence=ev)
            fid = f"fn:{svc}:{use.function}"
            if fid in pm.nodes:
                pm.add_edge(fid, tid, use.mode + "s", "code", evidence=[use.evidence])
        # in-service function calls
        by_short = {}
        for fn in f.functions:
            by_short.setdefault(fn.name.split(".")[-1], []).append(fn.name)
        for fn in f.functions:
            for c in fn.calls:
                for target in by_short.get(c, []):
                    if target != fn.name:
                        pm.add_edge(f"fn:{svc}:{fn.name}", f"fn:{svc}:{target}", "calls", "code", evidence=[fn.evidence])
        # tests -> endpoints / functions
        for tc in f.tests:
            tid = f"test:{svc}:{tc.name}"
            for m, p in tc.paths:
                for ep in [n for n in pm.nodes.values() if n.type == "endpoint" and n.parent == sid
                           and n.props["method"] == m and norm_path(n.props["path"]) == norm_path(p)]:
                    pm.add_edge(tid, ep.id, "tests", "code", evidence=[tc.evidence])
            for c in tc.calls - NOISE_CALLS:
                for target in by_short.get(c, []):
                    pm.add_edge(tid, f"fn:{svc}:{target}", "tests", "code", evidence=[tc.evidence])
        for u in f.unresolved:
            report["unresolved"].append({"service": svc, "kind": "unknown_url", "candidates": [],
                                         "reason": "The parser could not work out where this call goes", **u})

    # login tokens: who signs them, who trusts them
    issuers = [s for s, f in facts.items() if f.token_issuer]
    for svc, f in facts.items():
        if f.token_verifier:
            for iss in issuers:
                if iss != svc:
                    pm.add_edge(f"svc:{svc}", f"svc:{iss}", "trusts_tokens_from", "code",
                                evidence=f.token_verifier[:1] + facts[iss].token_issuer[:1])

    # ---- catalog: outside systems ---------------------------------------------------------------
    for x in catalog.external_systems:
        xev = catalog.evidence.get(f"ext:{x.id}")
        pm.add_node(f"ext:{x.id}", "external", x.name, evidence=[xev], description=x.description, owner=x.owner,
                    criticality=x.criticality)
        for target in x.consumes:
            for tid in ([target] if target in pm.nodes else []):
                pm.add_edge(f"ext:{x.id}", tid, "consumes", "catalog", evidence=[xev])
                db = pm.nodes[tid].parent
                if db:
                    pm.add_edge(f"ext:{x.id}", db, "consumes", "catalog", detail=pm.nodes[tid].label, evidence=[xev])

    report["steps"].append(f"Links: {sum(1 for e in pm.edges.values() if e.type == 'calls_api' and e.source.startswith('svc:') and e.target.startswith('svc:'))} service-to-service API links, "
                           f"{sum(1 for e in pm.edges.values() if e.type in ('reads', 'writes') and e.target.startswith('table:'))} table links")
    report["counts"] = {t: len(pm.of_type(t)) for t in ("service", "database", "table", "column", "endpoint", "config",
                                                         "function", "test", "external")}
    report["counts"]["edges"] = len(pm.edges)
    return pm, report
