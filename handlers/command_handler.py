# =========================
# handlers/command_handler.py
# Comandos supervisor / admin
# =========================

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from core.session_manager import (
    get_state,
    get_all_data,
    has_active_supervision,
    stop_supervision,
    force_close_supervision,
    release_group,
    reset_session,
)
from utils.logger import log_event
from services.google_sheets_service import clear_sheet_cache
from services.sheets_queue_service import (
    process_queue_once,
    queue_health_snapshot,
    get_queue_metrics,
)


# =========================
# HELPERS
# =========================
_ADMIN_STATUSES = {"administrator", "creator"}


def _is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and getattr(chat, "type", "") == "private")


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        status = str(getattr(member, "status", "")).strip().lower()
        return status in _ADMIN_STATUSES
    except Exception as e:
        log_event(
            "CMD_ADMIN_CHECK_ERROR",
            chat_id=getattr(chat, "id", None),
            user_id=getattr(user, "id", None),
            error=str(e),
        )
        return False


async def _require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id if update.effective_chat else None

    if _is_private_chat(update):
        await update.message.reply_text("⚠️ Este comando es solo para admins del grupo.")
        log_event("CMD_ADMIN_DENIED_PRIVATE", chat_id=chat_id)
        return False

    if not await _is_group_admin(update, context):
        await update.message.reply_text("⛔ Solo un admin del grupo puede usar este comando.")
        log_event(
            "CMD_ADMIN_DENIED",
            chat_id=chat_id,
            user_id=getattr(update.effective_user, "id", None),
        )
        return False

    return True


def _format_dt(ts: float) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return "-"


def _build_logs_text(chat_id: int) -> str:
    state = get_state(chat_id)
    data = get_all_data(chat_id)
    queue = get_queue_metrics()
    health = queue_health_snapshot()

    evidencias = data.get("evidencias", [])
    evid_count = len(evidencias) if isinstance(evidencias, list) else 0

    supervisor = str(data.get("supervisor", "") or "-").strip()
    empresa = str(data.get("empresa", "") or "-").strip()
    codigo = str(data.get("codigo_pedido", "") or "-").strip()
    tipo_sup = str(data.get("tipo_supervision", "") or "-").strip()
    tecnico_1 = str(data.get("tecnico_1_nombre", "") or "-").strip()

    lines = [
        "📄 RESUMEN DE DIAGNÓSTICO",
        "",
        f"Estado: {state}",
        f"Supervisión activa: {'SI' if has_active_supervision(chat_id) else 'NO'}",
        f"Supervisor: {supervisor}",
        f"Empresa: {empresa}",
        f"Código pedido: {codigo}",
        f"Tipo supervisión: {tipo_sup}",
        f"Técnico 1: {tecnico_1}",
        f"Evidencias cargadas: {evid_count}",
        "",
        "📤 COLA SHEETS",
        f"Estado cola: {health.get('status', '-')}",
        f"Pendientes: {queue.get('queue_size', 0)}",
        f"Dead letter: {queue.get('dead_letter_size', 0)}",
        f"Procesados total: {queue.get('processed_total', 0)}",
        f"Fallidos total: {queue.get('failed_total', 0)}",
        f"Reintentos total: {queue.get('retried_total', 0)}",
        f"Último worker: {_format_dt(queue.get('last_worker_run', 0.0))}",
    ]

    return "\n".join(lines)


# =========================
# /stop → cancelar supervisión actual
# =========================
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not has_active_supervision(chat_id):
        await update.message.reply_text("ℹ️ No hay una supervisión activa para cancelar.")
        log_event("CMD_STOP_NO_ACTIVE", chat_id=chat_id)
        return

    stop_supervision(chat_id)

    await update.message.reply_text("🛑 Supervisión cancelada.")
    log_event("CMD_STOP", chat_id=chat_id, user_id=getattr(update.effective_user, "id", None))


# =========================
# /forzar_cierre → cierre sin validación
# =========================
async def forzar_cierre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    if not has_active_supervision(chat_id):
        await update.message.reply_text("ℹ️ No hay una supervisión activa para cerrar.")
        log_event("CMD_FORZAR_CIERRE_NO_ACTIVE", chat_id=chat_id, user_id=user_id)
        return

    force_close_supervision(chat_id, closed_by_user_id=user_id)

    await update.message.reply_text("⚠️ Supervisión cerrada forzadamente.")
    log_event("CMD_FORZAR_CIERRE", chat_id=chat_id, user_id=user_id)


# =========================
# /reset → limpia TODO
# =========================
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    reset_session(chat_id)

    await update.message.reply_text("🔄 Bot reiniciado en este grupo.")
    log_event("CMD_RESET", chat_id=chat_id, user_id=user_id)


# =========================
# /liberar → desbloquea sin borrar data
# =========================
async def liberar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    release_group(chat_id)

    await update.message.reply_text("🔓 Grupo liberado. Ya puedes continuar o iniciar una nueva supervisión.")
    log_event("CMD_LIBERAR", chat_id=chat_id, user_id=user_id)


# =========================
# /reload_sheet → limpia cache
# =========================
async def reload_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    clear_sheet_cache()

    await update.message.reply_text("🔄 Datos recargados desde Google Sheets.")
    log_event("CMD_RELOAD_SHEET", chat_id=chat_id, user_id=user_id)


# =========================
# /reintentar_envio → fuerza cola
# =========================
async def reintentar_envio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    try:
        result = process_queue_once()
    except Exception as e:
        await update.message.reply_text("❌ Error al reintentar envío.")
        log_event("CMD_REINTENTAR_ERROR", chat_id=chat_id, user_id=user_id, error=str(e))
        return

    processed = int(result.get("processed", 0))
    failed = int(result.get("failed", 0))
    moved_dead = int(result.get("moved_dead", 0))
    remaining = int(result.get("remaining", 0))

    text = (
        "📤 Reintento ejecutado.\n\n"
        f"Procesados: {processed}\n"
        f"Fallidos: {failed}\n"
        f"Dead letter: {moved_dead}\n"
        f"Pendientes: {remaining}"
    )
    await update.message.reply_text(text)

    log_event(
        "CMD_REINTENTAR_ENVIO",
        chat_id=chat_id,
        user_id=user_id,
        processed=processed,
        failed=failed,
        dead=moved_dead,
        remaining=remaining,
    )


# =========================
# /logs → resumen diagnóstico
# =========================
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = getattr(update.effective_user, "id", None)

    if not await _require_admin(update, context):
        return

    text = _build_logs_text(chat_id)
    await update.message.reply_text(text)

    log_event("CMD_LOGS", chat_id=chat_id, user_id=user_id)