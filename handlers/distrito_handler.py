# =========================
# handlers/distrito_handler.py
# Manejo de distritos (búsqueda por texto)
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event
from services.google_sheets_service import get_distritos
from services.cache_service import get_or_set


# =========================
# HELPERS
# =========================
def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _is_active(value: str) -> bool:
    v = str(value or "").strip().lower()
    return v in ("1", "true", "si", "sí", "activo", "")


def _load_distritos():
    return get_or_set(
        key="distritos",
        ttl=180,
        fetch_func=get_distritos,
    )


def _filter_distritos(query: str):
    query_n = _normalize(query)
    rows = _load_distritos()
    out = []

    for r in rows:
        distrito = str(
            r.get("distrito", "")
            or r.get("Distrito", "")
            or r.get("DISTRITO", "")
        ).strip()

        alias = str(r.get("alias", "")).strip()
        activo = r.get("activo", "1")

        if not _is_active(activo):
            continue

        if not distrito:
            continue

        hay_match = False

        if query_n in _normalize(distrito):
            hay_match = True

        if not hay_match and alias:
            for a in alias.split(";"):
                if query_n in _normalize(a):
                    hay_match = True
                    break

        if hay_match:
            out.append({
                "distrito": distrito,
                "alias": alias,
            })

    return out


def _build_distritos_keyboard(items):
    buttons = []

    for item in items[:8]:
        buttons.append([
            InlineKeyboardButton(
                item["distrito"][:60],
                callback_data=f"DISTRITO|SELECT|{item['distrito']}"
            )
        ])

    buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="BACK|DISTRITO")])

    return InlineKeyboardMarkup(buttons)


def _build_location_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - REPORTA TU UBICACIÓN\n\n"
        "📍 Envía tu ubicación actual."
    )


async def _send_location_step(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    next_step = int(get_data(chat_id, "current_step_number", 4)) + 1

    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "WAIT_LOCATION_CLIENTE")

    await context.bot.send_message(
        chat_id=chat_id,
        text=_build_location_prompt(next_step)
    )


# =========================
# CALLBACK PRINCIPAL
# =========================
async def distrito_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("DISTRITO_CALLBACK", chat_id=chat_id, action=action)

    # retraer botones del mensaje anterior
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "SELECT" and len(parts) >= 3:
        distrito = "|".join(parts[2:]).strip()

        if not distrito:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Distrito inválido."
            )
            return

        set_data(chat_id, "distrito", distrito)

        log_event("DISTRITO_SELECTED", chat_id=chat_id, distrito=distrito)

        # mensaje independiente de confirmación
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Distrito seleccionado automáticamente:\n{distrito}"
        )

        # siguiente paso: ubicación
        await _send_location_step(chat_id, context)
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Opción no válida para distrito."
    )


# =========================
# INPUT BÚSQUEDA
# =========================
async def distrito_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if len(text) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Escribe al menos 2 caracteres para buscar."
        )
        return

    results = _filter_distritos(text)

    log_event("DISTRITO_SEARCH", chat_id=chat_id, query=text, results=len(results))

    if not results:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ No encontré coincidencias.\n\n"
                "Prueba con otro nombre o alias."
            )
        )
        return

    # 1 coincidencia -> selección automática
    if len(results) == 1:
        distrito = results[0]["distrito"]

        set_data(chat_id, "distrito", distrito)

        log_event("DISTRITO_AUTO_SELECTED", chat_id=chat_id, distrito=distrito)

        # mensaje independiente de confirmación
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Distrito seleccionado automáticamente:\n{distrito}"
        )

        # siguiente paso: ubicación
        await _send_location_step(chat_id, context)
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔎 Encontré {len(results)} coincidencias. Selecciona una:",
        reply_markup=_build_distritos_keyboard(results)
    )


# =========================
# INPUT MANUAL
# =========================
async def distrito_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Escribe un distrito válido."
        )
        return

    set_data(chat_id, "distrito", text)

    log_event("DISTRITO_MANUAL", chat_id=chat_id, distrito=text)

    # mensaje independiente de confirmación
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Distrito registrado:\n{text}"
    )

    # siguiente paso: ubicación
    await _send_location_step(chat_id, context)