# =========================
# handlers/tecnico_handler.py
# Flujo completo de técnicos (Técnico 1, 2, 3) + validación SCTR
# Ahora redirige a:
# TIPO DE SUPERVISIÓN -> PLACA DE UNIDAD -> CÓDIGO DE PEDIDO
# =========================

import asyncio
import io
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TimedOut, NetworkError, RetryAfter
from telegram.ext import ContextTypes

from core.session_manager import set_state, set_data, get_data
from utils.logger import log_event
from services.google_sheets_service import (
    get_info_tecnicos,
    get_sctr_records,
    download_drive_file_bytes,
)
from services.cache_service import get_or_set
from config import now_peru_dt


# =========================
# HELPERS
# =========================
def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _safe_int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _parse_date_flexible(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None

    patterns = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for fmt in patterns:
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            pass

    return None


def _format_date_short(value: str) -> str:
    d = _parse_date_flexible(value)
    if not d:
        return str(value or "").strip()
    return f"{d.day}/{d.month}/{d.year}"


def _compute_sctr_status(record: dict) -> str:
    dias_restantes = _safe_int(record.get("dias_restantes", ""), default=999999)

    if dias_restantes < 0:
        return "VENCIDO"

    vig_hasta = _parse_date_flexible(record.get("vigencia_hasta", ""))
    if vig_hasta and vig_hasta < now_peru_dt().date():
        return "VENCIDO"

    return "ACTIVO"


def _build_sctr_message(record: dict) -> str:
    nombre = str(record.get("apellidos_y_nombres", "")).strip()
    empresa = str(record.get("empresa", "")).strip()
    inicio = _format_date_short(record.get("vigencia_desde", ""))
    final = _format_date_short(record.get("vigencia_hasta", ""))
    dias_restantes = _safe_int(record.get("dias_restantes", ""), default=0)
    estado = _compute_sctr_status(record)

    return (
        "📋 DATOS DEL ASEGURADO\n\n"
        f"👤 Nombre: {nombre}\n"
        f"🏢 Empresa: {empresa}\n"
        f"📅 Inicio: {inicio}\n"
        f"📅 Final: {final}\n"
        f"📊 Estado: {estado}\n"
        f"Días restantes: {dias_restantes}"
    )


def _build_codigo_pedido_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - INGRESA CÓDIGO DE PEDIDO\n\n"
        "✍️ Escribe el código de pedido."
    )


def _build_placa_unidad_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - INGRESAR PLACA DE UNIDAD\n\n"
        "✍️ Escribe la placa de la unidad.\n\n"
        "Ejemplo:\n"
        "• ABC-123\n"
        "• B7T-456"
    )


def _build_tipo_supervision_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 SUPERVISION EN CALIENTE", callback_data="TIPO_SUP|CALIENTE")],
        [InlineKeyboardButton("🧊 SUPERVISION EN FRIO", callback_data="TIPO_SUP|FRIO")],
    ])


def _build_tipo_supervision_prompt(step_number: int) -> str:
    return (
        f"PASO {step_number} - TIPO DE SUPERVISIÓN\n\n"
        "Selecciona una opción:"
    )


def _load_tecnicos():
    return get_or_set(
        key="info_tecnicos",
        ttl=180,
        fetch_func=get_info_tecnicos,
    )


def _load_sctr():
    return get_or_set(
        key="sctr_records",
        ttl=180,
        fetch_func=get_sctr_records,
    )


def _find_sctr_record(nombre: str, empresa: str):
    nombre_n = _normalize(nombre)
    empresa_n = _normalize(empresa)

    rows = _load_sctr()

    for r in rows:
        r_nombre = str(r.get("apellidos_y_nombres", "")).strip()
        r_empresa = str(r.get("empresa", "")).strip()

        if _normalize(r_nombre) == nombre_n and _normalize(r_empresa) == empresa_n:
            return r

    for r in rows:
        r_nombre = str(r.get("apellidos_y_nombres", "")).strip()
        if _normalize(r_nombre) == nombre_n:
            return r

    return None


