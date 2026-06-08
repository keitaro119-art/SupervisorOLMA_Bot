# =========================
# handlers/final_handler.py
# Finalización de supervisión
# Flujo:
# Confirmar → Observaciones finales → Estado final → Guardar → Resumen
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import (
    set_state,
    set_data,
    get_data,
    get_all_data,
    clear_data,
)
from utils.logger import log_event
from services.google_sheets_service import save_supervision_row
from handlers.step_handler import get_all_steps_summary
from config import now_peru_str, now_peru_dt


# =========================
# HELPERS UI
# =========================
def _build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar finalización", callback_data="FINAL|CONFIRM")],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="MENU|BACK")],
    ])


def _build_estado_final_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ CORRECTA", callback_data="FINAL|ESTADO|CORRECTA"),
            InlineKeyboardButton("⚠️ OBSERVADA", callback_data="FINAL|ESTADO|OBSERVADA"),
        ]
    ])


def _safe_text(value) -> str:
    return str(value or "").strip()


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
    if secs > 0 or not parts:
        parts.append(f"{secs} seg")

    return " ".join(parts)


def _format_duration_short(seconds_text: str) -> str:
    text = _safe_text(seconds_text)
    if not text:
        return "-"
    return text.replace(" h", "h").replace(" min", "m").replace(" seg", "s")


def _compute_total_duration(chat_id: int) -> tuple[float, str, str]:
    start_ts = _safe_float(get_data(chat_id, "supervision_start_ts", 0.0), 0.0)
    start_str = _safe_text(get_data(chat_id, "supervision_start_str", ""))

    end_dt = now_peru_dt()
    end_ts = end_dt.timestamp()
    end_str = now_peru_str()

    duration_seconds = max(0.0, end_ts - start_ts) if start_ts > 0 else 0.0
    return duration_seconds, start_str, end_str


# =========================
# MÓDULOS
# =========================
MODULES = [
    ("instalacion", "Supervision de Instalación"),
    ("herramientas", "Herramientas"),
    ("epp", "EPP"),
    ("epe", "EPE"),
    ("uniformes", "Uniformes"),
    ("vehiculo", "Vehículo"),
    ("opcionales", "Evidencias opcionales"),
    ("info", "Información de Supervision"),
]


def _get_module_info(chat_id: int, key: str) -> dict:
    estado = _safe_text(get_data(chat_id, f"mod_{key}_estado", ""))
    duracion = _safe_text(get_data(chat_id, f"mod_{key}_duracion", ""))

    return {
        "key": key,
        "nombre": dict(MODULES).get(key, key),
        "estado": estado if estado else "-",
        "tiempo": _format_duration_short(duracion) if duracion else "-",
    }


def _get_modules_summary(chat_id: int) -> list[dict]:
    return [_get_module_info(chat_id, key) for key, _ in MODULES]


# =========================
# SERIALIZACIÓN
# =========================
def _serialize_evidencias(chat_id: int) -> str:
    evidencias = get_data(chat_id, "evidencias", [])
    if not isinstance(evidencias, list) or not evidencias:
        return ""

    lines = []
    for idx, ev in enumerate(evidencias, start=1):
        tipo = _safe_text(ev.get("tipo"))
        media_type = _safe_text(ev.get("media_type"))
        file_id = _safe_text(ev.get("file_id"))
        resultado = _safe_text(ev.get("resultado"))
        observacion = _safe_text(ev.get("observacion"))
        opcional_tipo = _safe_text(ev.get("opcional_tipo"))
        opcional_subopcion = _safe_text(ev.get("opcional_subopcion"))

        extra_parts = []
        if resultado:
            extra_parts.append(f"resultado={resultado}")
        if observacion:
            extra_parts.append(f"observacion={observacion}")
        if opcional_tipo:
            extra_parts.append(f"opcional_tipo={opcional_tipo}")
        if opcional_subopcion:
            extra_parts.append(f"opcional_subopcion={opcional_subopcion}")

        extra = " | " + " | ".join(extra_parts) if extra_parts else ""

        lines.append(
            f"{idx}) tipo={tipo} | media_type={media_type} | file_id={file_id}{extra}"
        )

    return "\n".join(lines)


