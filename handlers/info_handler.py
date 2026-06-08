# =========================
# handlers/info_handler.py
# Manejo de Información de Supervisión
# Información en Acta con botones SI / NO
# Cierre del módulo controlado desde menu_handler con Volver
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event
from utils.helpers import now_str
from constants import STATE_MENU_INFO
from config import now_peru_dt


# =========================
# HELPERS
# =========================
def _mark(val) -> str:
    return "✅" if val not in ("", None, {}, []) else "⬜"


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} h")
    if minutes > 0:
        parts.append(f"{minutes} min")
    parts.append(f"{secs} seg")

    return " ".join(parts)


def _set_module_data(chat_id: int, suffix: str, value):
    set_data(chat_id, f"mod_info_{suffix}", value)


def _get_module_data(chat_id: int, suffix: str, default=None):
    return get_data(chat_id, f"mod_info_{suffix}", default)


def _touch_info_module_start(chat_id: int):
    now_dt = now_peru_dt()

    _set_module_data(chat_id, "current", True)

    if not _get_module_data(chat_id, "inicio_ts"):
        _set_module_data(chat_id, "inicio_ts", now_dt.timestamp())
        _set_module_data(chat_id, "inicio_str", now_str())

    _set_module_data(chat_id, "fin_ts", "")
    _set_module_data(chat_id, "fin_str", "")
    _set_module_data(chat_id, "duracion_seg", "")
    _set_module_data(chat_id, "duracion", "")
    _set_module_data(chat_id, "estado", "")


def _close_info_module(chat_id: int, status_value: str):
    now_dt = now_peru_dt()
    start_ts = _safe_float(_get_module_data(chat_id, "inicio_ts", 0.0), 0.0)
    end_ts = now_dt.timestamp()

    duration_seconds = max(0.0, end_ts - start_ts) if start_ts > 0 else 0.0

    _set_module_data(chat_id, "fin_ts", end_ts)
    _set_module_data(chat_id, "fin_str", now_str())
    _set_module_data(chat_id, "duracion_seg", int(duration_seconds))
    _set_module_data(chat_id, "duracion", _format_duration(duration_seconds))
    _set_module_data(chat_id, "estado", status_value)
    _set_module_data(chat_id, "current", False)


def _build_info_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📏 Metraje drop externo", callback_data="INFO|DROP_EXT")],
        [InlineKeyboardButton("🏠 Metraje drop interno", callback_data="INFO|DROP_INT")],
        [InlineKeyboardButton("🪵 Cantidad de postes usados", callback_data="INFO|POSTES")],
        [InlineKeyboardButton("🔧 Cantidad de falsos tramos usados", callback_data="INFO|FALSOS")],
        [InlineKeyboardButton("⚙️ Cantidad aprox. de templadores usados", callback_data="INFO|TEMPLADORES")],
        [InlineKeyboardButton("🗺️ Captura de recorrido", callback_data="INFO|RECORRIDO")],
        [InlineKeyboardButton("📄 Información en Acta", callback_data="INFO|VALIDACION_ACTA")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")],
    ])


def _build_acta_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data="INFO|ACTA|SI"),
            InlineKeyboardButton("❌ NO", callback_data="INFO|ACTA|NO"),
        ],
        [InlineKeyboardButton("⬅️ Volver", callback_data="MENU|INFO")],
    ])


def _build_info_menu_text(chat_id: int) -> str:
    drop_ext = get_data(chat_id, "info_drop_ext", {})
    drop_ext_metraje = get_data(chat_id, "info_drop_ext_metraje", "")
    drop_int = get_data(chat_id, "info_drop_int", "")
    postes = get_data(chat_id, "info_postes", "")
    falsos = get_data(chat_id, "info_falsos", "")
    templadores = get_data(chat_id, "info_templadores", "")
    recorrido = get_data(chat_id, "info_recorrido_file_id", "")
    acta_ok = get_data(chat_id, "info_validacion_acta", "")

    mod_estado = str(_get_module_data(chat_id, "estado", "") or "").strip()
    mod_duracion = str(_get_module_data(chat_id, "duracion", "") or "").strip()

    drop_ext_ok = bool(drop_ext) and str(drop_ext_metraje).strip() != ""

    extra = ""
    if mod_estado or mod_duracion:
        extra = (
            "\n\n"
            f"📌 Estado módulo: {mod_estado or '-'}\n"
            f"⏱️ Tiempo módulo: {mod_duracion or '-'}"
        )

    return (
        "📊 INFORMACIÓN DE SUPERVISIÓN\n\n"
        f"{_mark(drop_ext_ok)} Metraje drop externo\n"
        f"{_mark(drop_int)} Metraje drop interno\n"
        f"{_mark(postes)} Cantidad de postes usados\n"
        f"{_mark(falsos)} Cantidad de falsos tramos usados\n"
        f"{_mark(templadores)} Cantidad aprox. de templadores usados\n"
        f"{_mark(recorrido)} Captura de recorrido\n"
        f"{_mark(acta_ok)} Información en Acta"
        f"{extra}"
    )