def _filter_tecnicos(query: str):
    query_n = _normalize(query)
    rows = _load_tecnicos()
    out = []

    for r in rows:
        nombre = str(r.get("apellidos_y_nombres", "")).strip()
        empresa = str(r.get("empresa", "")).strip()

        nombres = str(r.get("nombres", "")).strip()
        ap_pat = str(r.get("apellido_paterno", "")).strip()
        ap_mat = str(r.get("apellido_materno", "")).strip()
        nro_doc = str(r.get("nro_doc", "")).strip()

        texto_full = f"{nombre} {nombres} {ap_pat} {ap_mat} {nro_doc}"

        if query_n in _normalize(texto_full):
            out.append({
                "nombre": nombre,
                "empresa": empresa,
            })

    return out


def _build_tecnicos_keyboard(items):
    buttons = []

    for i, item in enumerate(items[:8]):
        label = item["nombre"][:60]
        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"TECNICO|SELECT|{i}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


def _build_si_no_keyboard(next_step: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data=f"TECNICO|ADD|{next_step}|SI"),
            InlineKeyboardButton("❌ NO", callback_data=f"TECNICO|ADD|{next_step}|NO"),
        ]
    ])


def _build_tecnico_prompt(step_number: int, slot: int) -> str:
    return (
        f"PASO {step_number} - INGRESAR TÉCNICO {slot}\n\n"
        "✍️ Escribe parte del nombre o apellido del técnico.\n\n"
        "Ejemplos:\n"
        "• ojeda\n"
        "• alejandro\n"
        "• salcedo\n\n"
        "🧠 El bot buscará coincidencias en INFO_TECNICOS."
    )


async def _send_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup=None,
    attempts: int = 3,
):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            return

        except RetryAfter as e:
            wait_seconds = int(getattr(e, "retry_after", 2)) + 1
            log_event(
                "TECNICO_SEND_RETRY_AFTER",
                chat_id=chat_id,
                attempt=attempt,
                wait_seconds=wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
            last_error = e

        except (TimedOut, NetworkError) as e:
            wait_seconds = attempt
            log_event(
                "TECNICO_SEND_RETRY",
                chat_id=chat_id,
                attempt=attempt,
                error=str(e),
                wait_seconds=wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
            last_error = e

        except Exception:
            raise

    if last_error:
        raise last_error


async def _send_document_bytes(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    content: bytes,
    filename: str,
    caption: str = "",
    attempts: int = 3,
):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            bio = io.BytesIO(content)
            bio.name = filename

            await context.bot.send_document(
                chat_id=chat_id,
                document=bio,
                filename=filename,
                caption=caption or None,
            )
            return

        except RetryAfter as e:
            wait_seconds = int(getattr(e, "retry_after", 2)) + 1
            log_event(
                "TECNICO_DOC_RETRY_AFTER",
                chat_id=chat_id,
                attempt=attempt,
                wait_seconds=wait_seconds,
                filename=filename,
            )
            await asyncio.sleep(wait_seconds)
            last_error = e

        except (TimedOut, NetworkError) as e:
            wait_seconds = attempt
            log_event(
                "TECNICO_DOC_RETRY",
                chat_id=chat_id,
                attempt=attempt,
                error=str(e),
                wait_seconds=wait_seconds,
                filename=filename,
            )
            await asyncio.sleep(wait_seconds)
            last_error = e

        except Exception:
            raise

    if last_error:
        raise last_error


def _save_tecnico_selection(chat_id: int, slot: int, nombre: str, empresa: str) -> None:
    set_data(chat_id, f"tecnico_{slot}_nombre", nombre)
    set_data(chat_id, f"tecnico_{slot}_empresa", empresa)


async def _send_sctr_info(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    nombre: str,
    empresa: str,
):
    try:
        record = _find_sctr_record(nombre, empresa)
    except Exception as e:
        log_event("SCTR_LOOKUP_ERROR", chat_id=chat_id, nombre=nombre, empresa=empresa, error=str(e))
        return

    if not record:
        log_event("SCTR_NOT_FOUND", chat_id=chat_id, nombre=nombre, empresa=empresa)
        return

    log_event("SCTR_FOUND", chat_id=chat_id, nombre=nombre, empresa=empresa)

    await _send_message(
        context,
        chat_id,
        _build_sctr_message(record)
    )

    file_id = str(record.get("file_id_drive", "")).strip()
    if not file_id:
        log_event("SCTR_FILE_ID_EMPTY", chat_id=chat_id, nombre=nombre, empresa=empresa)
        return

    try:
        content, filename, mime_type = download_drive_file_bytes(file_id)
        log_event(
            "SCTR_FILE_DOWNLOADED",
            chat_id=chat_id,
            nombre=nombre,
            empresa=empresa,
            filename=filename,
            mime_type=mime_type,
        )

        await _send_document_bytes(
            context,
            chat_id,
            content=content,
            filename=filename,
        )

    except Exception as e:
        log_event(
            "SCTR_FILE_DOWNLOAD_ERROR",
            chat_id=chat_id,
            nombre=nombre,
            empresa=empresa,
            file_id=file_id,
            error=str(e),
        )
        await _send_message(
            context,
            chat_id,
            "⚠️ Se encontró el registro SCTR, pero no se pudo descargar el PDF."
        )


async def _go_to_tipo_supervision(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    current_step: int,
):
    next_step = current_step + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "WAITING_TIPO_SUPERVISION")

    await _send_message(
        context,
        chat_id,
        _build_tipo_supervision_prompt(next_step),
        reply_markup=_build_tipo_supervision_keyboard(),
    )


async def _go_to_placa_unidad(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    current_step: int,
):
    next_step = current_step + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "INPUT_PLACA_UNIDAD")

    await _send_message(
        context,
        chat_id,
        _build_placa_unidad_prompt(next_step),
    )


