"""Self-Healing Documentation: detect stale/missing docs after code changes and draft fixes."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from .. import config
from .core import Engine
from .evidence import STORE
from .gitrepo import hunks_for_lines
from .indexer import DocSection, Index


def _fid(*parts: str) -> str:
    return "DOC-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:6].upper()


def _sym_hunk_evidence(engine: Engine, base: str, head: str, path: str, start: int, end: int, side: str, title: str) -> str:
    patch = engine.repo.run("diff", "-U3", engine.repo.rev(base), engine.repo.rev(head), "--", path)
    text = hunks_for_lines(patch, start, end, side) or patch
    return STORE.add("diff", title, text, path, start, end, engine.repo.rev(head)[:7])


def _finding(kind, detector, section: DocSection, token, replacement, title, explanation, severity, evidence, **extra):
    return {
        "id": _fid(detector, section.id, token), "kind": kind, "detector": detector, "title": title,
        "doc_path": section.path, "section_id": section.id, "section_heading": section.heading,
        "section_text": section.text, "section_start": section.start, "section_end": section.end,
        "token": token, "replacement": replacement, "explanation": explanation, "severity": severity,
        "evidence": [e for e in dict.fromkeys(evidence) if e], **extra,
    }


def _best_config_section(ix_d: Index) -> DocSection | None:
    scored = sorted(ix_d.docs.values(), key=lambda d: -sum(1 for b in d.backticks if re.match(r"^[A-Z][A-Z0-9_]{3,}$", b)))
    return scored[0] if scored and "|" in scored[0].text else (scored[0] if scored else None)


def detect_changes(engine: Engine, base: str, head: str, docs_ref: str, story: str | None = None,
                   pr_number: int | None = None) -> list[dict]:
    ix_b, ix_h, ix_d = engine.index(base), engine.index(head), engine.index(docs_ref)
    findings: dict[str, dict] = {}
    story_ev = engine.issue_evidence(story) if story and story in engine.jira else None
    pr_ev = engine.pr_evidence(pr_number) if pr_number in engine.prs else None
    ctx = {"story": story, "pr": pr_number}

    def add(f):
        findings.setdefault(f["id"], f | ctx)

    # 1/2. removed, renamed or re-signatured functions still named in docs
    base_syms = {s.id: s for s in ix_b.code_symbols()}
    head_syms = {s.id: s for s in ix_h.code_symbols()}
    for sid, old in base_syms.items():
        new = head_syms.get(sid)
        if new is None:
            candidates = [s for s in head_syms.values() if s.module == old.module and s.id not in base_syms]
            candidates.sort(key=lambda s: -len(set(s.params) & set(old.params)))
            new_sym = candidates[0] if candidates and set(candidates[0].params) & set(old.params) else None
            ev = _sym_hunk_evidence(engine, base, head, old.path, old.start, old.end, "old", f"{old.name} removed")
            for sec in ix_d.docs_mentioning(old.name):
                if new_sym:
                    add(_finding("stale", "symbol_renamed", sec, old.name, new_sym.signature,
                                 f"`{old.name}` was renamed to `{new_sym.name}`",
                                 f"The doc names `{old.name}`, which no longer exists. The code now uses "
                                 f"`{new_sym.signature}` in {new_sym.path}.",
                                 "high", [sec.evidence_id, ev, new_sym.evidence_id, story_ev, pr_ev]))
                else:
                    add(_finding("stale", "symbol_removed", sec, old.name, None, f"`{old.name}` no longer exists",
                                 f"The doc names `{old.name}`, which was removed from {old.path}.",
                                 "high", [sec.evidence_id, ev, story_ev, pr_ev]))
        elif new.params != old.params:
            for sec in ix_d.docs_mentioning(old.name):
                documented = [b for b in sec.backticks if b.startswith(f"{old.name}(")]
                if documented and all(b.replace(" ", "") != new.signature.replace(" ", "") for b in documented):
                    ev = _sym_hunk_evidence(engine, base, head, new.path, new.start, new.end, "new", f"{new.name} signature")
                    add(_finding("stale", "signature_changed", sec, old.name, new.signature,
                                 f"`{old.name}` signature changed",
                                 f"The doc shows `{documented[0]}` but the code is now `{new.signature}`.",
                                 "medium", [sec.evidence_id, ev, new.evidence_id, story_ev, pr_ev]))

    # 3/4. API response fields and routes
    r_b, r_h = ix_b.routes(), ix_h.routes()
    for route, old in r_b.items():
        new = r_h.get(route)
        secs = [d for d in ix_d.docs.values() if route in d.routes]
        if new is None:
            for sec in secs:
                add(_finding("stale", "route_removed", sec, route, None, f"API {route} was removed",
                             f"The doc describes {route}, which no longer exists.", "high",
                             [sec.evidence_id, old.evidence_id, story_ev, pr_ev]))
            continue
        removed = old.response_fields - new.response_fields
        added = new.response_fields - old.response_fields
        for field in sorted(removed):
            for sec in secs:
                if field in sec.backticks:
                    repl = sorted(added)[0] if len(added) == 1 else None
                    ev = _sym_hunk_evidence(engine, base, head, new.path, new.start, new.end, "new", f"{route} response")
                    add(_finding("stale", "response_field_changed", sec, field, repl,
                                 f"{route} no longer returns `{field}`" + (f" (now `{repl}`)" if repl else ""),
                                 f"The API doc lists response field `{field}` for {route}, but the handler "
                                 f"`{new.name}` now returns {', '.join(f'`{f}`' for f in sorted(new.response_fields))}.",
                                 "high", [sec.evidence_id, ev, story_ev, pr_ev]))
    doc_route_targets = [d for d in ix_d.docs.values() if d.routes]
    for route, new in r_h.items():
        if route not in r_b and not any(route in d.routes for d in ix_d.docs.values()) and doc_route_targets:
            sec = next((d for d in doc_route_targets if d.level == 1), doc_route_targets[0])
            add(_finding("missing", "route_undocumented", sec, route, new.signature, f"New API {route} is not documented",
                         f"{route} (handled by `{new.name}` in {new.path}) was added but no document describes it.",
                         "high", [new.evidence_id, sec.evidence_id, story_ev, pr_ev]))

    # 5/6. configuration keys
    c_b, c_h = ix_b.config_keys(), ix_h.config_keys()
    for key in sorted(set(c_h) - set(c_b)):
        if not any(key in d.backticks or key in d.names for d in ix_d.docs.values()):
            sec = _best_config_section(ix_d)
            if sec:
                user = c_h[key][0]
                ev = _sym_hunk_evidence(engine, base, head, user.path, user.start, user.end, "new", f"{key} read by {user.name}")
                add(_finding("missing", "config_undocumented", sec, key, ix_h.config_default(key),
                             f"New config key `{key}` is not documented",
                             f"`{user.name}` in {user.path} now reads `{key}`"
                             + (f" (default {ix_h.config_default(key)})" if ix_h.config_default(key) else "")
                             + ", but no document mentions it.", "medium", [ev, sec.evidence_id, story_ev, pr_ev]))
    for key in sorted(set(c_b) - set(c_h)):
        for sec in ix_d.docs_mentioning(key):
            add(_finding("stale", "config_removed", sec, key, None, f"Config key `{key}` is no longer used",
                         f"The doc mentions `{key}`, which the code no longer reads.", "medium",
                         [sec.evidence_id, story_ev, pr_ev]))
    return list(findings.values())


def scan_completed_work(engine: Engine, docs_ref: str = config.MAIN_REF) -> list[dict]:
    """Run detectors for every Done Jira story with a merged PR, against the docs as they are now."""
    out: dict[str, dict] = {}
    for key, issue in engine.jira.items():
        f = issue["fields"]
        if f["status"]["name"] != "Done":
            continue
        for n in f.get("linked_prs", []):
            pr = engine.prs.get(n)
            if not pr or pr["state"] != "merged":
                continue
            docs_touched = any(d.path.startswith("docs/") for d in engine.repo.diff(pr["base"]["rev"], pr["head"]["rev"]))
            for fd in detect_changes(engine, pr["base"]["rev"], pr["head"]["rev"], docs_ref, key, n):
                fd["story_summary"] = f["summary"]
                fd["story_resolved"] = f.get("resolutiondate")
                fd["docs_touched_in_pr"] = docs_touched
                out.setdefault(fd["id"], fd)
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out.values(), key=lambda x: (order.get(x["severity"], 3), x["doc_path"]))


# ---------------------------------------------------------------------------- drafting
def rule_based_draft(f: dict) -> str:
    """Deterministic fix for a finding; the AI may polish it, the verifier checks both."""
    text = f["section_text"]
    tok, repl = f["token"], f["replacement"]
    det = f["detector"]
    if det in ("symbol_renamed", "signature_changed") and repl:
        text = re.sub(r"`" + re.escape(tok) + r"(\([^`]*\))?`", f"`{repl}`", text)
        return re.sub(r"(?<![`\w])" + re.escape(tok) + r"(?![\w`])", repl.split("(")[0], text)
    if det == "response_field_changed" and repl:
        return text.replace(f"`{tok}`", f"`{repl}`")
    if det == "config_undocumented":
        desc = f"Added by {f.get('story') or 'a recent change'}: {f.get('story_summary') or 'see linked change'}"
        row = f"| `{tok}` | {repl or '-'} | {desc} |"
        lines = text.rstrip("\n").split("\n")
        last_table = max((i for i, l in enumerate(lines) if l.strip().startswith("|")), default=None)
        if last_table is not None:
            lines.insert(last_table + 1, row)
        else:
            lines += ["", f"- `{tok}` (default {repl or '-'}): {desc}"]
        return "\n".join(lines)
    if det == "route_undocumented":
        method_path = tok
        return text.rstrip("\n") + f"\n\n## {method_path}\n\nHandled by `{repl}`. _Description pending review._"
    if det in ("symbol_removed", "route_removed", "config_removed"):
        return text.rstrip("\n") + f"\n\n> **Note:** `{tok}` was removed by {f.get('story') or 'a recent change'}; this section needs review."
    return text


def required_tokens(f: dict) -> tuple[list[str], list[str]]:
    """(tokens that must disappear, tokens that must appear) for a correct fix."""
    det, tok, repl = f["detector"], f["token"], f["replacement"]
    if det in ("symbol_renamed", "signature_changed") and repl:
        return ([f"`{tok}("] if det == "symbol_renamed" else []), [repl.split("(")[0]]
    if det == "response_field_changed" and repl:
        return [f"`{tok}`"], [f"`{repl}`"]
    if det == "config_undocumented":
        return [], [tok]
    if det == "route_undocumented":
        return [], [tok]
    return [], []


# ---------------------------------------------------------------------------- applying
def _merge_into_changed_section(current: str, old: str, new: str) -> str:
    """The section was already edited by an earlier approved fix: re-apply this fix's line delta to it."""
    lines = current.split("\n")
    heading = old.strip().split("\n")[0].strip()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        raise ValueError("The documented section no longer exists; re-scan and retry.") from None
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,6}\s", lines[i])), len(lines))
    section = lines[start:end]
    old_lines, new_lines = old.rstrip("\n").split("\n"), new.rstrip("\n").split("\n")
    removed = [l for l in old_lines if l not in new_lines]
    section = [l for l in section if l not in removed]
    for idx, line in enumerate(new_lines):
        if line in old_lines or line in section:
            continue
        prev = new_lines[idx - 1] if idx else heading
        pos = max((i for i, l in enumerate(section) if l == prev), default=None)
        if pos is None:
            # keep table rows together: insert after the last table row, else at the end of the content
            pos = max((i for i, l in enumerate(section) if l.strip().startswith("|")), default=len(section) - 1)
        section.insert(pos + 1, line)
    while section and not section[-1].strip() and end < len(lines):
        section.pop()
    tail = [""] if end < len(lines) else []
    return "\n".join(lines[:start] + section + tail + lines[end:])


