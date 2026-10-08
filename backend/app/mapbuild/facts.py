"""Facts extracted from one service's source code (language-independent shape)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Function:
    name: str              # e.g. "payment" or "LedgerWriterController.addTransaction"
    file: str
    start: int
    end: int
    evidence: str
    calls: set[str] = field(default_factory=set)   # simple names of functions/methods called


@dataclass
class Endpoint:
    method: str
    path: str              # display form, e.g. /contacts/{username}
    function: str
    file: str
    line: int
    evidence: str


@dataclass
class OutboundCall:
    function: str          # caller function name
    env_var: str           # e.g. BALANCES_API_ADDR
    path: str              # full path template, e.g. /balances/{}
    method: str | None     # None = could not be determined from the call itself
    file: str
    line: int
    evidence: str
    how: str = ""          # short explanation of how it was resolved


@dataclass
class TableUse:
    table: str             # lower-case table name
    mode: str              # read | write
    function: str
    file: str
    line: int
    evidence: str
    columns: set[str] = field(default_factory=set)


@dataclass
class EnvRead:
    name: str
    file: str
    line: int
    evidence: str


@dataclass
class TestCase:
    name: str
    file: str
    line: int
    evidence: str
    paths: list[tuple[str, str]] = field(default_factory=list)   # (METHOD, path) requested by the test
    calls: set[str] = field(default_factory=set)


@dataclass
class ServiceFacts:
    service: str
    language: str
    src_dir: str
    files: list[str] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    outbound: list[OutboundCall] = field(default_factory=list)
    tables: list[TableUse] = field(default_factory=list)
    env: list[EnvRead] = field(default_factory=list)
    tests: list[TestCase] = field(default_factory=list)
    token_issuer: list[str] = field(default_factory=list)     # evidence ids where tokens are signed
    token_verifier: list[str] = field(default_factory=list)   # evidence ids where tokens are verified
    unresolved: list[dict] = field(default_factory=list)      # calls the parser could not resolve (for AI)
