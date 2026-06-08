# =========================
# handlers/almuerzo_handler.py
# Handler de almuerzo
# =========================

from telegram import Update
from telegram.ext import ContextTypes

from core.session_manager import get_data, set_state
from services.almuerzo_service import iniciar_almuerzo, finalizar_almuerzo
from utils.logger import log_event


async def almuerzo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    chat_id = update.effective_chat.id
    user = update.effective_user
    data = query.data or ""

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("ALMUERZO_ACTION", chat_id=chat_id, action=action)

    supervisor = (
        get_data(chat_id, "supervisor_nombre", "")
        or get_data(chat_id, "supervisor", "")
        or user.full_name
        or ""
    )

    supervisor_id = (
        get_data(chat_id, "supervisor_id", "")
        or str(user.id)
    )

    if action == "START":
        result = iniciar_almuerzo({
            "Chat_ID": chat_id,
            "Supervisor": supervisor,
            "Supervisor_ID": supervisor_id,
        })

        set_state(chat_id, "MENU_ALMUERZO")

        if not result.get("ok"):
            await query.answer(
                result.get("msg", "⛔️ Ya tienes un almuerzo en curso."),
                show_alert=True
            )
            return

        await query.answer()

        await context.bot.send_message(
            chat_id=chat_id,
            text=result.get(
                "msg",
                "🍽️ Inicio de almuerzo\n🕒 Hora de inicio: --:--"
            )
        )
        return

    if action == "END":
        await query.answer()

        result = finalizar_almuerzo(str(chat_id))

        set_state(chat_id, "MENU_ALMUERZO")

        await context.bot.send_message(
            chat_id=chat_id,
            text=result.get(
                "msg",
                "🍽️ Fin de almuerzo\n🕒 Hora de inicio: --:--\n🕒 Hora de fin: --:--\n⏱️ Tiempo total: N/D"
            )
        )
        return

    await query.answer()

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Opción de almuerzo no válida."
    )