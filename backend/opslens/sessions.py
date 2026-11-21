"""Server-side, in-memory, TTL-bound investigation context (Phase 4).

Follow-up context is created ONLY by the server from validated report events and referenced by an
unguessable session id. The client can never submit history, evidence or prior answers, so it cannot
fabricate numbers that the agent would treat as verified. Nothing is persisted: restart = context gone.
"""
from __future__ import annotations

import secrets
import threading
import time

from .agent import HistoryItem


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600, max_sessions: int = 200, max_turns: int = 6):
        self.ttl, self.max_sessions, self.max_turns = ttl_seconds, max_sessions, max_turns
        self._s: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _purge(self):
        now = time.time()
        for k in [k for k, v in self._s.items() if now - v["touched"] > self.ttl]:
            del self._s[k]
        while len(self._s) > self.max_sessions:
            del self._s[min(self._s, key=lambda k: self._s[k]["touched"])]

    def exists(self, sid: str | None) -> bool:
        with self._lock:
            self._purge()
            return bool(sid) and sid in self._s

    def add_turn(self, sid: str | None, question: str, report: dict) -> tuple[str, int]:
        with self._lock:
            self._purge()
            if not sid or sid not in self._s:
                sid = secrets.token_urlsafe(24)
                self._s[sid] = {"turns": [], "touched": time.time()}
            sess = self._s[sid]
            summary = report["executive_summary"] + " " + " ".join(f["text"] for f in report["findings"])
            sess["turns"].append({"question": question, "summary": summary[:2400], "report": report, "evidence": report["evidence"]})
            del sess["turns"][:-self.max_turns]
            sess["touched"] = time.time()
            n = len(sess["turns"]) - 1
            self._purge()  # enforce max_sessions after insertion
            return sid, n

    def history(self, sid: str | None) -> list[HistoryItem]:
        with self._lock:
            self._purge()
            sess = self._s.get(sid or "")
            if not sess:
                return []
            return [HistoryItem(question=t["question"][:600], summary=t["summary"], evidence=t["evidence"][:20]) for t in sess["turns"]]

    def report(self, sid: str, n: int) -> dict | None:
        with self._lock:
            self._purge()
            sess = self._s.get(sid)
            if not sess or not (0 <= n < len(sess["turns"])):
                return None
            sess["touched"] = time.time()
            return sess["turns"][n]
