# =========================
# handlers/health_handler.py
# Monitoreo básico del bot en producción
# =========================

from telegram import Update
from telegram.ext import ContextTypes

from services.sheets_queue_service import queue_health_snapshot
from services.cache_service import cache_stats
from services.metrics_service import metrics_health
from services.rate_limit_service import stats as rate_limit_stats
from core.session_manager import get_active_sessions
from utils.logger import log_event


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /health
    Muestra estado general del bot
    """
    queue_data = queue_health_snapshot()
    cache_data = cache_stats()
    metrics_data = metrics_health()
    rl_data = rate_limit_stats()
    sessions = get_active_sessions()

    text = (
        "🩺 ESTADO DEL BOT\n\n"
        f"Queue status: {queue_data.get('status')}\n"
        f"Queue size: {queue_data.get('queue_size')}\n"
        f"Dead letter: {queue_data.get('dead_letter_size')}\n"
        f"Worker running: {queue_data.get('worker_running')}\n\n"
        f"Cache total: {cache_data.get('total')}\n"
        f"Cache valid: {cache_data.get('valid')}\n"
        f"Cache expired: {cache_data.get('expired')}\n\n"
        f"Metrics status: {metrics_data.get('status')}\n"
        f"Rate limit buckets: {rl_data.get('active_buckets')}\n"
        f"Sesiones activas: {len(sessions)}"
    )

    log_event(
        "HEALTH_CHECK",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=update.effective_user.id if update.effective_user else None,
    )

    await update.message.reply_text(text)


async def metrics_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /metrics
    Muestra métricas resumidas
    """
    data = metrics_health()
    metrics = data.get("metrics", {})

    if not metrics:
        await update.message.reply_text("📊 No hay métricas registradas aún.")
        return

    lines = ["📊 MÉTRICAS\n"]
    for name, m in metrics.items():
        lines.append(
            f"{name}\n"
            f"  count={m.get('count')}\n"
            f"  avg={m.get('avg_time')}\n"
            f"  max={m.get('max_time')}\n"
            f"  min={m.get('min_time')}\n"
        )

    await update.message.reply_text("\n".join(lines))