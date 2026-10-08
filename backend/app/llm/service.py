"""One way to ask the local model: evidence pack in, JSON out, cached. Verification is done by the callers."""
from __future__ import annotations

import hashlib

from .. import config
from ..engine.evidence import STORE
from ..store import Store
from .ollama_client import OllamaError, chat_json


def evidence_pack(ids, max_chars: int = 900, max_blocks: int = 12) -> tuple[str, dict[str, str]]:
    """Render evidence ids as labelled blocks for a prompt. Returns (text, {id: text})."""
    blocks, pack = [], {}
    for e in STORE.many(list(dict.fromkeys(i for i in ids if i)))[:max_blocks]:
        text = e.text if len(e.text) <= max_chars else e.text[:max_chars] + "\n...[truncated]"
        pack[e.id] = text
        blocks.append(f"[{e.id}] ({e.kind}) {e.location}\n{text}")
    return "\n\n".join(blocks), pack


def ask(store: Store, task: str, system: str, user: str, schema: dict, mode: str = "auto",
        model: str | None = None) -> tuple[dict | None, dict]:
    """mode: 'cache' = never call the model; 'auto' = cache, else call; 'force' = always call."""
    key = hashlib.sha256(f"{task}|{config.PROMPT_VERSION}|{system}|{user}".encode("utf-8")).hexdigest()
    if mode != "force":
        hit = store.cache_get(key)
        if hit:
            return hit["response"], {"status": "cached", "model": hit["model"], "seconds": hit["seconds"]}
        if mode == "cache":
            return None, {"status": "not_generated"}
    model = model or config.LIVE_MODEL
    try:
        resp, secs = chat_json(model, system, user, schema)
    except OllamaError as exc:
        return None, {"status": "unavailable", "error": str(exc)[:200]}
    store.cache_put(key, task, model, resp, secs)
    return resp, {"status": "generated", "model": model, "seconds": round(secs, 1)}
