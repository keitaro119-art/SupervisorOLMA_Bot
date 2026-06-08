# =========================
# services/sheets_queue_service.py
# Cola avanzada para Google Sheets (Pro+)
# =========================

import time
import threading
import logging
from typing import Dict, Any, List, Optional

from config import (
    QUEUE_ENABLED,
    QUEUE_BATCH_SIZE,
    QUEUE_MAX_RETRIES,
)
from services.google_sheets_service import append_dict
from utils.logger import log_event

logger = logging.getLogger("sheets_queue_service")


# =========================
# STORAGE EN MEMORIA
# =========================
_queue: List[Dict[str, Any]] = []
_dead_letter: List[Dict[str, Any]] = []
_queue_lock = threading.Lock()

_worker_running = False
_last_worker_run = 0.0


# =========================
# MÉTRICAS
# =========================
_metrics = {
    "enqueued_total": 0,
    "processed_total": 0,
    "failed_total": 0,
    "retried_total": 0,
    "dead_letter_total": 0,
}


def get_queue_metrics() -> Dict[str, Any]:
    with _queue_lock:
        return {
            **_metrics,
            "queue_size": len(_queue),
            "dead_letter_size": len(_dead_letter),
            "worker_running": _worker_running,
            "last_worker_run": _last_worker_run,
        }


def get_dead_letter_items() -> List[Dict[str, Any]]:
    with _queue_lock:
        return list(_dead_letter)


# =========================
# ENQUEUE
# =========================
def enqueue_row(sheet_name: str, data: Dict[str, Any], source: str = "app") -> None:
    item = {
        "sheet": sheet_name,
        "data": data,
        "source": source,
        "created_at": time.time(),
        "attempts": 0,
        "last_error": "",
    }

    with _queue_lock:
        _queue.append(item)
        _metrics["enqueued_total"] += 1

    log_event("QUEUE_ENQUEUE", sheet=sheet_name, source=source)


# =========================
# RETRY STRATEGY
# =========================
def _compute_backoff_seconds(attempts: int) -> float:
    attempts = max(1, attempts)
    return min(60.0, float(2 ** attempts))


def _is_ready_for_retry(item: Dict[str, Any]) -> bool:
    attempts = int(item.get("attempts", 0))
    if attempts <= 0:
        return True

    last_try = float(item.get("last_try_ts", 0.0))
    wait = _compute_backoff_seconds(attempts)
    return (time.time() - last_try) >= wait


# =========================
# PROCESS SINGLE ITEM
# =========================
def _process_item(item: Dict[str, Any]) -> bool:
    sheet = item["sheet"]
    data = item["data"]

    try:
        append_dict(sheet, data)

        with _queue_lock:
            _metrics["processed_total"] += 1

        log_event("QUEUE_PROCESSED", sheet=sheet)
        return True

    except Exception as e:
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["last_try_ts"] = time.time()
        item["last_error"] = str(e)

        with _queue_lock:
            _metrics["failed_total"] += 1
            if item["attempts"] < QUEUE_MAX_RETRIES:
                _metrics["retried_total"] += 1

        logger.warning(
            "QUEUE_PROCESS_ERROR sheet=%s attempts=%s error=%s",
            sheet,
            item["attempts"],
            e,
        )
        return False


# =========================
# PROCESS BATCH
# =========================
def process_queue_batch(max_items: Optional[int] = None) -> Dict[str, int]:
    global _last_worker_run

    max_items = max_items or QUEUE_BATCH_SIZE
    processed = 0
    failed = 0
    moved_dead = 0

    with _queue_lock:
        snapshot = list(_queue)

    if not snapshot:
        _last_worker_run = time.time()
        return {
            "processed": 0,
            "failed": 0,
            "moved_dead": 0,
            "remaining": 0,
        }

    handled_indexes = []

    for idx, item in enumerate(snapshot):
        if processed + failed >= max_items:
            break

        if not _is_ready_for_retry(item):
            continue

        ok = _process_item(item)
        handled_indexes.append(idx)

        if ok:
            processed += 1
        else:
            failed += 1

    # reconstruir cola
    with _queue_lock:
        new_queue = []
        for idx, item in enumerate(snapshot):
            if idx not in handled_indexes:
                new_queue.append(item)
                continue

            # procesado OK
            if item.get("last_error") == "":
                continue

            # dead letter
            if int(item.get("attempts", 0)) >= QUEUE_MAX_RETRIES:
                _dead_letter.append(item)
                _metrics["dead_letter_total"] += 1
                moved_dead += 1
            else:
                new_queue.append(item)

        _queue.clear()
        _queue.extend(new_queue)

    _last_worker_run = time.time()

    log_event(
        "QUEUE_BATCH_DONE",
        processed=processed,
        failed=failed,
        dead=moved_dead,
        remaining=len(_queue),
    )

    return {
        "processed": processed,
        "failed": failed,
        "moved_dead": moved_dead,
        "remaining": len(_queue),
    }


# =========================
# NUEVO: PROCESS ONCE (para /reintentar_envio)
# =========================
def process_queue_once() -> Dict[str, int]:
    """
    Ejecuta un batch manual de la cola
    """
    return process_queue_batch(max_items=QUEUE_BATCH_SIZE)


# =========================
# WORKER LOOP CONTROL
# =========================
def mark_worker_running(value: bool) -> None:
    global _worker_running
    _worker_running = value


def is_worker_running() -> bool:
    return _worker_running


# =========================
# MAINTENANCE
# =========================
def retry_dead_letter_item(index: int) -> bool:
    with _queue_lock:
        if index < 0 or index >= len(_dead_letter):
            return False

        item = _dead_letter.pop(index)
        item["attempts"] = 0
        item["last_error"] = ""
        item["last_try_ts"] = 0.0
        _queue.append(item)

    log_event("DEAD_LETTER_REQUEUED", index=index, sheet=item.get("sheet"))
    return True


def clear_dead_letter() -> int:
    with _queue_lock:
        count = len(_dead_letter)
        _dead_letter.clear()

    log_event("DEAD_LETTER_CLEARED", count=count)
    return count


def queue_health_snapshot() -> Dict[str, Any]:
    metrics = get_queue_metrics()

    status = "healthy"
    if metrics["dead_letter_size"] > 0:
        status = "warning"
    if metrics["queue_size"] > 200:
        status = "degraded"

    return {
        "status": status,
        **metrics,
    }