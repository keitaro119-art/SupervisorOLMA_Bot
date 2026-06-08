# =========================
# services/rate_limit_service.py
# Control simple de rate limit por chat/user (Pro+)
# =========================

import time
import threading
from typing import Dict, Tuple

from utils.logger import log_event


# =========================
# STORAGE
# =========================
_hits: Dict[Tuple[str, int], list[float]] = {}
_lock = threading.Lock()


# =========================
# CORE
# =========================
def is_allowed(scope: str, entity_id: int, limit: int, window_sec: int) -> bool:
    """
    scope: 'chat' o 'user' o cualquier etiqueta
    entity_id: chat_id / user_id
    limit: máximo de eventos permitidos
    window_sec: ventana en segundos
    """
    now = time.time()
    key = (scope, int(entity_id))

    with _lock:
        arr = _hits.get(key, [])
        arr = [ts for ts in arr if (now - ts) <= window_sec]

        if len(arr) >= limit:
            _hits[key] = arr
            log_event(
                "RATE_LIMIT_BLOCK",
                scope=scope,
                entity_id=entity_id,
                limit=limit,
                window_sec=window_sec,
            )
            return False

        arr.append(now)
        _hits[key] = arr
        return True


def get_remaining(scope: str, entity_id: int, limit: int, window_sec: int) -> int:
    now = time.time()
    key = (scope, int(entity_id))

    with _lock:
        arr = _hits.get(key, [])
        arr = [ts for ts in arr if (now - ts) <= window_sec]
        _hits[key] = arr
        return max(0, limit - len(arr))


def reset_entity(scope: str, entity_id: int) -> None:
    key = (scope, int(entity_id))
    with _lock:
        _hits.pop(key, None)

    log_event("RATE_LIMIT_RESET", scope=scope, entity_id=entity_id)


def clear_all() -> None:
    with _lock:
        _hits.clear()

    log_event("RATE_LIMIT_CLEAR_ALL")


def stats() -> dict:
    now = time.time()
    active = 0

    with _lock:
        for key, arr in list(_hits.items()):
            valid = [ts for ts in arr if (now - ts) <= 3600]
            if valid:
                active += 1
                _hits[key] = valid
            else:
                _hits.pop(key, None)

    return {
        "active_buckets": active,
    }