async def _after_tecnico_selected(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    slot: int,
    current_step: int,
):
    if slot == 1:
        set_state(chat_id, "WAIT_TECNICO_2_DECISION")
        await _send_message(
            context,
            chat_id,
            "¿Deseas ingresar Técnico 2?",
            reply_markup=_build_si_no_keyboard("2"),
        )
        return

    if slot == 2:
        set_state(chat_id, "WAIT_TECNICO_3_DECISION")
        await _send_message(
            context,
            chat_id,
            "¿Deseas ingresar Técnico 3?",
            reply_markup=_build_si_no_keyboard("3"),
        )
        return

    if slot == 3:
        await _go_to_tipo_supervision(context, chat_id, current_step)
        return


# =========================
# CALLBACK PRINCIPAL
# =========================
async def tecnico_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("TECNICO_CALLBACK", chat_id=chat_id, action=action, data=data)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "SELECT" and len(parts) >= 3:
        try:
            index = int(parts[2])
        except Exception:
            await _send_message(context, chat_id, "⚠️ Selección inválida.")
            return

        results = get_data(chat_id, "tecnicos_cache", []) or []

        if index < 0 or index >= len(results):
            await _send_message(
                context,
                chat_id,
                "⚠️ La selección ya no es válida. Vuelve a buscar el técnico."
            )
            return

        item = results[index]
        nombre = str(item.get("nombre", "")).strip()
        empresa = str(item.get("empresa", "")).strip()

        if not nombre:
            await _send_message(
                context,
                chat_id,
                "⚠️ No se pudo recuperar el técnico seleccionado."
            )
            return

        slot = int(get_data(chat_id, "tecnico_slot", 1))
        current_step = int(get_data(chat_id, "current_step_number", 3))

        _save_tecnico_selection(chat_id, slot, nombre, empresa)

        log_event(
            "TECNICO_SELECTED_FROM_BUTTON",
            chat_id=chat_id,
            slot=slot,
            index=index,
            nombre=nombre,
        )

        await _send_message(
            context,
            chat_id,
            f"✅ Técnico {slot} seleccionado:\n{nombre}\n{empresa}"
        )

        await _send_sctr_info(context, chat_id, nombre, empresa)
        await _after_tecnico_selected(context, chat_id, slot, current_step)
        return

    if action == "ADD" and len(parts) >= 4:
        next_slot = int(parts[2])
        decision = parts[3].strip().upper()
        current_step = int(get_data(chat_id, "current_step_number", 3))

        if decision == "SI":
            next_step = current_step + 1
            set_data(chat_id, "tecnico_slot", next_slot)
            set_data(chat_id, "current_step_number", next_step)
            set_state(chat_id, "SEARCH_TECNICO")

            await _send_message(
                context,
                chat_id,
                _build_tecnico_prompt(next_step, next_slot)
            )
            return

        if decision == "NO":
            if next_slot == 2:
                set_state(chat_id, "WAIT_TECNICO_3_DECISION")
                await _send_message(
                    context,
                    chat_id,
                    "¿Deseas ingresar Técnico 3?",
                    reply_markup=_build_si_no_keyboard("3"),
                )
                return

            if next_slot == 3:
                await _go_to_tipo_supervision(context, chat_id, current_step)
                return

    await _send_message(
        context,
        chat_id,
        "⚠️ Opción no válida para técnico."
    )


