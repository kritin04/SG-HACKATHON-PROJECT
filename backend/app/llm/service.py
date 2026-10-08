"""LLM tasks: build a small evidence pack, call the local model, verify, cache."""
from __future__ import annotations

import hashlib

from .. import config
from ..engine.evidence import STORE
from ..store import Store
from . import prompts
from .ollama_client import OllamaError, chat_json
from .verify import strip_inline_citations, verify_claims, verify_doc_fix

MAX_BLOCK_CHARS = 900
MAX_BLOCKS = 10


def _pack(ids: list[str]) -> tuple[str, dict[str, str]]:
    blocks, pack = [], {}
    for e in STORE.many(list(dict.fromkeys(i for i in ids if i)))[:MAX_BLOCKS]:
        text = e.text if len(e.text) <= MAX_BLOCK_CHARS else e.text[:MAX_BLOCK_CHARS] + "\n...[truncated]"
        pack[e.id] = text
        blocks.append(f"[{e.id}] ({e.kind}) {e.location}\n{text}")
    return "\n\n".join(blocks), pack


def _key(task: str, prompt: str) -> str:
    return hashlib.sha256(f"{task}|{config.PROMPT_VERSION}|{prompt}".encode("utf-8")).hexdigest()


class LLMService:
    def __init__(self, store: Store):
        self.store = store

    def _run(self, task: str, system: str, user: str, schema: dict, mode: str, model: str | None):
        """mode: 'cache' (never call the model), 'auto' (cache, else call), 'force' (always call)."""
        key = _key(task, user)
        if mode != "force":
            hit = self.store.cache_get(key)
            if hit:
                return hit["response"], {"status": "cached", "model": hit["model"], "seconds": hit["seconds"],
                                         "generated_at": hit["created_at"]}
            if mode == "cache":
                return None, {"status": "not_generated"}
        model = model or config.LIVE_MODEL
        try:
            resp, secs = chat_json(model, system, user, schema)
        except OllamaError as exc:
            return None, {"status": "unavailable", "error": str(exc)[:200]}
        self.store.cache_put(key, task, model, resp, secs)
        return resp, {"status": "generated", "model": model, "seconds": round(secs, 1)}

    # ---- impact brief ----------------------------------------------------------
    def impact_brief(self, report: dict, known_names: set[str], mode: str = "cache", model: str | None = None) -> dict:
        ids = [report["cr"]["evidence"]]
        for it in report["code"][:5]:
            ids += [e for e in it["evidence"] if e.startswith("E-") and STORE.get(e) and STORE.get(e).kind == "code"][:1]
        ids += [e for x in report["external"] for e in x["evidence"] if STORE.get(e) and STORE.get(e).kind == "catalog"][:2]
        ids += [c["evidence"][0] for c in report["controls"] if c["evidence"][0]]
        ids += [g["evidence"][0] for g in report["tests"]["gaps"][:2] if g["evidence"]]
        evidence, pack = _pack(ids)
        r = report
        facts = "\n".join([
            f"- Risk: {r['risk']['level']} ({'; '.join(r['risk']['reasons'])})",
            "- Impacted code: " + ", ".join(f"{i['label']} ({i['confidence']})" for i in r["code"]),
            "- Downstream systems: " + (", ".join(x["label"] for x in r["external"]) or "none"),
            "- Data: " + (", ".join(f"{d['label']}{' [' + ', '.join(d.get('classifications') or []) + ']' if d.get('classifications') else ''}" for d in r["data"]) or "none"),
            "- Controls triggered: " + (", ".join(f"{c['id']} {c['name']}" for c in r["controls"]) or "none"),
            "- Modules without tests: " + (", ".join(g["label"] for g in r["tests"]["gaps"]) or "none"),
        ])
        cr = f"{r['cr']['key']}: {r['cr']['summary']}\n{r['cr']['description']}"
        user = prompts.IMPACT_USER.format(cr=cr, facts=facts, evidence=evidence)
        resp, meta = self._run("impact_brief", prompts.IMPACT_SYSTEM, user, prompts.IMPACT_SCHEMA, mode, model)
        if not resp:
            return meta | {"summary": None, "key_risks": [], "suggested_tests": []}
        risks = verify_claims(resp.get("key_risks", []), pack)
        tests = verify_claims(resp.get("suggested_tests", []), pack, known_names)
        return meta | {"summary": strip_inline_citations(resp.get("summary", "")), "key_risks": risks, "suggested_tests": tests,
                       "evidence_pack": list(pack), "verified_count": sum(x["verified"] for x in risks + tests),
                       "total_count": len(risks) + len(tests)}

    # ---- release review brief -------------------------------------------------
    def review_brief(self, rec: dict, mode: str = "cache", model: str | None = None) -> dict:
        ids = [rec["pr"]["evidence"]]
        for s in rec["code"]["surprise"]:
            ids += s["evidence"][:2]
        for m in rec["code"]["missed"]:
            ids += m["evidence"][:1]
        ids += [c["evidence"][0] for c in rec["controls"] if not c["satisfied"]]
        evidence, pack = _pack(ids)
        facts = "\n".join([f"- Matched plan: {', '.join(c['label'] for c in rec['code']['confirmed']) or 'none'}"] +
                          [f"- [{a['severity']}] {a['text']}" for a in rec["verdict"]["actions"]])
        user = prompts.REVIEW_USER.format(pr=f"#{rec['pr']['number']} {rec['pr']['title']}", facts=facts, evidence=evidence)
        resp, meta = self._run("review_brief", prompts.REVIEW_SYSTEM, user, prompts.REVIEW_SCHEMA, mode, model)
        if not resp:
            return meta | {"summary": None}
        cited = verify_claims([{"evidence_ids": resp.get("evidence_ids", [])}], pack)[0]
        return meta | {"summary": strip_inline_citations(resp.get("summary", "")), "evidence_ids": cited["evidence_ids"],
                       "verified": cited["verified"], "issues": cited["issues"]}

    # ---- doc fix ----------------------------------------------------------------
    def doc_fix(self, finding: dict, rule_draft: str, must_remove: list[str], must_add: list[str],
                mode: str = "cache", model: str | None = None) -> dict:
        evidence, pack = _pack(finding["evidence"])
        user = prompts.DOC_USER.format(title=finding["title"].replace("`", ""), explanation=finding["explanation"],
                                       doc_path=finding["doc_path"], section=finding["section_text"],
                                       draft=rule_draft, evidence=evidence)
        resp, meta = self._run("doc_fix", prompts.DOC_SYSTEM, user, prompts.DOC_SCHEMA, mode, model)
        if not resp:
            return meta | {"updated_section": None}
        updated = (resp.get("updated_section") or "").strip("\n")
        draft_lines = set(rule_draft.split("\n"))
        keep = [l for l in finding["section_text"].split("\n") if l.strip() and l in draft_lines]
        issues = verify_doc_fix(finding["section_text"], updated, must_remove, must_add,
                                allow_new_headings=finding["detector"] == "route_undocumented", keep_lines=keep)
        cited = verify_claims([{"evidence_ids": resp.get("evidence_ids", [])}], pack)[0]
        return meta | {"updated_section": updated, "change_summary": resp.get("change_summary", ""),
                       "evidence_ids": cited["evidence_ids"], "verified": not issues, "issues": issues}
