"""Curated catalog: knowledge that is not in the code (owners, outside systems, data labels, rules, glossary).

For the demo these files are SYNTHETIC (demo_data/catalog/*.yaml). At a bank they would be imported from the
application inventory, interface catalogue, data classification register and change-management policies.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .evidence import STORE


class ServiceInfo(BaseModel):
    owner: str = "Unknown"
    capability: str = "Other"
    criticality: str = "medium"


class ExternalSystem(BaseModel):
    id: str
    name: str
    description: str = ""
    consumes: list[str] = []
    owner: str = ""
    criticality: str = "medium"


class Control(BaseModel):
    id: str
    name: str
    when: str = ""
    triggers: dict = Field(default_factory=dict)
    requires: list[str] = []


class Term(BaseModel):
    term: str
    synonyms: list[str] = []
    targets: list[str] = []


class Catalog(BaseModel):
    services: dict[str, ServiceInfo] = {}
    external_systems: list[ExternalSystem] = []
    columns: dict[str, str] = {}
    controls: list[Control] = []
    terms: list[Term] = []
    evidence: dict[str, str] = {}

    def service(self, name: str) -> ServiceInfo:
        return self.services.get(name, ServiceInfo())

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
    for f in sorted(Path(directory).glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            if isinstance(v, list):
                merged.setdefault(k, []).extend(v)
            elif isinstance(v, dict):
                merged.setdefault(k, {}).update(v)
    cat = Catalog(**merged)

    def ev(key, title, obj, fname):
        cat.evidence[key] = STORE.add("catalog", title, yaml.safe_dump(obj, sort_keys=False).strip(),
                                      path=f"demo_data/catalog/{fname}")

    for name, info in cat.services.items():
        ev(f"service:{name}", f"Catalog: {name}", {name: info.model_dump()}, "services.yaml")
    for x in cat.external_systems:
        ev(f"ext:{x.id}", f"Catalog: outside system {x.name}", x.model_dump(), "external.yaml")
    for col, cls in cat.columns.items():
        ev(f"column:{col}", f"Catalog: {col} is {cls}", {col: cls}, "data_classification.yaml")
    for c in cat.controls:
        ev(f"control:{c.id}", f"Catalog: control {c.id}", c.model_dump(), "controls.yaml")
    for t in cat.terms:
        ev(f"term:{t.term}", f"Catalog: business term '{t.term}'", t.model_dump(), "glossary.yaml")
    return cat
