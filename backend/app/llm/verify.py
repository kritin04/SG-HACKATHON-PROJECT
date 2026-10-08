"""Deterministic verification of LLM output. The model is never trusted on its own."""
from __future__ import annotations

import re

HEADING = re.compile(r"^#{1,6}\s+", re.M)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower().strip("`'\".")


def check_citations(ids: list[str], pack: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (valid ids, issues)."""
    valid = [i for i in dict.fromkeys(ids or []) if i in pack]
    issues = [f"Unknown evidence id {i}" for i in dict.fromkeys(ids or []) if i not in pack]
    return valid, issues


def check_quote(quote: str, ids: list[str], pack: dict[str, str]) -> bool:
    q = _norm(quote)
    if len(q) < 3:
        return False
    return any(q in _norm(pack[i]) for i in ids)


def verify_claims(items: list[dict], pack: dict[str, str], known_names: set[str] | None = None) -> list[dict]:
    out, seen = [], set()
    for it in items or []:
        sig = _norm(it.get("text") or it.get("title") or "")
        if sig and sig in seen:
            continue
        seen.add(sig)
        ids, issues = check_citations(it.get("evidence_ids", []), pack)
        if not ids:
            issues.append("No valid evidence cited")
        if "quote" in it and not (ids and check_quote(it["quote"], ids, pack)):
            # the model may cite the wrong block: accept only if the quote is verbatim in another pack block
            other = [i for i in pack if i not in ids and check_quote(it["quote"], [i], pack)]
            if other and ids:  # never rescue a claim whose only citations were invalid
                ids = ids + other[:1]
                issues = [x for x in issues if x != "No valid evidence cited"]
                it = it | {"citation_corrected": True}
            else:
                issues.append("Quote not found verbatim in any evidence")
        if known_names is not None and it.get("target"):
            tgt = it["target"].split("(")[0].strip().strip("`").lower()
            if not any(tgt and (tgt == n or n.endswith("." + tgt) or tgt.endswith("." + n.split(".")[-1]) or tgt == n.split(".")[-1])
                       for n in known_names):
                issues.append(f"Target '{it['target']}' not found in the code index")
        out.append(it | {"evidence_ids": ids, "verified": not issues, "issues": issues})
    return out


def strip_inline_citations(text: str) -> str:
    """Remove raw evidence ids from model prose (the UI shows citations separately)."""
    text = re.sub(r"\(?\[?E-[0-9a-f]{6}\]?\)?", "", text)
    text = re.sub(r",?\s*(as per|per|according to|as shown in|see|based on)\s+the evidence(\s+in)?(\s|,|\band\b)*(?=[.;)]|$)",
                  "", text, flags=re.I)
    text = re.sub(r"(\s*,)+\s*(and\s*)?(?=[.;)])", "", text)
    text = re.sub(r"\s+([.,;])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def verify_doc_fix(original: str, updated: str, must_remove: list[str], must_add: list[str],
                   allow_new_headings: bool = False, keep_lines: list[str] | None = None) -> list[str]:
    issues = []
    updated_lines = {l.strip() for l in (updated or "").split("\n")}
    dropped = [l for l in keep_lines or [] if l.strip() not in updated_lines]
    if dropped:
        issues.append(f"Changed {len(dropped)} line(s) that did not need to change")
    if not updated or not updated.strip():
        return ["Empty section"]
    if original.strip().splitlines()[0].strip() != updated.strip().splitlines()[0].strip():
        issues.append("Heading line was changed")
    if not allow_new_headings and len(HEADING.findall(updated)) > len(HEADING.findall(original)):
        issues.append("New headings were added outside the section")
    for tok in must_remove:
        if tok in updated:
            issues.append(f"Still contains stale reference {tok}")
    for tok in must_add:
        if tok not in updated:
            issues.append(f"Missing required reference {tok}")
    if len(updated) > 3 * len(original) + 400:
        issues.append("Rewrite is much longer than the original section")
    return issues
