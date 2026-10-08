"""The dependency map data model: nodes, edges, and the map that holds them.

Every edge says WHERE it came from (origin) and points at proof (evidence ids).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# node type -> zoom level (1 = system view ... 4 = data fields)
NODE_LEVEL = {"user": 1, "service": 1, "database": 1, "external": 1,
              "endpoint": 2, "table": 2, "config": 2,
              "function": 3, "test": 3,
              "column": 4}

# edge type -> plain-English verb shown on the map
EDGE_VERB = {
    "uses": "uses",
    "calls_api": "calls",
    "offers": "offers",
    "reads": "reads",
    "writes": "writes",
    "needs_config": "needs setting",
    "trusts_tokens_from": "trusts login tokens from",
    "handled_by": "handled by",
    "calls": "calls",
    "tests": "tests",
    "consumes": "reads (outside system)",
}

# where a fact came from
ORIGINS = ("code", "config", "schema", "catalog", "ai", "human")


@dataclass
class Node:
    id: str
    type: str
    label: str
    parent: str | None = None
    props: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    @property
    def level(self) -> int:
        return NODE_LEVEL.get(self.type, 3)

    def to_dict(self) -> dict:
        return asdict(self) | {"level": self.level}


@dataclass
class Edge:
    source: str
    target: str
    type: str
    origin: str = "code"
    confidence: float = 1.0
    details: list[str] = field(default_factory=list)     # e.g. ["POST /transactions"]
    evidence: list[str] = field(default_factory=list)
    props: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}|{self.type}|{self.target}"

    @property
    def verb(self) -> str:
        return EDGE_VERB.get(self.type, self.type)

    def to_dict(self) -> dict:
        return asdict(self) | {"id": self.id, "verb": self.verb}


class ProjectMap:
    def __init__(self, name: str, sha: str):
        self.name = name
        self.sha = sha
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}

    def add_node(self, nid: str, type: str, label: str, parent: str | None = None,
                 evidence: list[str] | None = None, **props) -> Node:
        node = self.nodes.get(nid)
        if node is None:
            node = self.nodes[nid] = Node(nid, type, label, parent)
        node.props.update({k: v for k, v in props.items() if v is not None})
        node.evidence.extend(e for e in evidence or [] if e and e not in node.evidence)
        return node

    def add_edge(self, source: str, target: str, type: str, origin: str = "code", confidence: float = 1.0,
                 detail: str | None = None, evidence: list[str] | None = None, **props) -> Edge | None:
        if source == target or source not in self.nodes or target not in self.nodes:
            return None
        e = Edge(source, target, type, origin, confidence)
        e = self.edges.setdefault(e.id, e)
        e.confidence = max(e.confidence, confidence)
        if detail and detail not in e.details:
            e.details.append(detail)
        e.evidence.extend(x for x in evidence or [] if x and x not in e.evidence)
        e.props.update(props)
        return e

    def out_edges(self, nid: str, type: str | None = None) -> list[Edge]:
        return [e for e in self.edges.values() if e.source == nid and (type is None or e.type == type)]

    def in_edges(self, nid: str, type: str | None = None) -> list[Edge]:
        return [e for e in self.edges.values() if e.target == nid and (type is None or e.type == type)]

    def of_type(self, type: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == type]

    def to_dict(self) -> dict:
        return {"name": self.name, "sha": self.sha,
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [e.to_dict() for e in self.edges.values()]}


def norm_path(path: str) -> str:
    """'/contacts/<username>' and '/contacts/{username}' -> '/contacts/{}' (for matching)."""
    import re
    return re.sub(r"(<[^>]+>|\{[^}]*\})", "{}", path.rstrip("/") or "/")


def pretty_path(path: str) -> str:
    """Flask '<username>' -> '{username}' so all endpoints display the same way."""
    import re
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", path)