async def _edit_or_send(query, context, chat_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def _send_info_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, prefix: str = ""):
    text = _build_info_menu_text(chat_id)
    if prefix:
        text = f"{prefix}\n\n{text}"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=_build_info_menu_keyboard(),
    )


async def _send_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, prefix: str = ""):
    from handlers.menu_handler import build_menu_principal

    set_state(chat_id, "MENU_SUPERVISION")

    text = "MENÚ DE SUPERVISIÓN"
    if prefix:
        text = f"{prefix}\n\n{text}"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=build_menu_principal(chat_id),
    )


# =========================
# CALLBACK: INFO
# =========================
async def info_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data or ""

    parts = data.split("|")
    option = parts[1] if len(parts) > 1 else ""

    log_event("INFO_SELECTED", chat_id=chat_id, option=option, data=data)

    set_state(chat_id, STATE_MENU_INFO)

    if option in {"DROP_EXT", "DROP_INT", "POSTES", "FALSOS", "TEMPLADORES", "RECORRIDO", "VALIDACION_ACTA"}:
        _touch_info_module_start(chat_id)

    if option == "DROP_EXT":
        set_data(chat_id, "info_current_field", "DROP_EXT_CTO")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "📏 METRAJE DROP EXTERNO\n\n"
            "📍 Envía primero la ubicación de la CTO."
        )
        return

    if option == "DROP_INT":
        set_data(chat_id, "info_current_field", "DROP_INT")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "🏠 METRAJE DROP INTERNO\n\n"
            "✍️ Ingresa en números el metraje aprox. de drop usado."
        )
        return

    if option == "POSTES":
        set_data(chat_id, "info_current_field", "POSTES")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "🪵 CANTIDAD DE POSTES USADOS\n\n"
            "✍️ Ingresa en números la cantidad de postes usados en el recorrido."
        )
        return

    if option == "FALSOS":
        set_data(chat_id, "info_current_field", "FALSOS")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "🔧 CANTIDAD DE FALSOS TRAMOS USADOS\n\n"
            "✍️ Ingresa en números la cantidad de falsos tramos usados en el recorrido."
        )
        return

    if option == "TEMPLADORES":
        set_data(chat_id, "info_current_field", "TEMPLADORES")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "⚙️ CANTIDAD APROXIMADA DE TEMPLADORES USADOS\n\n"
            "✍️ Ingresa en números la cantidad aproximada de templadores usados en el recorrido."
        )
        return

    if option == "RECORRIDO":
        set_data(chat_id, "info_current_field", "RECORRIDO")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "🗺️ CAPTURA DE RECORRIDO\n\n"
            "📸 Carga la imagen del recorrido."
        )
        return

    if option == "VALIDACION_ACTA":
        set_data(chat_id, "info_current_field", "")
        await _edit_or_send(
            query,
            context,
            chat_id,
            "📄 INFORMACIÓN EN ACTA\n\n"
            "¿La información colocada en el acta por el técnico es correcta?",
            reply_markup=_build_acta_keyboard()
        )
        return

    if option == "ACTA" and len(parts) >= 3:
        value = str(parts[2]).strip().upper()
        if value not in {"SI", "NO"}:
            await query.answer("⚠️ Opción no válida.", show_alert=True)
            return

        set_data(chat_id, "info_validacion_acta", value)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_VALIDACION_ACTA", chat_id=chat_id, value=value)

        await _edit_or_send(
            query,
            context,
            chat_id,
            f"✅ Información en acta guardada: {value}\n\n{_build_info_menu_text(chat_id)}",
            reply_markup=_build_info_menu_keyboard()
        )
        return

    if option == "MODULE_STATUS" and len(parts) >= 3:
        status_value = str(parts[2]).strip().upper()
        _close_info_module(chat_id, status_value)

        duracion = str(_get_module_data(chat_id, "duracion", "-") or "-").strip()
        await _send_main_menu(
            chat_id,
            context,
            prefix=(
                "✅ Módulo cerrado: Información de Supervisión\n"
                f"Estado: {status_value}\n"
                f"Tiempo: {duracion}"
            ),
        )
        return

    await query.answer("⚠️ Opción de información no válida.", show_alert=True)


