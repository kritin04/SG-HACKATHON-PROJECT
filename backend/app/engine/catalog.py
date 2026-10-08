"""Curated catalog: systems, owners, external consumers, glossary, data classification, controls."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .evidence import STORE


class System(BaseModel):
    id: str
    name: str
    paths: list[str]
    owners: list[str] = []
    criticality: str = "medium"


class ExternalSystem(BaseModel):
    id: str
    name: str
    description: str = ""
    consumes: list[str] = []
    owners: list[str] = []
    criticality: str = "medium"


class Term(BaseModel):
    term: str
    synonyms: list[str] = []
    entities: list[str] = []


class EvidenceRule(BaseModel):
    type: str  # approver_role | test_change | doc_change
    role: str | None = None
    paths: list[str] = []


class ControlTriggers(BaseModel):
    paths: list[str] = []
    keywords: list[str] = []
    data_classes: list[str] = []
    external_systems: list[str] = []


class Control(BaseModel):
    id: str
    name: str
    description: str = ""
    triggers: ControlTriggers = Field(default_factory=ControlTriggers)
    required_evidence: list[EvidenceRule] = []


class Person(BaseModel):
    name: str
    roles: list[str] = []


class Catalog(BaseModel):
    systems: list[System] = []
    components: dict[str, str] = {}
    people: dict[str, Person] = {}
    external_systems: list[ExternalSystem] = []
    terms: list[Term] = []
    columns: dict[str, str] = {}
    controls: list[Control] = []
    evidence: dict[str, str] = {}  # "system:<id>" / "ext:<id>" / "control:<id>" / "term:<t>" -> evidence id

    # ---- lookups -------------------------------------------------------
    def system_for_path(self, path: str) -> System | None:
        for s in self.systems:
            if any(fnmatch.fnmatch(path, p) for p in s.paths):
                return s
        return None

    def system(self, sid: str) -> System | None:
        return next((s for s in self.systems if s.id == sid), None)

    def external(self, xid: str) -> ExternalSystem | None:
        return next((x for x in self.external_systems if x.id == xid), None)

    def roles_of(self, login: str) -> list[str]:
        p = self.people.get(login)
        return p.roles if p else []

    def people_with_role(self, role: str) -> list[str]:
        return [login for login, p in self.people.items() if role in p.roles]

    def classes_for_columns(self, cols) -> dict[str, str]:
        return {c: self.columns[c] for c in cols if c in self.columns}

    def match_terms(self, text: str) -> list[tuple[Term, str]]:
        low = text.lower()
        hits = []
        for t in self.terms:
            for word in [t.term, *t.synonyms]:
                if re.search(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])", low):
                    hits.append((t, word))
                    break
        return hits


def load_catalog(directory: Path) -> Catalog:
    merged: dict = {}
    raw_files: dict[str, str] = {}
    for f in sorted(Path(directory).glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        raw_files[f.name] = text
        data = yaml.safe_load(text) or {}
        for k, v in data.items():
            if isinstance(v, list):
                merged.setdefault(k, []).extend(v)
            elif isinstance(v, dict):
                merged.setdefault(k, {}).update(v)
    cat = Catalog(**merged)

    def ev(key: str, title: str, obj, fname: str):
        text = yaml.safe_dump(obj, sort_keys=False).strip()
        cat.evidence[key] = STORE.add("catalog", title, text, path=f"catalog/{fname}")

    for s in cat.systems:
        ev(f"system:{s.id}", f"System: {s.name}", s.model_dump(), "systems.yaml")
    for x in cat.external_systems:
        ev(f"ext:{x.id}", f"External system: {x.name}", x.model_dump(), "external.yaml")
    for t in cat.terms:
        ev(f"term:{t.term}", f"Glossary: {t.term}", t.model_dump(), "glossary.yaml")
    for c in cat.controls:
        ev(f"control:{c.id}", f"Control {c.id}: {c.name}", c.model_dump(exclude_none=True), "controls.yaml")
    for col, cls in cat.columns.items():
        ev(f"column:{col}", f"Data classification: {col}", {col: cls}, "data_classification.yaml")
    return cat
