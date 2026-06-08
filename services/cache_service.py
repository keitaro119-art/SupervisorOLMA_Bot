# =========================
# services/cache_service.py
# Sistema de caché en memoria con TTL (Pro+)
# =========================

import time
import threading
from typing import Any, Dict, Optional

from utils.logger import log_event


# =========================
# STORAGE
# =========================
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


# =========================
# SET
# =========================
def set_cache(key: str, value: Any, ttl: int = 300):
    """
    Guarda un valor en cache con TTL (segundos)
    """
    expire_at = time.time() + ttl

    with _cache_lock:
        _cache[key] = {
            "value": value,
            "expire_at": expire_at
        }

    log_event("CACHE_SET", key=key, ttl=ttl)


# =========================
# GET
# =========================
def get_cache(key: str) -> Optional[Any]:
    """
    Obtiene valor del cache si no ha expirado
    """
    with _cache_lock:
        item = _cache.get(key)

        if not item:
            return None

        if time.time() > item["expire_at"]:
            # Expirado
            del _cache[key]
            log_event("CACHE_EXPIRED", key=key)
            return None

        return item["value"]


# =========================
# DELETE
# =========================
def delete_cache(key: str):
    with _cache_lock:
        if key in _cache:
            del _cache[key]
            log_event("CACHE_DELETE", key=key)


# =========================
# CLEAR ALL
# =========================
def clear_cache():
    with _cache_lock:
        _cache.clear()
    log_event("CACHE_CLEAR_ALL")


# =========================
# GET OR SET
# =========================
def get_or_set(key: str, ttl: int, fetch_func):
    """
    Obtiene del cache o ejecuta función para obtener y guardar
    """
    value = get_cache(key)

    if value is not None:
        log_event("CACHE_HIT", key=key)
        return value

    log_event("CACHE_MISS", key=key)

    value = fetch_func()
    set_cache(key, value, ttl)

    return value


# =========================
# STATS
# =========================
def cache_stats():
    now = time.time()

    with _cache_lock:
        total = len(_cache)
        valid = 0
        expired = 0

        for item in _cache.values():
            if now > item["expire_at"]:
                expired += 1
            else:
                valid += 1

    return {
        "total": total,
        "valid": valid,
        "expired": expired
    }