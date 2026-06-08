# =========================
# handlers/ubicacion_handler.py
# Paso: reporta tu ubicación
# =========================

from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event


def _build_selfie_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - SELFIE EN FACHADA DE CLIENTE\n\n"
        "📸 Envía una foto selfie en la fachada del cliente."
    )


async def ubicacion_input(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    location = update.message.location if update.message else None

    if not location:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Debes enviar tu ubicación actual."
        )
        return

    set_data(chat_id, "ubicacion_lat", location.latitude)
    set_data(chat_id, "ubicacion_lon", location.longitude)

    log_event(
        "UBICACION_SET",
        chat_id=chat_id,
        lat=location.latitude,
        lon=location.longitude,
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ Ubicación registrada:\n"
            f"Lat: {location.latitude}\n"
            f"Lon: {location.longitude}"
        )
    )

    # 🔧 Corrección de numeración de pasos
    next_step = int(get_data(chat_id, "current_step_number", 5)) + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "WAIT_SELFIE_FACHADA")

    await context.bot.send_message(
        chat_id=chat_id,
        text=_build_selfie_prompt(next_step)
    )