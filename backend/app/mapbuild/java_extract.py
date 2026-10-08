"""Extract facts from a Java (Spring Boot) service using the tree-sitter Java parser.

Handles the patterns used in Bank of Anthos and common Spring code:
  * routes:     @GetMapping("/x"), @PostMapping(value = "/x"), @RequestMapping on the class
  * settings:   @Value("${X}") / @Value("${X:default}")
  * URL wiring: @Value("http://${BALANCES_API_ADDR}/balances") String balancesApiUri
  * calls:      restTemplate.exchange(uri, HttpMethod.GET, ...), getForObject(...), postForEntity(...)
  * database:   @Entity @Table(name = "TRANSACTIONS"); repositories (CrudRepository) with @Query;
                repo.save(...) = write, other repo calls = read
  * tokens:     JWT verifier (JWT.require / JWTVerifier) = verifies login tokens
"""
from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_java as tsj
from tree_sitter import Language, Parser

from ..engine.evidence import STORE
from .facts import Endpoint, EnvRead, Function, OutboundCall, ServiceFacts, TableUse, TestCase
from .model import pretty_path
from .project import Project

JAVA = Language(tsj.language())
MAPPINGS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT", "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH", "RequestMapping": None}
REST_METHODS = {"getForObject": "GET", "getForEntity": "GET", "postForObject": "POST", "postForEntity": "POST",
                "put": "PUT", "delete": "DELETE", "exchange": None}
VALUE_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::[^}]*)?\}")


def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _strings(node, src) -> list[str]:
    return [_text(n, src)[1:-1] for n in _walk(node) if n.type == "string_literal"]


def _annotations(node, src) -> list[tuple[str, object]]:
    """(name, annotation node) for annotations in a declaration's modifiers."""
    mods = next((c for c in node.children if c.type == "modifiers"), None)
    out = []
    for c in (mods.children if mods else []):
        if c.type in ("annotation", "marker_annotation"):
            name = _text(c.child_by_field_name("name"), src)
            out.append((name, c))
    return out


def _mapping_path(ann, src) -> str:
    args = ann.child_by_field_name("arguments")
    if args is None:
        return ""
    for c in args.children:
        if c.type == "string_literal":
            return _text(c, src)[1:-1]
        if c.type == "element_value_pair" and _text(c.child_by_field_name("key"), src) in ("value", "path"):
            s = _strings(c, src)
            return s[0] if s else ""
    return ""


