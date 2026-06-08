# =========================
# handlers/supervisor_handler.py
# Selección de supervisor (desde Google Sheets)
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data
from utils.logger import log_event
from services.google_sheets_service import get_supervisores
from services.cache_service import get_or_set


# =========================
# HELPERS
# =========================
def _is_active(value: str) -> bool:
    v = str(value or "").strip().lower()
    return v in ("1", "true", "si", "sí", "activo", "")


def _load_supervisores():
    return get_or_set(
        key="supervisores",
        ttl=180,
        fetch_func=get_supervisores,
    )


def _build_supervisores_keyboard(rows) -> InlineKeyboardMarkup:
    buttons = []

    for r in rows[:10]:
        nombre = str(
            r.get("nombre", "")
            or r.get("Nombre", "")
            or r.get("NOMBRE", "")
        ).strip()

        if not nombre:
            continue

        buttons.append([
            InlineKeyboardButton(
                nombre,
                callback_data=f"SUPERVISOR|{nombre}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


def _build_empresa_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("WIN", callback_data="EMPRESA|WIN"),
            InlineKeyboardButton("TU FIBRA", callback_data="EMPRESA|TUFIBRA"),
        ]
    ])


# =========================
# ENTRY POINT DESDE START
# =========================
async def send_supervisores_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra supervisores activos desde Google Sheets
    """
    chat_id = update.effective_chat.id

    rows = _load_supervisores()

    activos = []
    for r in rows:
        if _is_active(r.get("activo", "1")):
            nombre = str(
                r.get("nombre", "")
                or r.get("Nombre", "")
                or r.get("NOMBRE", "")
            ).strip()
            if nombre:
                activos.append(r)

    log_event("SUPERVISORES_LOAD", chat_id=chat_id, total=len(activos))

    if not activos:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ No hay supervisores activos en la hoja SUPERVISORES."
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="PASO 1 - NOMBRE DEL SUPERVISOR\n\nSelecciona el supervisor:",
        reply_markup=_build_supervisores_keyboard(activos)
    )


# =========================
# CALLBACK PRINCIPAL
# =========================
async def supervisor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    log_event("SUPERVISOR_CALLBACK", chat_id=chat_id, data=data)

    # retraer botones del mensaje anterior
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data.startswith("SUPERVISOR|"):
        parts = data.split("|", 1)
        supervisor = parts[1].strip() if len(parts) > 1 else ""

        if not supervisor:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Supervisor inválido."
            )
            return

        set_data(chat_id, "supervisor", supervisor)
        set_state(chat_id, "SELECT_EMPRESA")

        log_event("SUPERVISOR_SELECTED", chat_id=chat_id, supervisor=supervisor)

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Supervisor: {supervisor}\n\n"
                "PASO 2 - SELECCIONA EMPRESA"
            ),
            reply_markup=_build_empresa_keyboard()
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Opción no válida."
    )