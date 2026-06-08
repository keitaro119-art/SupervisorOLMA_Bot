# =========================
# handlers/cuadrilla_handler.py
# Manejo de cuadrillas WIN (búsqueda por texto)
# Corregido para evitar Button_data_invalid
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event
from services.google_sheets_service import get_cuadrillas_win
from services.cache_service import get_or_set


# =========================
# HELPERS
# =========================
def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _is_active(value: str) -> bool:
    v = str(value or "").strip().lower()
    return v in ("1", "true", "si", "sí", "activo", "")


def _load_cuadrillas():
    return get_or_set(
        key="cuadrillas_win",
        ttl=180,
        fetch_func=get_cuadrillas_win,
    )


def _filter_cuadrillas(query: str):
    query_n = _normalize(query)
    rows = _load_cuadrillas()
    out = []

    for r in rows:
        nombre = str(
            r.get("nombre_completo", "")
            or r.get("nombre", "")
            or r.get("Nombre_Completo", "")
            or r.get("NOMBRE_COMPLETO", "")
        ).strip()

        alias = str(r.get("alias", "")).strip()
        activo = r.get("activo", "1")

        if not _is_active(activo):
            continue

        if not nombre:
            continue

        hay_match = False

        if query_n in _normalize(nombre):
            hay_match = True

        if not hay_match and alias:
            for a in alias.split(";"):
                if query_n in _normalize(a):
                    hay_match = True
                    break

        if hay_match:
            out.append({
                "nombre": nombre,
                "alias": alias,
            })

    return out


def _build_cuadrillas_keyboard(items):
    buttons = []

    for i, item in enumerate(items[:8]):
        buttons.append([
            InlineKeyboardButton(
                item["nombre"][:60],
                callback_data=f"CUADRILLA|SELECT|{i}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


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


async def _go_to_tecnico_1(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    next_step = int(get_data(chat_id, "current_step_number", 3)) + 1
    set_data(chat_id, "current_step_number", next_step)

    set_data(chat_id, "tecnico_slot", 1)
    set_state(chat_id, "SEARCH_TECNICO")

    await context.bot.send_message(
        chat_id=chat_id,
        text=_build_tecnico_1_prompt(next_step)
    )


# =========================
# CALLBACK PRINCIPAL
# =========================
async def cuadrilla_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("CUADRILLA_CALLBACK", chat_id=chat_id, action=action, data=data)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "SELECT" and len(parts) >= 3:
        try:
            index = int(parts[2])
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Selección inválida."
            )
            return

        results = get_data(chat_id, "cuadrillas_cache", []) or []

        if index < 0 or index >= len(results):
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ La selección ya no es válida. Vuelve a buscar la cuadrilla."
            )
            return

        item = results[index]
        nombre = str(item.get("nombre", "")).strip()

        if not nombre:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ No se pudo recuperar la cuadrilla seleccionada."
            )
            return

        set_data(chat_id, "cuadrilla", nombre)

        log_event("CUADRILLA_SELECTED", chat_id=chat_id, cuadrilla=nombre, index=index)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Cuadrilla seleccionada automáticamente:\n{nombre}"
        )

        await _go_to_tecnico_1(chat_id, context)
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Opción no válida para cuadrilla."
    )


# =========================
# INPUT BÚSQUEDA
# =========================
async def cuadrilla_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if len(text) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Escribe al menos 2 caracteres para buscar."
        )
        return

    results = _filter_cuadrillas(text)

    log_event("CUADRILLA_SEARCH", chat_id=chat_id, query=text, results=len(results))

    if not results:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ No encontré coincidencias.\n\n"
                "Prueba con otro nombre, alias o código."
            )
        )
        return

    # deduplicar por nombre
    dedup = []
    seen = set()
    for r in results:
        key = str(r.get("nombre", "")).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    results = dedup

    log_event("CUADRILLA_SEARCH_DEDUP", chat_id=chat_id, query=text, results=len(results))

    # 1 coincidencia -> selección automática
    if len(results) == 1:
        nombre = str(results[0].get("nombre", "")).strip()

        set_data(chat_id, "cuadrilla", nombre)

        log_event("CUADRILLA_AUTO_SELECTED", chat_id=chat_id, cuadrilla=nombre)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Cuadrilla seleccionada automáticamente:\n{nombre}"
        )

        await _go_to_tecnico_1(chat_id, context)
        return

    # múltiples resultados -> guardar cache corto para botones
    set_data(chat_id, "cuadrillas_cache", results[:8])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔎 Encontré {len(results)} coincidencias. Selecciona una:",
        reply_markup=_build_cuadrillas_keyboard(results)
    )


# =========================
# INPUT MANUAL
# =========================
async def cuadrilla_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Escribe un nombre válido."
        )
        return

    set_data(chat_id, "cuadrilla", text)

    log_event("CUADRILLA_MANUAL", chat_id=chat_id, cuadrilla=text)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Cuadrilla registrada:\n{text}"
    )

    await _go_to_tecnico_1(chat_id, context)