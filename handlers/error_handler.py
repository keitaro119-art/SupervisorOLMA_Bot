# =========================
# handlers/error_handler.py
# Manejo global de errores del bot
# =========================

import traceback
from telegram import Update
from telegram.ext import ContextTypes

from utils.logger import log_event


# =========================
# ERROR HANDLER GLOBAL
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja cualquier excepción no controlada del bot.
    Evita que el bot se caiga y registra todo para debug.
    """

    # =========================
    # INFO BASE
    # =========================
    error = context.error
    tb = traceback.format_exc()

    chat_id = None
    user_id = None

    try:
        if isinstance(update, Update):
            chat_id = update.effective_chat.id if update.effective_chat else None
            user_id = update.effective_user.id if update.effective_user else None
    except Exception:
        pass

    # =========================
    # LOG DETALLADO
    # =========================
    log_event(
        "GLOBAL_ERROR",
        chat_id=chat_id,
        user_id=user_id,
        error=str(error),
        traceback=tb
    )

    # =========================
    # RESPUESTA AL USUARIO
    # =========================
    try:
        if isinstance(update, Update):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Ocurrió un error inesperado.\n"
                    "El equipo técnico ya fue notificado.\n"
                    "Por favor intenta nuevamente."
                )
    except Exception:
        # Evitar que falle el handler de errores
        pass

    # =========================
    # LOG CONSOLA (DEBUG)
    # =========================
    print("\n========== ERROR GLOBAL ==========")
    print(f"chat_id: {chat_id}")
    print(f"user_id: {user_id}")
    print(f"error: {error}")
    print("traceback:")
    print(tb)
    print("==================================\n")