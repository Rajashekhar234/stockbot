"""
Process-wide mutable bot state controllable via Telegram.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class _State:
    paused: bool = False        # /pause → True, /resume → False
    stop_signal: bool = False   # /stop  → True (orchestrator exits at next loop)
    reason: str = ""


_state = _State()
_lock = Lock()


def is_paused() -> bool:
    with _lock:
        return _state.paused


def is_stopping() -> bool:
    with _lock:
        return _state.stop_signal


def pause(reason: str = "") -> None:
    with _lock:
        _state.paused = True
        _state.reason = reason


def resume() -> None:
    with _lock:
        _state.paused = False
        _state.reason = ""


def request_stop(reason: str = "") -> None:
    with _lock:
        _state.stop_signal = True
        _state.reason = reason


def snapshot() -> dict:
    with _lock:
        return {"paused": _state.paused, "stopping": _state.stop_signal,
                "reason": _state.reason}
