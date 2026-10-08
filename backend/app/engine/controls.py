"""Evaluate curated control rules against a set of impacted (or actually changed) things."""
from __future__ import annotations

import fnmatch
import re

from .catalog import Catalog


def evaluate_controls(cat: Catalog, *, paths: set[str], data_classes: dict[str, list[str]],
                      externals: set[str], text: str = "") -> list[dict]:
    """data_classes: class -> list of columns. externals: external system ids. Returns triggered controls."""
    hits = []
    low = text.lower()
    for c in cat.controls:
        reasons = []
        t = c.triggers
        for pat in t.paths:
            matched = sorted(p for p in paths if fnmatch.fnmatch(p, pat))
            if matched:
                reasons.append(f"Changes {', '.join(matched)} (rule: path {pat})")
        for cls in t.data_classes:
            if data_classes.get(cls):
                reasons.append(f"Touches {cls} data: {', '.join(sorted(data_classes[cls]))}")
        for x in t.external_systems:
            if x in externals:
                ext = cat.external(x)
                reasons.append(f"Affects downstream system {ext.name if ext else x}")
        for kw in t.keywords:
            if low and re.search(r"(?<![a-z])" + re.escape(kw.lower()) + r"(?![a-z])", low):
                reasons.append(f'Change request mentions "{kw}"')
        if reasons:
            hits.append({
                "id": c.id, "name": c.name, "description": c.description, "reasons": reasons, "tier": "curated",
                "required_evidence": [r.model_dump(exclude_none=True) for r in c.required_evidence],
                "approvers": sorted({p for r in c.required_evidence if r.role for p in cat.people_with_role(r.role)}),
                "evidence": [cat.evidence.get(f"control:{c.id}")],
            })
    return hits
