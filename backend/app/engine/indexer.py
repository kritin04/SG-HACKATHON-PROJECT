"""Index a repository at a git ref: code symbols and their resources, SQL, docs and tests.

Everything here is deterministic static analysis (Python `ast`, regex for SQL and Markdown).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .evidence import STORE
from .gitrepo import GitRepo

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER)\b", re.I)
SQL_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER)\b", re.I)
SQL_TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
SQL_ADD_COL = re.compile(r"\bADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
SQL_WORDS = set("""select from where insert into values update set delete create table alter add column primary key
text integer numeric date default sum count and or not null as on join in is left right inner outer group by order
limit varchar boolean timestamp""".split())
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BACKTICK = re.compile(r"`([^`]+)`")
ROUTE_MENTION = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s`|,]*)")
CONFIG_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


@dataclass
class Symbol:
    id: str              # sym:<module>.<qualname>  or test:<module>.<name>
    module: str
    name: str
    qualname: str
    kind: str            # function | test
    path: str
    start: int
    end: int
    signature: str
    params: list[str]
    evidence_id: str = ""
    raw_calls: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)        # resolved symbol ids
    routes: list[tuple[str, str]] = field(default_factory=list)
    response_fields: set[str] = field(default_factory=set)
    config_keys: set[str] = field(default_factory=set)
    tables_read: set[str] = field(default_factory=set)
    tables_written: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)      # "table.column"
    topics_pub: set[str] = field(default_factory=set)
    topics_sub: set[str] = field(default_factory=set)
    http_calls: list[tuple[str, str]] = field(default_factory=list)  # (METHOD, path)


@dataclass
class Module:
    id: str              # mod:<dotted>
    name: str
    path: str
    is_test: bool
    imports: dict[str, str] = field(default_factory=dict)  # alias -> dotted target
    symbols: list[str] = field(default_factory=list)
    constants: dict[str, dict] = field(default_factory=dict)  # module-level dict literals of str->str


@dataclass
class SqlFile:
    id: str              # file:<path>
    path: str
    tables_written: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)
    evidence_id: str = ""


@dataclass
class DocSection:
    id: str              # doc:<path>#<anchor>
    path: str
    heading: str
    level: int
    start: int
    end: int
    text: str
    backticks: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)       # identifiers (func names w/o args)
    routes: set[str] = field(default_factory=set)      # "METHOD /path"
    evidence_id: str = ""


@dataclass
class Index:
    ref: str
    sha: str
    modules: dict[str, Module] = field(default_factory=dict)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    sql_files: dict[str, SqlFile] = field(default_factory=dict)
    docs: dict[str, DocSection] = field(default_factory=dict)
    files: tuple[str, ...] = ()

    # -- convenience views ------------------------------------------------
    @property
    def short(self) -> str:
        return self.sha[:7]

    def code_symbols(self):
        return (s for s in self.symbols.values() if s.kind == "function")

    def tests(self):
        return (s for s in self.symbols.values() if s.kind == "test")

    def routes(self) -> dict[str, Symbol]:
        return {f"{m} {p}": s for s in self.code_symbols() for (m, p) in s.routes}

    def config_keys(self) -> dict[str, list[Symbol]]:
        out: dict[str, list[Symbol]] = {}
        for s in self.code_symbols():
            for k in s.config_keys:
                out.setdefault(k, []).append(s)
        return out

    def symbols_by_name(self) -> dict[str, list[Symbol]]:
        out: dict[str, list[Symbol]] = {}
        for s in self.code_symbols():
            out.setdefault(s.name, []).append(s)
        return out

    def symbols_in_lines(self, path: str, lines: set[int]) -> list[Symbol]:
        return [s for s in self.symbols.values() if s.path == path and any(s.start <= l <= s.end for l in lines)]

    def config_default(self, key: str) -> str | None:
        for m in self.modules.values():
            for consts in m.constants.values():
                if key in consts:
                    return consts[key]
        return None

    def docs_mentioning(self, token: str) -> list[DocSection]:
        return [d for d in self.docs.values() if token in d.names or token in d.backticks]


def module_name(path: str) -> str:
    return path[:-3].replace("/", ".").removesuffix(".__init__")


def dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _const_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def parse_sql(sql: str):
    """Return (tables, written_tables, columns{table.col})."""
    clean = re.sub(r"'[^']*'", "", sql)
    tables = {t.lower() for t in SQL_TABLE.findall(clean)}
    written = tables if SQL_WRITE.match(clean) else set()
    idents = set(re.findall(r"[a-z_][a-z0-9_]*", clean.lower())) - SQL_WORDS - tables
    cols = {f"{t}.{c}" for t in tables for c in idents}
    for c in SQL_ADD_COL.findall(clean):
        cols |= {f"{t}.{c.lower()}" for t in tables}
    return tables, written, cols


def _analyze_function(sym: Symbol, fn: ast.AST) -> None:
    for dec in getattr(fn, "decorator_list", []):
        if isinstance(dec, ast.Call):
            name = dotted(dec.func)
            arg = _const_str(dec.args[0]) if dec.args else None
            if arg and name.split(".")[-1] in HTTP_METHODS and name.startswith("router"):
                sym.routes.append((name.split(".")[-1].upper(), arg))
            elif arg and name.endswith("subscribe"):
                sym.topics_sub.add(arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            if name:
                sym.raw_calls.add(name)
            first = _const_str(node.args[0]) if node.args else None
            if first:
                if name.endswith("settings.get") or name in ("os.getenv", "os.environ.get"):
                    sym.config_keys.add(first)
                elif name.endswith("bus.publish"):
                    sym.topics_pub.add(first)
                elif name.split(".")[0] == "http" and name.split(".")[-1] in HTTP_METHODS and first.startswith("http"):
                    sym.http_calls.append((name.split(".")[-1].upper(), urlparse(first).path or "/"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL_START.match(node.value):
            tables, written, cols = parse_sql(node.value)
            sym.tables_written |= written
            sym.tables_read |= tables - written
            sym.columns |= cols
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            sym.response_fields |= {k for k in (_const_str(k) for k in node.value.keys) if k}


def _index_python(index: Index, path: str, source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    mname = module_name(path)
    is_test = path.startswith("tests/")
    mod = Module(f"mod:{mname}", mname, path, is_test)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                mod.imports[a.asname or a.name] = f"{node.module}.{a.name}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                mod.imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and len(node.targets) == 1:
            target = dotted(node.targets[0])
            pairs = {_const_str(k): _const_str(v) for k, v in zip(node.value.keys, node.value.values)}
            pairs = {k: v for k, v in pairs.items() if k and v is not None}
            if target and pairs:
                mod.constants[target] = pairs

    def add_fn(fn, prefix=""):
        qual = f"{prefix}{fn.name}"
        kind = "test" if is_test and fn.name.startswith("test") else "function"
        sid = f"{'test' if kind == 'test' else 'sym'}:{mname}.{qual}"
        start = fn.decorator_list[0].lineno if fn.decorator_list else fn.lineno
        sym = Symbol(sid, mname, fn.name, qual, kind, path, start, fn.end_lineno,
                     f"{fn.name}({ast.unparse(fn.args)})", [a.arg for a in fn.args.args])
        _analyze_function(sym, fn)
        sym.evidence_id = STORE.add("code", f"{mname}.{qual}", "\n".join(lines[start - 1:fn.end_lineno]),
                                    path, start, fn.end_lineno, index.short)
        index.symbols[sid] = sym
        mod.symbols.append(sid)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_fn(node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_fn(item, f"{node.name}.")
    index.modules[mod.id] = mod


def _resolve_calls(index: Index) -> None:
    for mod in index.modules.values():
        for sid in mod.symbols:
            sym = index.symbols[sid]
            for raw in sym.raw_calls:
                head, _, rest = raw.partition(".")
                candidates = []
                if head in mod.imports:
                    target = mod.imports[head] + (f".{rest}" if rest else "")
                    candidates.append(f"sym:{target}")
                candidates.append(f"sym:{mod.name}.{raw}")
                for c in candidates:
                    if c in index.symbols and c != sid:
                        sym.calls.add(c)
                        break


def _index_sql(index: Index, path: str, source: str) -> None:
    sf = SqlFile(f"file:{path}", path)
    for stmt in source.split(";"):
        if stmt.strip():
            tables, written, cols = parse_sql(stmt)
            sf.tables_written |= tables if written or re.match(r"\s*(CREATE|ALTER)", stmt, re.I) else set()
            sf.columns |= cols
    sf.evidence_id = STORE.add("code", path, source.strip(), path, 1, source.count("\n") + 1, index.short)
    index.sql_files[sf.id] = sf


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _index_markdown(index: Index, path: str, source: str) -> None:
    lines = source.splitlines()
    heads = [(i, HEADING.match(l)) for i, l in enumerate(lines)]
    heads = [(i, m) for i, m in heads if m]
    for n, (i, m) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        body = "\n".join(lines[i:end]).rstrip()
        sec = DocSection(f"doc:{path}#{_slug(m.group(2))}", path, m.group(2), len(m.group(1)), i + 1,
                         i + len(body.splitlines()), body)
        for tok in BACKTICK.findall(body):
            tok = tok.strip()
            sec.backticks.add(tok)
            base = tok.split("(")[0].strip()
            if IDENT.match(base):
                sec.names.add(base)
        sec.routes = {f"{m_} {p}" for m_, p in ROUTE_MENTION.findall(body)}
        sec.evidence_id = STORE.add("doc", f"{path} § {sec.heading}", body, path, sec.start, sec.end, index.short)
        index.docs[sec.id] = sec


def build_index(repo: GitRepo, ref: str) -> Index:
    sha = repo.rev(ref)
    index = Index(ref, sha, files=repo.ls_files(sha))
    for path in index.files:
        if path.endswith(".py"):
            _index_python(index, path, repo.show(sha, path) or "")
        elif path.endswith(".sql"):
            _index_sql(index, path, repo.show(sha, path) or "")
        elif path.endswith(".md") and path.startswith("docs/"):
            _index_markdown(index, path, repo.show(sha, path) or "")
    _resolve_calls(index)
    return index
