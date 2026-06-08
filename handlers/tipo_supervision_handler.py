# =========================
# handlers/tipo_supervision_handler.py
# Paso: Tipo de supervisión
# Selección:
#   🔥 SUPERVISION EN CALIENTE
#   🧊 SUPERVISION EN FRIO
# Luego continúa a INPUT_PLACA_UNIDAD
# =========================

from telegram import Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event


# =========================
# HELPERS
# =========================
def _build_placa_unidad_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - INGRESAR PLACA DE UNIDAD\n\n"
        "✍️ Escribe la placa de la unidad.\n\n"
        "Ejemplo:\n"
        "• ABC-123\n"
        "• B7T-456"
    )


def _map_tipo_supervision(value: str) -> str:
    raw = (value or "").strip().upper()

    if raw == "CALIENTE":
        return "SUPERVISION EN CALIENTE"

    if raw == "FRIO":
        return "SUPERVISION EN FRIO"

    return ""


# =========================
# CALLBACK PRINCIPAL
# Espera callback_data:
#   TIPO_SUP|CALIENTE
#   TIPO_SUP|FRIO
# =========================
async def tipo_supervision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    parts = data.split("|")
    tipo_raw = parts[1] if len(parts) > 1 else ""
    tipo_supervision = _map_tipo_supervision(tipo_raw)

    log_event(
        "TIPO_SUPERVISION_CALLBACK",
        chat_id=chat_id,
        data=data,
        tipo_raw=tipo_raw,
        tipo_supervision=tipo_supervision,
    )

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not tipo_supervision:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Opción de tipo de supervisión no válida."
        )
        return

    set_data(chat_id, "tipo_supervision", tipo_supervision)

    current_step = int(get_data(chat_id, "current_step_number", 4))
    next_step = current_step + 1

    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "INPUT_PLACA_UNIDAD")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Tipo de supervisión seleccionado:\n{tipo_supervision}"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=_build_placa_unidad_prompt(next_step),
    )