"""Request-local, user-safe progress events for streaming agent execution."""
from threading import Lock
from typing import Callable

_emitters: dict[str, Callable[[str, str], None]] = {}
_lock = Lock()


def set_emitter(session_id: str, emitter: Callable[[str, str], None] | None) -> None:
    with _lock:
        if emitter:
            _emitters[session_id] = emitter
        else:
            _emitters.pop(session_id, None)


def emit(session_id: str, step: str, label: str) -> None:
    with _lock:
        callback = _emitters.get(session_id)
    if callback:
        callback(step, label)