# =========================
# STATE: INFO INPUT
# =========================
async def handle_info_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    field = get_data(chat_id, "info_current_field", "")

    if update.message.location:
        loc = update.message.location

        if field == "DROP_EXT_CTO":
            drop_ext = get_data(chat_id, "info_drop_ext", {})
            drop_ext["cto_lat"] = loc.latitude
            drop_ext["cto_lon"] = loc.longitude
            set_data(chat_id, "info_drop_ext", drop_ext)
            set_data(chat_id, "info_current_field", "DROP_EXT_DOM")

            log_event("INFO_DROP_EXT_CTO", chat_id=chat_id, lat=loc.latitude, lon=loc.longitude)

            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Ubicación CTO guardada.\n\nAhora envía la ubicación del domicilio."
            )
            return

        if field == "DROP_EXT_DOM":
            drop_ext = get_data(chat_id, "info_drop_ext", {})
            drop_ext["dom_lat"] = loc.latitude
            drop_ext["dom_lon"] = loc.longitude
            set_data(chat_id, "info_drop_ext", drop_ext)
            set_data(chat_id, "info_current_field", "DROP_EXT_METRAJE")

            log_event("INFO_DROP_EXT_DOM", chat_id=chat_id, lat=loc.latitude, lon=loc.longitude)

            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Ubicación domicilio guardada.\n\nAhora ingresa en números el metraje aprox. de drop usado."
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Esa ubicación no era esperada en este paso."
        )
        return

    if update.message.photo:
        if field == "RECORRIDO":
            file_id = update.message.photo[-1].file_id
            set_data(chat_id, "info_recorrido_file_id", file_id)
            set_data(chat_id, "info_current_field", "")

            log_event("INFO_RECORRIDO_FILE", chat_id=chat_id, file_id=file_id)

            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Captura de recorrido guardada."
            )
            await _send_info_menu(chat_id, context)
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Esa imagen no era esperada en este paso."
        )
        return

    text = (update.message.text or "").strip()
    if not text:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Envía un valor válido."
        )
        return

    if field == "DROP_EXT_METRAJE":
        set_data(chat_id, "info_drop_ext_metraje", text)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_DROP_EXT_METRAJE", chat_id=chat_id, value=text)

        await context.bot.send_message(chat_id=chat_id, text="✅ Metraje de drop externo guardado.")
        await _send_info_menu(chat_id, context)
        return

    if field == "DROP_INT":
        set_data(chat_id, "info_drop_int", text)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_DROP_INT", chat_id=chat_id, value=text)

        await context.bot.send_message(chat_id=chat_id, text="✅ Metraje de drop interno guardado.")
        await _send_info_menu(chat_id, context)
        return

    if field == "POSTES":
        set_data(chat_id, "info_postes", text)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_POSTES", chat_id=chat_id, value=text)

        await context.bot.send_message(chat_id=chat_id, text="✅ Cantidad de postes guardada.")
        await _send_info_menu(chat_id, context)
        return

    if field == "FALSOS":
        set_data(chat_id, "info_falsos", text)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_FALSOS", chat_id=chat_id, value=text)

        await context.bot.send_message(chat_id=chat_id, text="✅ Cantidad de falsos tramos guardada.")
        await _send_info_menu(chat_id, context)
        return

    if field == "TEMPLADORES":
        set_data(chat_id, "info_templadores", text)
        set_data(chat_id, "info_current_field", "")
        log_event("INFO_TEMPLADORES", chat_id=chat_id, value=text)

        await context.bot.send_message(chat_id=chat_id, text="✅ Cantidad de templadores guardada.")
        await _send_info_menu(chat_id, context)
        return

    if field == "VALIDACION_ACTA":
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Usa los botones SI o NO para Información en Acta."
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ No hay un campo de información activo."
    )