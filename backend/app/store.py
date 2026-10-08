"""SQLite persistence: key-value results (map enrichment, analyses), LLM cache, scope edits, audit trail."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, task TEXT, model TEXT, response TEXT, seconds REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS scope_edits (id INTEGER PRIMARY KEY AUTOINCREMENT, cr_key TEXT, node_id TEXT, action TEXT,
    verdict TEXT, note TEXT, user TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT, target TEXT, detail TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path = config.DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def _exec(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def _all(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # key-value JSON
    def get(self, key: str):
        rows = self._all("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else None

    def put(self, key: str, value) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES (?, ?, ?)", (key, json.dumps(value), now()))

    def delete_prefix(self, prefix: str) -> None:
        self._exec("DELETE FROM kv WHERE key LIKE ?", (prefix + "%",))

    # LLM cache
    def cache_get(self, key: str) -> dict | None:
        rows = self._all("SELECT * FROM llm_cache WHERE key = ?", (key,))
        if not rows:
            return None
        r = rows[0]
        return {"response": json.loads(r["response"]), "model": r["model"], "seconds": r["seconds"], "created_at": r["created_at"]}

    def cache_put(self, key: str, task: str, model: str, response: dict, seconds: float) -> None:
        self._exec("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?)",
                   (key, task, model, json.dumps(response), seconds, now()))

    # human scope edits on an impact analysis
    def add_scope_edit(self, cr_key, node_id, action, verdict, note, user) -> None:
        self._exec("INSERT INTO scope_edits (cr_key, node_id, action, verdict, note, user, at) VALUES (?,?,?,?,?,?,?)",
                   (cr_key, node_id, action, verdict, note, user, now()))
        self.audit(user, f"scope_{action}", cr_key, {"node": node_id, "verdict": verdict, "note": note})

    def scope_edits(self, cr_key: str) -> list[dict]:
        return self._all("SELECT * FROM scope_edits WHERE cr_key = ? ORDER BY id", (cr_key,))

    # audit
    def audit(self, actor, action, target, detail=None) -> None:
        self._exec("INSERT INTO audit (at, actor, action, target, detail) VALUES (?,?,?,?,?)",
                   (now(), actor, action, target, json.dumps(detail or {})))

    def audit_log(self, limit: int = 200) -> list[dict]:
        return self._all("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
