# =========================
# handlers/selfie_handler.py
# Paso: selfie en fachada y pase al menú
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event


def _build_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏗️ Supervision de Instalación", callback_data="MENU|INSTALACION")],
        [InlineKeyboardButton("🧰 Herramientas", callback_data="MENU|HERRAMIENTAS")],
        [InlineKeyboardButton("🦺 EPP", callback_data="MENU|EPP")],
        [InlineKeyboardButton("🚧 EPE", callback_data="MENU|EPE")],
        [InlineKeyboardButton("👕 Uniformes", callback_data="MENU|UNIFORMES")],
        [InlineKeyboardButton("🚗 Vehículo", callback_data="MENU|VEHICULO")],
        [InlineKeyboardButton("📸 Evidencias opcionales", callback_data="MENU|OPCIONAL")],
        [InlineKeyboardButton("📊 Información de Supervision", callback_data="MENU|INFO")],
    ])


async def selfie_input(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photos = update.message.photo if update.message else None

    if not photos:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Debes enviar una foto selfie en fachada."
        )
        return

    best_photo = photos[-1]
    file_id = best_photo.file_id
    file_unique_id = best_photo.file_unique_id

    set_data(chat_id, "selfie_fachada_file_id", file_id)
    set_data(chat_id, "selfie_fachada_file_unique_id", file_unique_id)

    log_event(
        "SELFIE_FACHADA_SET",
        chat_id=chat_id,
        file_id=file_id,
        file_unique_id=file_unique_id,
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text="✅ Selfie en fachada registrada correctamente."
    )

    next_step = int(get_data(chat_id, "current_step_number", 5)) + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "MENU_SUPERVISION")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"PASO {next_step} - MENÚ DE SUPERVISIÓN",
        reply_markup=_build_main_menu_keyboard()
    )