# =========================
# INPUT BÚSQUEDA
# =========================
async def tecnico_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if len(text) < 2:
        await _send_message(
            context,
            chat_id,
            "⚠️ Escribe al menos 2 caracteres para buscar."
        )
        return

    results = _filter_tecnicos(text)
    slot = int(get_data(chat_id, "tecnico_slot", 1))
    current_step = int(get_data(chat_id, "current_step_number", 3))

    log_event("TECNICO_SEARCH", chat_id=chat_id, query=text, results=len(results), slot=slot)

    if not results:
        await _send_message(
            context,
            chat_id,
            "❌ No encontré coincidencias.\n\nPrueba con otro nombre o apellido."
        )
        return

    dedup = []
    seen = set()
    for r in results:
        key = (
            str(r.get("nombre", "")).strip().upper(),
            str(r.get("empresa", "")).strip().upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    results = dedup

    log_event("TECNICO_SEARCH_DEDUP", chat_id=chat_id, query=text, results=len(results), slot=slot)

    if len(results) == 1:
        r = results[0]
        nombre = str(r.get("nombre", "")).strip()
        empresa = str(r.get("empresa", "")).strip()

        _save_tecnico_selection(chat_id, slot, nombre, empresa)

        log_event(
            "TECNICO_AUTO_SELECTED",
            chat_id=chat_id,
            slot=slot,
            nombre=nombre,
        )

        await _send_message(
            context,
            chat_id,
            f"✅ Técnico {slot} seleccionado automáticamente:\n{nombre}\n{empresa}"
        )

        await _send_sctr_info(context, chat_id, nombre, empresa)
        await _after_tecnico_selected(context, chat_id, slot, current_step)
        return

    set_data(chat_id, "tecnicos_cache", results[:8])

    await _send_message(
        context,
        chat_id,
        f"🔎 Encontré {len(results)} coincidencias. Selecciona un técnico:",
        reply_markup=_build_tecnicos_keyboard(results),
    )


# =========================
# INPUT MANUAL
# =========================
async def tecnico_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await _send_message(
            context,
            chat_id,
            "❌ Nombre inválido."
        )
        return

    slot = int(get_data(chat_id, "tecnico_slot", 1))
    current_step = int(get_data(chat_id, "current_step_number", 3))

    _save_tecnico_selection(chat_id, slot, text, "MANUAL")

    log_event("TECNICO_MANUAL", chat_id=chat_id, slot=slot, nombre=text)

    await _send_message(
        context,
        chat_id,
        f"✅ Técnico {slot} registrado:\n{text}\nMANUAL"
    )

    await _send_sctr_info(context, chat_id, text, "MANUAL")
    await _after_tecnico_selected(context, chat_id, slot, current_step)


# =========================
# INPUT PLACA DE UNIDAD
# =========================
async def placa_unidad_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await _send_message(
            context,
            chat_id,
            "❌ Ingresa una placa válida."
        )
        return

    current_step = int(get_data(chat_id, "current_step_number", 3))
    set_data(chat_id, "placa_unidad", text)

    log_event("PLACA_UNIDAD_SET", chat_id=chat_id, placa=text)

    await _send_message(
        context,
        chat_id,
        f"✅ Placa de unidad registrada:\n{text}"
    )

    next_step = current_step + 1
    set_data(chat_id, "current_step_number", next_step)
    set_state(chat_id, "INPUT_CODIGO_PEDIDO")

    await _send_message(
        context,
        chat_id,
        _build_codigo_pedido_prompt(next_step),
    )