def extract_java(project: Project, service: str, src_dir: Path) -> ServiceFacts:
    facts = ServiceFacts(service, "Java", project.rel(src_dir))
    parser = Parser(JAVA)
    short = project.sha[:7]
    parsed = []
    for f in sorted(src_dir.rglob("*.java")):
        if project.excluded(f):
            continue
        src = f.read_bytes()
        parsed.append((f, project.rel(f), src, parser.parse(src)))
        facts.files.append(project.rel(f))

    # pass 1: entities -> tables, repositories -> tables
    entity_table: dict[str, str] = {}
    repo_table: dict[str, str] = {}
    repo_ev: dict[str, str] = {}
    for f, rel, src, tree in parsed:
        for n in _walk(tree.root_node):
            if n.type == "class_declaration":
                anns = dict(_annotations(n, src))
                cname = _text(n.child_by_field_name("name"), src)
                if "Entity" in anns:
                    tbl = (_strings(anns["Table"], src) or [cname])[0] if "Table" in anns else cname
                    entity_table[cname] = tbl.lower()
            if n.type == "interface_declaration":
                text = _text(n, src)
                m = re.search(r"extends\s+(?:Crud|Jpa|PagingAndSorting)Repository\s*<\s*(\w+)", text)
                if m:
                    iname = _text(n.child_by_field_name("name"), src)
                    repo_table[iname] = m.group(1)
                    repo_ev[iname] = STORE.add("code", f"{service}: repository {iname}", text, rel,
                                               n.start_point[0] + 1, n.end_point[0] + 1, short)
    repo_table = {k: entity_table.get(v, v.lower()) for k, v in repo_table.items()}

    for f, rel, src, tree in parsed:
        is_test = "/src/test/" in f"/{rel}"
        lines = src.decode("utf-8", errors="replace").splitlines()
        for cls in [n for n in _walk(tree.root_node) if n.type in ("class_declaration", "interface_declaration")]:
            cname = _text(cls.child_by_field_name("name"), src)
            prefix = ""
            for name, ann in _annotations(cls, src):
                if name == "RequestMapping":
                    prefix = _mapping_path(ann, src)
            # field / parameter types: variable name -> type (to recognise repositories)
            var_types: dict[str, str] = {}
            uri_vars: dict[str, tuple[str, str]] = {}   # variable -> (ENV_VAR, base path)
            for n in _walk(cls):
                if n.type in ("field_declaration", "formal_parameter", "local_variable_declaration"):
                    t = n.child_by_field_name("type")
                    names = [_text(d.child_by_field_name("name"), src) for d in _walk(n)
                             if d.type == "variable_declarator"] or \
                            ([_text(n.child_by_field_name("name"), src)] if n.child_by_field_name("name") else [])
                    for nm in names:
                        if t is not None:
                            var_types[nm] = _text(t, src)
                    for aname, ann in _annotations(n, src):
                        if aname == "Value":
                            for s in _strings(ann, src):
                                for var in VALUE_VAR.findall(s):
                                    line = n.start_point[0] + 1
                                    facts.env.append(EnvRead(var, rel, line, STORE.add(
                                        "code", f"{service} reads setting {var}", lines[line - 1].strip(), rel, line,
                                        line, short)))
                                um = re.match(r"^https?://\$\{([A-Z0-9_]+)\}(/.*)?$", s)
                                if um:
                                    for nm in names:
                                        uri_vars[nm] = (um.group(1), um.group(2) or "")
            # this.x = x aliases for URI variables
            for n in _walk(cls):
                if n.type == "assignment_expression":
                    left, right = _text(n.child_by_field_name("left"), src), _text(n.child_by_field_name("right"), src)
                    if right in uri_vars:
                        uri_vars[left.replace("this.", "")] = uri_vars[right]

            for m in [c for c in _walk(cls) if c.type in ("method_declaration", "constructor_declaration")]:
                mname = _text(m.child_by_field_name("name"), src)
                anns = _annotations(m, src)
                start, end = m.start_point[0] + 1, m.end_point[0] + 1
                ann_start = min([a.start_point[0] + 1 for _, a in anns] + [start])
                ev = STORE.add("code", f"{service}: {cname}.{mname}()", "\n".join(lines[ann_start - 1:end]), rel,
                               ann_start, end, short)
                calls = {_text(c.child_by_field_name("name"), src) for c in _walk(m) if c.type == "method_invocation"}
                if is_test:
                    if any(a == "Test" for a, _ in anns):
                        facts.tests.append(TestCase(f"{cname}.{mname}", rel, start, ev, [], calls))
                    continue
                if cls.type == "interface_declaration":
                    if cname in repo_table:
                        for aname, ann in anns:
                            if aname == "Query":
                                q = " ".join(_strings(ann, src))
                                mode = "read" if q.strip().upper().startswith("SELECT") else "write"
                                facts.tables.append(TableUse(repo_table[cname], mode, f"{cname}.{mname}", rel,
                                                             ann.start_point[0] + 1, ev))
                    continue
                func = Function(f"{cname}.{mname}", rel, ann_start, end, ev, calls)
                facts.functions.append(func)
                for aname, ann in anns:
                    if aname in MAPPINGS:
                        verb = MAPPINGS[aname] or "GET"
                        if aname == "RequestMapping" and "RequestMethod." in _text(ann, src):
                            verb = re.search(r"RequestMethod\.(\w+)", _text(ann, src)).group(1)
                        facts.endpoints.append(Endpoint(verb, pretty_path(prefix + _mapping_path(ann, src)),
                                                        func.name, rel, ann.start_point[0] + 1, ev))
                # local string vars built from URI fields: String uri = balancesApiUri + "/" + id;
                local_uri: dict[str, tuple[str, str]] = {}
                for d in _walk(m):
                    if d.type == "variable_declarator" and d.child_by_field_name("value") is not None:
                        val = d.child_by_field_name("value")
                        idents = [_text(x, src) for x in _walk(val) if x.type == "identifier"]
                        base = next((uri_vars[i] for i in idents if i in uri_vars), None)
                        if base:
                            suffix = "/{}" if "+" in _text(val, src) else ""
                            local_uri[_text(d.child_by_field_name("name"), src)] = (base[0], base[1] + suffix)
                for c in [x for x in _walk(m) if x.type == "method_invocation"]:
                    name = _text(c.child_by_field_name("name"), src)
                    obj = c.child_by_field_name("object")
                    obj_name = _text(obj, src) if obj is not None else ""
                    line = c.start_point[0] + 1
                    call_ev = lambda title: STORE.add("code", title, "\n".join(lines[line - 1:c.end_point[0] + 1]).strip(),
                                                      rel, line, c.end_point[0] + 1, short)
                    args = c.child_by_field_name("arguments")
                    vtype = var_types.get(obj_name.replace("this.", ""), "")
                    is_rest_client = vtype in ("RestTemplate", "WebClient", "RestClient") or "rest" in obj_name.lower()
                    if name in REST_METHODS and args is not None and is_rest_client:
                        arg_ids = [_text(a, src) for a in args.children if a.type == "identifier"]
                        target = next((local_uri.get(a) or uri_vars.get(a) for a in arg_ids
                                       if a in local_uri or a in uri_vars), None)
                        verb = REST_METHODS[name]
                        hm = re.search(r"HttpMethod\.(\w+)", _text(args, src))
                        verb = hm.group(1) if hm else verb
                        if target:
                            facts.outbound.append(OutboundCall(func.name, target[0], pretty_path(target[1]), verb, rel,
                                                               line, call_ev(f"{service}: {func.name}() calls {target[0]}"),
                                                               how=f"@Value(\"http://${{{target[0]}}}{target[1].split('/{')[0]}\")"))
                        else:
                            facts.unresolved.append({"function": func.name, "file": rel, "line": line,
                                                     "code": lines[line - 1].strip(), "template": "?"})
                    if vtype in repo_table:
                        mode = "write" if name in ("save", "saveAll", "delete", "deleteAll") else "read"
                        facts.tables.append(TableUse(repo_table[vtype], mode, func.name, rel, line,
                                                     call_ev(f"{service}: {func.name}() uses {vtype}.{name}()")))
                    if name in ("require", "verify") and ("JWT" in obj_name or "verifier" in obj_name.lower()):
                        facts.token_verifier.append(call_ev(f"{service} verifies login tokens"))
    return facts
