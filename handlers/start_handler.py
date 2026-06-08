# =========================
# handlers/start_handler.py
# Handler inicial (/start e inicio de flujo)
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.session_manager import reset_session, set_state, set_data, get_data
from utils.logger import log_event
from config import now_peru_dt, now_peru_str
from services.almuerzo_service import obtener_almuerzo_activo


# =========================
# MENSAJES
# =========================
WELCOME_TEXT = (
    "👋 Bienvenido al sistema de Supervisión\n\n"
    "Selecciona una opción para comenzar:"
)

HELP_TEXT = (
    "ℹ️ Este bot permite registrar supervisiones con evidencias, "
    "validaciones y control de calidad.\n\n"
    "Flujo general:\n"
    "1. Seleccionas supervisor\n"
    "2. Seleccionas empresa\n"
    "3. Seleccionas cuadrilla o técnico\n"
    "4. Seleccionas distrito\n"
    "5. Cargas evidencias\n"
    "6. Completas información\n"
    "7. Finalizas la supervisión"
)

ALMUERZO_TEXT = (
    "🍽️ Gestión de almuerzo\n\n"
    "Selecciona una opción:"
)


# =========================
# KEYBOARDS
# =========================
def build_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Iniciar Supervisión", callback_data="START_SUP")],
        [InlineKeyboardButton("🍽️ Almuerzo", callback_data="START_ALMUERZO")],
        [InlineKeyboardButton("ℹ️ Ayuda", callback_data="START_HELP")],
    ])


def build_almuerzo_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Iniciar almuerzo", callback_data="ALMUERZO|START")],
        [InlineKeyboardButton("⏹️ Finalizar almuerzo", callback_data="ALMUERZO|END")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="START_BACK_MAIN")],
    ])


# =========================
# HELPERS
# =========================
def _set_supervision_start(chat_id: int) -> None:
    now_dt = now_peru_dt()
    set_data(chat_id, "supervision_start_ts", now_dt.timestamp())
    set_data(chat_id, "supervision_start_str", now_peru_str())


async def _alert_almuerzo_activo(query, chat_id: int) -> bool:
    activo = obtener_almuerzo_activo(str(chat_id))

    if not activo:
        return False

    hora_inicio = str(activo.get("Hora_Inicio_Formato", "") or "").strip()

    await query.answer(
        "⛔️ No puedes iniciar una supervisión porque tienes un almuerzo en curso.\n"
        f"🕒 Inicio de almuerzo: {hora_inicio}",
        show_alert=True
    )
    return True


# =========================
# HANDLER /START
# =========================
async def start_command(update, context):
    chat_id = update.effective_chat.id

    reset_session(chat_id)
    set_state(chat_id, "MENU_PRINCIPAL")
    _set_supervision_start(chat_id)

    log_event("START_COMMAND", chat_id=chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=WELCOME_TEXT,
        reply_markup=build_main_menu(),
    )


# =========================
# HANDLER CALLBACK MENU
# =========================
async def start_menu_callback(update, context):
    query = update.callback_query

    chat_id = update.effective_chat.id
    data = query.data or ""

    log_event("START_MENU_ACTION", chat_id=chat_id, action=data)

    # =========================
    # BLOQUEAR INICIAR SUPERVISIÓN SI HAY ALMUERZO
    # =========================
    if data == "START_SUP":
        if await _alert_almuerzo_activo(query, chat_id):
            return

        await query.answer()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        set_state(chat_id, "SELECT_SUPERVISOR")

        if not get_data(chat_id, "supervision_start_ts"):
            _set_supervision_start(chat_id)

        from handlers.supervisor_handler import send_supervisores_list

        await send_supervisores_list(update, context)
        return

    # =========================
    # ALMUERZO
    # =========================
    if data == "START_ALMUERZO":
        await query.answer()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        set_state(chat_id, "MENU_ALMUERZO")

        await context.bot.send_message(
            chat_id=chat_id,
            text=ALMUERZO_TEXT,
            reply_markup=build_almuerzo_menu(),
        )
        return

    # =========================
    # AYUDA
    # =========================
    if data == "START_HELP":
        await query.answer()

        await context.bot.send_message(
            chat_id=chat_id,
            text=HELP_TEXT,
        )
        return

    # =========================
    # VOLVER A MENÚ PRINCIPAL
    # =========================
    if data == "START_BACK_MAIN":
        if await _alert_almuerzo_activo(query, chat_id):
            return

        await query.answer()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        set_state(chat_id, "MENU_PRINCIPAL")

        await context.bot.send_message(
            chat_id=chat_id,
            text=WELCOME_TEXT,
            reply_markup=build_main_menu(),
        )
        return

    await query.answer()

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Opción no reconocida."
    )