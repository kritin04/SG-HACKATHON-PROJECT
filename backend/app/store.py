"""SQLite persistence: baselines, doc decisions, LLM cache, audit trail."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (
    cr_key TEXT PRIMARY KEY, ref TEXT, sha TEXT, included TEXT, excluded TEXT, added TEXT,
    report TEXT, confirmed_by TEXT, confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS doc_decisions (
    finding_id TEXT PRIMARY KEY, action TEXT, final_text TEXT, reason TEXT, decided_by TEXT,
    decided_at TEXT, commit_sha TEXT);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY, task TEXT, model TEXT, response TEXT, seconds REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT, target TEXT, detail TEXT);
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

    def _exec(self, sql: str, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def _one(self, sql: str, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    # ---- audit ----------------------------------------------------------
    def audit(self, actor: str, action: str, target: str, detail: dict | str = "") -> None:
        self._exec("INSERT INTO audit (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                   (now(), actor, action, target, json.dumps(detail) if isinstance(detail, dict) else detail))

    def audit_log(self, limit: int = 200) -> list[dict]:
        rows = self._all("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) | {"detail": _maybe_json(r["detail"])} for r in rows]

    # ---- baselines ------------------------------------------------------
    def save_baseline(self, cr_key: str, ref: str, sha: str, included: list[str], excluded: list[str],
                      added: list[str], report: dict, user: str) -> dict:
        self._exec("INSERT OR REPLACE INTO baselines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (cr_key, ref, sha, json.dumps(included), json.dumps(excluded), json.dumps(added),
                    json.dumps(report), user, now()))
        self.audit(user, "baseline_confirmed", cr_key, {"included": len(included), "excluded": excluded, "added": added})
        return self.baseline(cr_key)

    def baseline(self, cr_key: str) -> dict | None:
        r = self._one("SELECT * FROM baselines WHERE cr_key = ?", (cr_key,))
        if not r:
            return None
        return {"cr_key": r["cr_key"], "ref": r["ref"], "sha": r["sha"], "included": json.loads(r["included"]),
                "excluded": json.loads(r["excluded"]), "added": json.loads(r["added"]),
                "report": json.loads(r["report"]), "confirmed_by": r["confirmed_by"], "confirmed_at": r["confirmed_at"]}

    # ---- doc decisions --------------------------------------------------
    def save_decision(self, finding_id: str, action: str, final_text: str | None, reason: str | None,
                      user: str, commit_sha: str | None) -> None:
        self._exec("INSERT OR REPLACE INTO doc_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (finding_id, action, final_text, reason, user, now(), commit_sha))
        self.audit(user, f"doc_{action}", finding_id, {"reason": reason, "commit": commit_sha})

    def decisions(self) -> dict[str, dict]:
        return {r["finding_id"]: dict(r) for r in self._all("SELECT * FROM doc_decisions")}

    # ---- llm cache ------------------------------------------------------
    def cache_get(self, key: str) -> dict | None:
        r = self._one("SELECT * FROM llm_cache WHERE key = ?", (key,))
        return {"response": json.loads(r["response"]), "model": r["model"], "seconds": r["seconds"],
                "created_at": r["created_at"]} if r else None

    def cache_put(self, key: str, task: str, model: str, response: dict, seconds: float) -> None:
        self._exec("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?)",
                   (key, task, model, json.dumps(response), seconds, now()))

    def reset(self) -> None:
        with self.lock:
            self.conn.executescript("DELETE FROM baselines; DELETE FROM doc_decisions; DELETE FROM audit;")
            self.conn.commit()


def _maybe_json(s):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return s