def _serialize_modules(chat_id: int) -> str:
    lines = []

    for mod in _get_modules_summary(chat_id):
        lines.append(f"- {mod['nombre']}")
        lines.append(f"Estado: {mod['estado']}")
        lines.append(f"Tiempo: {mod['tiempo']}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_supervision_payload(chat_id: int) -> dict:
    data = get_all_data(chat_id)
    resumen_steps = get_all_steps_summary(chat_id)
    duration_seconds, start_str, end_str = _compute_total_duration(chat_id)

    payload = {
        "registrado_en": now_peru_str(),
        "hora_inicio": start_str,
        "hora_fin": end_str,
        "duracion_total_segundos": int(duration_seconds),
        "duracion_total": _format_duration(duration_seconds),

        "supervisor": _safe_text(data.get("supervisor")),
        "empresa": _safe_text(data.get("empresa")),
        "cuadrilla": _safe_text(data.get("cuadrilla")),
        "placa_unidad": _safe_text(data.get("placa_unidad")),
        "codigo_pedido": _safe_text(data.get("codigo_pedido")),
        "distrito": _safe_text(data.get("distrito")),
        "tipo_supervision": _safe_text(data.get("tipo_supervision")),

        "tecnico_1_nombre": _safe_text(data.get("tecnico_1_nombre")),
        "tecnico_1_empresa": _safe_text(data.get("tecnico_1_empresa")),
        "tecnico_2_nombre": _safe_text(data.get("tecnico_2_nombre")),
        "tecnico_2_empresa": _safe_text(data.get("tecnico_2_empresa")),
        "tecnico_3_nombre": _safe_text(data.get("tecnico_3_nombre")),
        "tecnico_3_empresa": _safe_text(data.get("tecnico_3_empresa")),

        "ubicacion_lat": _safe_text(data.get("ubicacion_lat")),
        "ubicacion_lon": _safe_text(data.get("ubicacion_lon")),
        "selfie_fachada_file_id": _safe_text(data.get("selfie_fachada_file_id")),
        "selfie_fachada_file_unique_id": _safe_text(data.get("selfie_fachada_file_unique_id")),

        "info_drop_ext": str(data.get("info_drop_ext", {})),
        "info_drop_ext_metraje": _safe_text(data.get("info_drop_ext_metraje")),
        "info_drop_int": _safe_text(data.get("info_drop_int")),
        "info_postes": _safe_text(data.get("info_postes")),
        "info_falsos": _safe_text(data.get("info_falsos")),
        "info_templadores": _safe_text(data.get("info_templadores")),
        "info_recorrido_file_id": _safe_text(data.get("info_recorrido_file_id")),
        "info_validacion_acta": _safe_text(data.get("info_validacion_acta")),

        "observaciones_finales": _safe_text(data.get("observaciones_finales")),

        "evidencias_resumen": str(resumen_steps),
        "evidencias_detalle": _serialize_evidencias(chat_id),
        "modulos_resumen": _serialize_modules(chat_id),

        "mod_instalacion_estado": _safe_text(get_data(chat_id, "mod_instalacion_estado")),
        "mod_instalacion_duracion": _safe_text(get_data(chat_id, "mod_instalacion_duracion")),
        "mod_herramientas_estado": _safe_text(get_data(chat_id, "mod_herramientas_estado")),
        "mod_herramientas_duracion": _safe_text(get_data(chat_id, "mod_herramientas_duracion")),
        "mod_epp_estado": _safe_text(get_data(chat_id, "mod_epp_estado")),
        "mod_epp_duracion": _safe_text(get_data(chat_id, "mod_epp_duracion")),
        "mod_epe_estado": _safe_text(get_data(chat_id, "mod_epe_estado")),
        "mod_epe_duracion": _safe_text(get_data(chat_id, "mod_epe_duracion")),
        "mod_uniformes_estado": _safe_text(get_data(chat_id, "mod_uniformes_estado")),
        "mod_uniformes_duracion": _safe_text(get_data(chat_id, "mod_uniformes_duracion")),
        "mod_vehiculo_estado": _safe_text(get_data(chat_id, "mod_vehiculo_estado")),
        "mod_vehiculo_duracion": _safe_text(get_data(chat_id, "mod_vehiculo_duracion")),
        "mod_opcionales_estado": _safe_text(get_data(chat_id, "mod_opcionales_estado")),
        "mod_opcionales_duracion": _safe_text(get_data(chat_id, "mod_opcionales_duracion")),
        "mod_info_estado": _safe_text(get_data(chat_id, "mod_info_estado")),
        "mod_info_duracion": _safe_text(get_data(chat_id, "mod_info_duracion")),

        "estado_supervision": "FINALIZADA",
        "estado": "Completado",
        "estado_final": _safe_text(data.get("estado_final")) or "CORRECTA",
        "sheets_estado": "OK",
    }

    return payload


def _build_success_text(payload: dict, chat_id: int) -> str:
    cuadrilla = _safe_text(payload.get("cuadrilla")) or "-"
    placa_unidad = _safe_text(payload.get("placa_unidad")) or "-"
    codigo = _safe_text(payload.get("codigo_pedido")) or "-"
    estado = _safe_text(payload.get("estado")) or "Completado"
    estado_final = _safe_text(payload.get("estado_final")) or "-"
    distrito = _safe_text(payload.get("distrito")) or "-"
    duracion = _safe_text(payload.get("duracion_total")) or "-"
    observaciones = _safe_text(payload.get("observaciones_finales")) or "-"
    sheets_estado = _safe_text(payload.get("sheets_estado")) or "OK"

    lines = [
        "✅ SE FINALIZÓ SUPERVISIÓN",
        f"👷 Cuadrilla: {cuadrilla}",
        f"🚘 Placa unidad: {placa_unidad}",
        f"🧾 Código: {codigo}",
        f"📌 Estado: {estado}",
        f"✅ Estado final: {estado_final}",
        f"🏙️ Distrito: {distrito}",
        f"⏱️ Duración Total: {duracion}",
        f"📝 Observaciones: {observaciones}",
        "-------------------------",
        "📋 MODULOS",
        "-------------------------",
    ]

    for mod in _get_modules_summary(chat_id):
        lines.append(f"- {mod['nombre']}")
        lines.append(f"Estado: {mod['estado']}")
        lines.append(f"Tiempo: {mod['tiempo']}")
        lines.append("")

    lines.append("-------------------")
    lines.append(f"📊 Sheets: {sheets_estado}")

    return "\n".join(lines).strip()


# =========================
# INPUT OBSERVACIONES FINALES
# =========================
async def observaciones_finales_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Ingresa una observación válida. Si no hay observación, escribe: SIN OBSERVACIONES"
        )
        return

    set_data(chat_id, "observaciones_finales", text)
    set_state(chat_id, "WAIT_ESTADO_FINAL")

    await context.bot.send_message(
        chat_id=chat_id,
        text="INDICAR ESTADO FINAL DE LA SUPERVISIÓN",
        reply_markup=_build_estado_final_keyboard()
    )


