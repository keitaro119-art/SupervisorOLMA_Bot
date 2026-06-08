# =========================
# handlers/empresa_handler.py
# Selección de empresa (WIN / TU FIBRA)
# =========================

from telegram import Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data
from utils.logger import log_event


# =========================
# HELPERS
# =========================
def _build_tecnico_1_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - INGRESAR TÉCNICO 1\n\n"
        "✍️ Escribe parte del nombre o apellido del técnico.\n\n"
        "Ejemplos:\n"
        "• ojeda\n"
        "• alejandro\n"
        "• salcedo\n\n"
        "🧠 El bot buscará coincidencias en INFO_TECNICOS."
    )


# =========================
# CALLBACK PRINCIPAL
# =========================
async def empresa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    try:
        _, empresa = data.split("|", 1)
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Error al seleccionar empresa."
        )
        return

    empresa = empresa.upper().strip()

    log_event("EMPRESA_SELECTED", chat_id=chat_id, empresa=empresa)

    # retraer botones anteriores
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    set_data(chat_id, "empresa", empresa)

    # limpiar/arrancar flujo de técnicos
    set_data(chat_id, "tecnico_slot", 1)
    set_data(chat_id, "tecnico_1_nombre", "")
    set_data(chat_id, "tecnico_1_empresa", "")
    set_data(chat_id, "tecnico_2_nombre", "")
    set_data(chat_id, "tecnico_2_empresa", "")
    set_data(chat_id, "tecnico_3_nombre", "")
    set_data(chat_id, "tecnico_3_empresa", "")

    # =========================
    # FLUJO WIN
    # =========================
    if empresa == "WIN":
        set_data(chat_id, "current_step_number", 3)
        set_state(chat_id, "SEARCH_CUADRILLA")

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "PASO 3 - BUSCAR CUADRILLA (WIN)\n\n"
                "✍️ Escribe parte del nombre o código.\n\n"
                "Ejemplos:\n"
                "• arucutipa\n"
                "• P32\n"
                "• olma sgi\n\n"
                "🧠 El bot mostrará coincidencias."
            )
        )
        return

    # =========================
    # FLUJO TU FIBRA
    # =========================
    if empresa in ("TUFIBRA", "TU_FIBRA", "TU FIBRA"):
        set_data(chat_id, "current_step_number", 3)
        set_state(chat_id, "SEARCH_TECNICO")

        await context.bot.send_message(
            chat_id=chat_id,
            text=_build_tecnico_1_prompt(3)
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Empresa no válida."
    )