"""Evidence records: every claim in the product points at one or more of these."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


@dataclass
class Evidence:
    id: str
    kind: str          # code | doc | diff | catalog | jira | pr | rule
    title: str
    text: str
    path: str | None = None
    start: int | None = None
    end: int | None = None
    ref: str | None = None  # short commit sha

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def location(self) -> str:
        loc = self.path or self.title
        if self.start:
            loc += f":{self.start}" + (f"-{self.end}" if self.end and self.end != self.start else "")
        if self.ref:
            loc += f" @{self.ref}"
        return loc


class EvidenceStore:
    def __init__(self):
        self._items: dict[str, Evidence] = {}

    def add(self, kind: str, title: str, text: str, path: str | None = None, start: int | None = None,
            end: int | None = None, ref: str | None = None) -> str:
        key = "|".join(str(x) for x in (kind, title, path, start, end, ref, text))
        eid = "E-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
        if eid not in self._items:
            self._items[eid] = Evidence(eid, kind, title, text, path, start, end, ref)
        return eid

    def get(self, eid: str) -> Evidence | None:
        return self._items.get(eid)

    def many(self, ids) -> list[Evidence]:
        return [self._items[i] for i in ids if i in self._items]


STORE = EvidenceStore()
