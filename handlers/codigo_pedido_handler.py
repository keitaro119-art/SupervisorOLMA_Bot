# =========================
# handlers/codigo_pedido_handler.py
# Paso: ingreso de código de pedido
# =========================

from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event


def _build_distrito_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - DISTRITO DE SUPERVISIÓN\n\n"
        "🔎 Escribe parte del nombre o alias del distrito.\n\n"
        "Ejemplos:\n"
        "• miraflores\n"
        "• sjl\n"
        "• los olivos"
    )


async def codigo_pedido_input(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ingresa un código de pedido válido."
        )
        return

    set_data(chat_id, "codigo_pedido", text)

    log_event("CODIGO_PEDIDO_SET", chat_id=chat_id, codigo_pedido=text)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Código de pedido registrado:\n{text}"
    )

    next_step = int(get_data(chat_id, "current_step_number", 5)) + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "SEARCH_DISTRITO")

    await context.bot.send_message(
        chat_id=chat_id,
        text=_build_distrito_prompt(next_step)
    )