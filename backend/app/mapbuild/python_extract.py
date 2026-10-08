"""Extract facts from a Python (Flask) service with Python's own parser (`ast`).

Handles the patterns used in Bank of Anthos and common Flask code:
  * routes:     @app.route('/path', methods=['POST'])
  * settings:   os.environ.get('X'), os.getenv('X'), os.environ['X']
  * URL wiring: app.config["URI"] = 'http://{}/path'.format(os.environ.get('X_API_ADDR'))
  * calls:      requests.post(url=app.config["URI"]), ApiRequest(url=f'{app.config["URI"]}/{id}')
  * database:   self.t = Table("users", ...); self.t.insert()/select()/update()/delete(); raw SQL strings
  * tokens:     jwt.encode (issues), jwt.decode (verifies)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from ..engine.evidence import STORE
from .facts import Endpoint, EnvRead, Function, OutboundCall, ServiceFacts, TableUse, TestCase
from .model import pretty_path
from .project import Project

HTTP_VERBS = {"get", "post", "put", "delete", "patch"}
SQL_TABLE = re.compile(r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _env_name(node) -> str | None:
    """os.environ.get('X') / os.getenv('X') / os.environ['X'] -> 'X'."""
    if isinstance(node, ast.Call) and _dotted(node.func) in ("os.environ.get", "os.getenv", "environ.get", "getenv"):
        return _const(node.args[0]) if node.args else None
    if isinstance(node, ast.Subscript) and _dotted(node.value) in ("os.environ", "environ"):
        return _const(node.slice)
    return None


def _config_key(node) -> str | None:
    """app.config["X"] -> 'X'."""
    if isinstance(node, ast.Subscript) and _dotted(node.value).endswith("config"):
        return _const(node.slice)
    return None


def _template(node, local: dict, depth: int = 0) -> str:
    """Render an expression as a URL template: app.config keys -> <<KEY>>, env vars -> <<$VAR>>, unknowns -> {}."""
    if depth > 5 or node is None:
        return "{}"
    if (k := _config_key(node)) is not None:
        return f"<<{k}>>"
    if (v := _env_name(node)) is not None:
        return f"<<${v}>>"
    if (c := _const(node)) is not None:
        return c
    if isinstance(node, ast.JoinedStr):
        return "".join(_template(v.value if isinstance(v, ast.FormattedValue) else v, local, depth + 1) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _template(node.left, local, depth + 1) + _template(node.right, local, depth + 1)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        fmt = _template(node.func.value, local, depth + 1)
        for a in node.args:
            fmt = fmt.replace("{}", _template(a, local, depth + 1), 1)
        return fmt
    if isinstance(node, ast.Name) and node.id in local:
        return _template(local[node.id], local, depth + 1)
    return "{}"


def _own_nodes(fn):
    """Walk a function body without descending into nested functions/classes."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    stack = [n for n in fn.body if not isinstance(n, nested)]
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                stack.append(child)


