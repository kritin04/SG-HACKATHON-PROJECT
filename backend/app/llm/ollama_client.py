"""Minimal Ollama client using structured (JSON-schema) outputs."""
from __future__ import annotations

import json
import time

import httpx

from .. import config


class OllamaError(RuntimeError):
    pass


def health() -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"up": True, "models": models, "live_model": config.LIVE_MODEL,
                "live_model_ready": config.LIVE_MODEL in models}
    except Exception as exc:  # noqa: BLE001 - surface any connectivity problem as "down"
        return {"up": False, "models": [], "live_model": config.LIVE_MODEL, "live_model_ready": False, "error": str(exc)}


def chat_json(model: str, system: str, user: str, schema: dict, num_ctx: int = 8192) -> tuple[dict, float]:
    payload = {
        "model": model, "stream": False, "format": schema,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0.1, "num_ctx": num_ctx},
        "keep_alive": "30m",
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.LLM_TIMEOUT_SECONDS)
        r.raise_for_status()
        content = r.json()["message"]["content"]
        return json.loads(content), time.time() - t0
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
        raise OllamaError(str(exc)) from exc