# =========================
# GUARDAR Y FINALIZAR
# =========================
async def _save_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, estado_final: str):
    query = update.callback_query
    chat_id = update.effective_chat.id

    set_data(chat_id, "estado_final", estado_final)

    payload = _build_supervision_payload(chat_id)

    try:
        save_supervision_row(payload, queued=True)
        log_event("FINAL_SAVE_OK", chat_id=chat_id)
    except Exception as e:
        log_event("FINAL_SAVE_ERROR", chat_id=chat_id, error=str(e))

        try:
            await query.edit_message_text(
                text="❌ Ocurrió un error al guardar la supervisión. Intenta nuevamente."
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Ocurrió un error al guardar la supervisión. Intenta nuevamente."
            )
        return

    success_text = _build_success_text(payload, chat_id)

    clear_data(chat_id)
    set_state(chat_id, "START")

    try:
        await query.edit_message_text(text=success_text)
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=success_text)


# =========================
# CALLBACK PRINCIPAL
# =========================
async def final_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""
    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("FINAL_CALLBACK", chat_id=chat_id, action=action, data=data)

    if action == "ASK":
        set_state(chat_id, "CONFIRM_FINAL")

        try:
            await query.edit_message_text(
                text="⚠️ ¿Deseas finalizar la supervisión?",
                reply_markup=_build_confirm_keyboard()
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ ¿Deseas finalizar la supervisión?",
                reply_markup=_build_confirm_keyboard()
            )
        return

    if action == "CONFIRM":
        set_state(chat_id, "INPUT_OBSERVACIONES_FINALES")

        try:
            await query.edit_message_text(
                text="INGRESAR OBSERVACIONES FINALES\n\nEscribe el comentario final en texto libre.\n\nSi no hay observaciones, escribe: SIN OBSERVACIONES"
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="INGRESAR OBSERVACIONES FINALES\n\nEscribe el comentario final en texto libre.\n\nSi no hay observaciones, escribe: SIN OBSERVACIONES"
            )
        return

    if action == "ESTADO" and len(parts) >= 3:
        estado_final = str(parts[2]).strip().upper()

        if estado_final not in {"CORRECTA", "OBSERVADA"}:
            await query.answer("⚠️ Estado final inválido.", show_alert=True)
            return

        await _save_and_finish(update, context, estado_final)
        return

    await query.answer("⚠️ Opción inválida.", show_alert=True)