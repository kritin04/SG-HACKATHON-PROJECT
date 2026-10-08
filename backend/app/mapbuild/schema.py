"""Read database schemas from the SQL init scripts shipped with each database (CREATE TABLE ...)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..engine.evidence import STORE
from .project import Project

CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;", re.I | re.S)
NOT_COLUMN = {"primary", "foreign", "constraint", "unique", "check", "key", "index"}


@dataclass
class Table:
    db: str
    name: str
    columns: list[tuple[str, str]] = field(default_factory=list)   # (column, sql type)
    path: str = ""
    line: int = 1
    evidence: str = ""


def read_schemas(project: Project, databases: list[str]) -> dict[str, Table]:
    """Return {'<db>.<table>': Table}. A database's scripts live in src/**/<db>/**/*.sql."""
    tables: dict[str, Table] = {}
    short = project.sha[:7]
    for db in databases:
        for sql_file in sorted(project.source_dir.rglob(f"{db}/**/*.sql")):
            text = project.read(sql_file)
            for m in CREATE.finditer(text):
                name = m.group(1).lower()
                cols = []
                for raw in re.split(r",\s*\n", m.group(2)):
                    parts = raw.strip().split()
                    if len(parts) >= 2 and parts[0].lower() not in NOT_COLUMN:
                        cols.append((parts[0].lower(), parts[1].upper().rstrip(",")))
                line = text.count("\n", 0, m.start()) + 1
                rel = project.rel(sql_file)
                ev = STORE.add("schema", f"{db}: CREATE TABLE {name}", m.group(0).strip(), rel, line,
                               line + m.group(0).count("\n"), short)
                tables[f"{db}.{name}"] = Table(db, name, cols, rel, line, ev)
    return tables
