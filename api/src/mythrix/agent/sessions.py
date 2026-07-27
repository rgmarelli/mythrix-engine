"""Per-browser-session conversation + context state (specs/interfaces/agent.md FR-AG-20:
retained only for the life of the backend process, never persisted to disk)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from mythrix.agent.context import AgentContext


@dataclass
class SessionState:
    history: list = field(default_factory=list)
    context: AgentContext = field(default_factory=AgentContext)


class SessionStore:
    """In-memory `session_id -> SessionState`, plus a per-session lock
    guarding double-submit — the frontend disabling its composer while
    awaiting a reply is the primary defense (mirrors the app's existing
    `isQuerying` pattern); this lock is cheap insurance on top. Built once at
    `app.py`'s `lifespan` (cheap, never fails), unlike the lazily-built agent
    graph."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionState:
        with self._registry_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState()
            return self._sessions[session_id]

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._registry_lock:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]
