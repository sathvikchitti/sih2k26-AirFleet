"""Store bootstrap: deterministic in-memory state plus the id generator.

Split out of the repositories so every repository shares exactly one lock and
one source of truth.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from functools import wraps

from .. import data

_LOCK = threading.RLock()
_STATE: dict = {}


def store() -> dict:
    """The live state collection. Read-only access goes through repositories."""
    if not _STATE:
        reset()
    return _STATE


def reset() -> dict:
    """Restore the deterministic demo dataset."""
    with _LOCK:
        _STATE.clear()
        _STATE.update(data.build_seed())
    return _STATE


def snapshot() -> dict:
    """Deep copy of all state — used by tests and the demo export."""
    with _LOCK:
        return deepcopy(_STATE)


def lock() -> threading.RLock:
    return _LOCK


def state_locked(function):
    """Serialize a complete in-memory state transition across service calls."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _LOCK:
            return function(*args, **kwargs)
    return wrapped


def next_id(kind: str, prefix: str, width: int = 4) -> str:
    """Monotonic id generator.

    `prefix` is used verbatim so callers can include their own separator:
    next_id('work_order_seq', 'WO-') -> 'WO-1046'.
    """
    with _LOCK:
        seq = _STATE.get(kind, 1000)
        _STATE[kind] = seq + 1
        return f"{prefix}{seq:0{width}d}"