def apply_fix(engine: Engine, f: dict, new_section: str, user: str) -> str:
    """Write the approved section into a git worktree on branch docs/auto-heal and commit it."""
    repo = engine.repo
    wt = config.WORKSPACE / "doc_heal_worktree"
    branch = "docs/auto-heal"
    if not (wt / ".git").exists():
        branches = repo.run("branch", "--list", branch).strip()
        if branches:
            repo.run("worktree", "add", str(wt), branch)
        else:
            repo.run("worktree", "add", "-b", branch, str(wt), config.MAIN_REF)
    target = Path(wt) / f["doc_path"]
    current = target.read_text(encoding="utf-8")
    old = f["section_text"]
    if old in current:
        updated = current.replace(old, new_section.rstrip("\n"), 1)
    else:
        updated = _merge_into_changed_section(current, old, new_section)
    target.write_text(updated, encoding="utf-8", newline="\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="Change Assurance Copilot", GIT_AUTHOR_EMAIL="copilot@local",
               GIT_COMMITTER_NAME="Change Assurance Copilot", GIT_COMMITTER_EMAIL="copilot@local")
    msg = f"docs: {f['title'].replace('`', '')} ({f['id']})\n\nApproved by {user}. Related: {f.get('story') or '-'}"
    subprocess.run(["git", "add", f["doc_path"]], cwd=wt, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=wt, check=True, capture_output=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, check=True, capture_output=True, text=True).stdout.strip()