def extract_python(project: Project, service: str, src: Path) -> ServiceFacts:
    facts = ServiceFacts(service, "Python", project.rel(src))
    short = project.sha[:7]
    uri_map: dict[str, str] = {}          # app.config key -> template like 'http://<<$X_API_ADDR>>/balances'
    table_attrs: dict[str, str] = {}      # self.users_table -> users
    parsed = []

    for f in sorted(src.rglob("*.py")):
        if project.excluded(f):
            continue
        text = project.read(f)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = project.rel(f)
        facts.files.append(rel)
        parsed.append((f, rel, text, tree))
        lines = text.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                key = _config_key(node.targets[0])
                if key:
                    uri_map[key] = _template(node.value, {})
                tgt = _dotted(node.targets[0])
                if isinstance(node.value, ast.Call) and _dotted(node.value.func).endswith("Table") and node.value.args:
                    tname = _const(node.value.args[0])
                    if tname:
                        table_attrs[tgt] = tname.lower()
            if (name := _env_name(node)) is not None:
                ev = STORE.add("code", f"{service} reads setting {name}", lines[node.lineno - 1].strip(), rel,
                               node.lineno, node.lineno, short)
                facts.env.append(EnvRead(name, rel, node.lineno, ev))

    for f, rel, text, tree in parsed:
        lines = text.splitlines()
        is_test = "/tests/" in f"/{rel}" or Path(rel).name.startswith("test_")
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            start = fn.decorator_list[0].lineno if fn.decorator_list else fn.lineno
            snippet = "\n".join(lines[start - 1:fn.end_lineno])
            ev = STORE.add("code", f"{service}: {fn.name}()", snippet, rel, start, fn.end_lineno, short)
            if is_test:
                if fn.name.startswith("test"):
                    tc = TestCase(fn.name, rel, fn.lineno, ev)
                    for n in ast.walk(fn):
                        if isinstance(n, ast.Call):
                            d = _dotted(n.func)
                            meth = d.split(".")[-1]
                            if meth in HTTP_VERBS and n.args and (p := _template(n.args[0], {})).startswith("/"):
                                tc.paths.append((meth.upper(), pretty_path(p)))
                            if d:
                                tc.calls.add(meth)
                    facts.tests.append(tc)
                continue

            func = Function(fn.name, rel, start, fn.end_lineno, ev)
            facts.functions.append(func)
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and _dotted(dec.func).endswith(".route") and dec.args:
                    path = _const(dec.args[0])
                    methods = ["GET"]
                    for kw in dec.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            methods = [(_const(e) or "GET").upper() for e in kw.value.elts]
                    for m in methods:
                        facts.endpoints.append(Endpoint(m, pretty_path(path), fn.name, rel, dec.lineno, ev))

            local: dict[str, ast.AST] = {}
            for n in _own_nodes(fn):
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                    local[n.targets[0].id] = n.value
            for n in _own_nodes(fn):
                if not isinstance(n, ast.Call):
                    continue
                d = _dotted(n.func)
                last = d.split(".")[-1]
                if d:
                    func.calls.add(last)
                    func.call_lines[last] = min(func.call_lines.get(last, n.lineno), n.lineno)
                line_ev = lambda title: STORE.add("code", title, "\n".join(lines[n.lineno - 1:(n.end_lineno or n.lineno)]),
                                                  rel, n.lineno, n.end_lineno, short)
                # outbound HTTP
                url_node = next((k.value for k in n.keywords if k.arg == "url"), n.args[0] if n.args else None)
                method = None
                if d.startswith("requests.") and last in HTTP_VERBS:
                    method = last.upper()
                elif last == "ApiRequest" or (d in HTTP_VERBS and url_node is not None):
                    method = None if last == "ApiRequest" else d.upper()
                else:
                    url_node = None
                if url_node is not None:
                    tmpl = _template(url_node, local)
                    m = re.match(r"^<<([^$>][^>]*)>>(.*)$", tmpl)
                    if m and m.group(1) in uri_map:
                        base = uri_map[m.group(1)]
                        bm = re.match(r"^(?:https?://)?<<\$([^>]+)>>(.*)$", base)
                        if bm:
                            facts.outbound.append(OutboundCall(
                                fn.name, bm.group(1), pretty_path(bm.group(2) + m.group(2)), method, rel, n.lineno,
                                line_ev(f"{service}: {fn.name}() calls {bm.group(1)}"),
                                how=f'URL = app.config["{m.group(1)}"] = {base.replace("<<$", "${").replace(">>", "}")}'))
                            continue
                    facts.unresolved.append({"function": fn.name, "file": rel, "line": n.lineno,
                                             "code": lines[n.lineno - 1].strip(), "template": tmpl})
                # tokens
                if d in ("jwt.encode",):
                    facts.token_issuer.append(line_ev(f"{service} signs login tokens"))
                if d in ("jwt.decode",):
                    facts.token_verifier.append(line_ev(f"{service} verifies login tokens"))
                # database via SQLAlchemy table objects: self.users_table.insert()
                if isinstance(n.func, ast.Attribute) and last in ("insert", "select", "update", "delete"):
                    owner = _dotted(n.func.value)
                    if owner in table_attrs:
                        mode = "read" if last == "select" else "write"
                        facts.tables.append(TableUse(table_attrs[owner], mode, fn.name, rel, n.lineno,
                                                     line_ev(f"{service}: {fn.name}() {last}s {table_attrs[owner]}")))
            # raw SQL text
            for n in _own_nodes(fn):
                if (s := _const(n)) and re.match(r"\s*(SELECT|INSERT|UPDATE|DELETE)\b", s, re.I):
                    mode = "read" if s.strip().upper().startswith("SELECT") else "write"
                    for t in SQL_TABLE.findall(s):
                        facts.tables.append(TableUse(t.lower(), mode, fn.name, rel, n.lineno,
                                                     STORE.add("code", f"{service}: SQL on {t}", s.strip(), rel,
                                                               n.lineno, n.lineno, short)))
    return facts
