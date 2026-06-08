# =========================
# jobs/sheets_worker_job.py
# Worker programado para procesar la cola de Google Sheets
# =========================

import logging
from telegram.ext import ContextTypes

from config import (
    QUEUE_ENABLED,
    QUEUE_BATCH_SIZE,
)
from services.sheets_queue_service import (
    process_queue_batch,
    mark_worker_running,
    is_worker_running,
    queue_health_snapshot,
)
from utils.logger import log_event

logger = logging.getLogger("sheets_worker_job")


async def sheets_worker_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Job periódico que vacía la cola por lotes.
    Seguro contra solapamiento.
    """
    if not QUEUE_ENABLED:
        return

    if is_worker_running():
        logger.warning("Sheets worker omitido: ya hay una ejecución en curso.")
        return

    mark_worker_running(True)
    try:
        result = process_queue_batch(max_items=QUEUE_BATCH_SIZE)

        if result["processed"] or result["failed"] or result["moved_dead"]:
            log_event(
                "SHEETS_WORKER_RUN",
                processed=result["processed"],
                failed=result["failed"],
                dead=result["moved_dead"],
                remaining=result["remaining"],
            )

        health = queue_health_snapshot()
        if health["status"] != "healthy":
            logger.warning(
                "Queue health=%s queue_size=%s dead_letter=%s",
                health["status"],
                health["queue_size"],
                health["dead_letter_size"],
            )

    except Exception as e:
        logger.exception("Error en sheets_worker_job: %s", e)
    finally:
        mark_worker_running(False)