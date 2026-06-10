# =========================
# handlers/final_handler.py
# Finalización de supervisión
# Flujo:
# Confirmar → Observaciones finales → Estado final → Guardar → Resumen
# Compatible con headers actuales de Supervisiones_v2
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


def _maps_link(lat, lon) -> str:
    lat = _safe_text(lat)
    lon = _safe_text(lon)
    if not lat or not lon:
        return ""
    return f"https://www.google.com/maps?q={lat},{lon}"


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
# OBSERVACIONES / EVIDENCIAS
# =========================
def _get_evidencias(chat_id: int) -> list:
    evidencias = get_data(chat_id, "evidencias", [])
    return evidencias if isinstance(evidencias, list) else []


def _normalize_key(value: str) -> str:
    return _safe_text(value).upper().replace(" ", "_").replace("-", "_")


def _get_obs_by_keywords(chat_id: int, keywords: list[str]) -> str:
    """
    Busca observaciones dentro de la lista evidencias.
    Funciona con tipo/opcional_tipo/opcional_subopcion.
    """
    keys = [_normalize_key(k) for k in keywords]
    found = []

    for ev in _get_evidencias(chat_id):
        tipo = _normalize_key(ev.get("tipo"))
        opcional_tipo = _normalize_key(ev.get("opcional_tipo"))
        opcional_subopcion = _normalize_key(ev.get("opcional_subopcion"))
        resultado = _safe_text(ev.get("resultado"))
        observacion = _safe_text(ev.get("observacion"))

        searchable = "|".join([tipo, opcional_tipo, opcional_subopcion])
        if any(k in searchable for k in keys):
            parts = []
            if resultado:
                parts.append(f"Resultado: {resultado}")
            if observacion:
                parts.append(f"Obs: {observacion}")
            if parts:
                found.append(" / ".join(parts))

    return "\n".join(found)


def _has_evidence_by_keywords(chat_id: int, keywords: list[str]) -> str:
    keys = [_normalize_key(k) for k in keywords]
    for ev in _get_evidencias(chat_id):
        tipo = _normalize_key(ev.get("tipo"))
        opcional_tipo = _normalize_key(ev.get("opcional_tipo"))
        opcional_subopcion = _normalize_key(ev.get("opcional_subopcion"))
        searchable = "|".join([tipo, opcional_tipo, opcional_subopcion])
        if any(k in searchable for k in keys):
            return "SI"
    return "NO"


def _serialize_evidencias(chat_id: int) -> str:
    evidencias = _get_evidencias(chat_id)
    if not evidencias:
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
        lines.append(f"{idx}) tipo={tipo} | media_type={media_type} | file_id={file_id}{extra}")

    return "\n".join(lines)


def _serialize_modules(chat_id: int) -> str:
    lines = []
    for mod in _get_modules_summary(chat_id):
        lines.append(f"- {mod['nombre']}")
        lines.append(f"Estado: {mod['estado']}")
        lines.append(f"Tiempo: {mod['tiempo']}")
        lines.append("")
    return "\n".join(lines).strip()


# =========================
# PAYLOAD GOOGLE SHEET
# =========================
def _build_supervision_payload(chat_id: int) -> dict:
    data = get_all_data(chat_id)
    resumen_steps = get_all_steps_summary(chat_id)
    duration_seconds, start_str, end_str = _compute_total_duration(chat_id)

    lat = _safe_text(data.get("ubicacion_lat"))
    lon = _safe_text(data.get("ubicacion_lon"))

    drop_cto_lat = _safe_text(data.get("drop_ext_cto_lat") or data.get("info_drop_ext_cto_lat") or data.get("Drop_Externo_CTO_Latitud"))
    drop_cto_lon = _safe_text(data.get("drop_ext_cto_lon") or data.get("info_drop_ext_cto_lon") or data.get("Drop_Externo_CTO_Longitud"))
    drop_dom_lat = _safe_text(data.get("drop_ext_dom_lat") or data.get("info_drop_ext_dom_lat") or data.get("Drop_Externo_Domicilio_Latitud"))
    drop_dom_lon = _safe_text(data.get("drop_ext_dom_lon") or data.get("info_drop_ext_dom_lon") or data.get("Drop_Externo_Domicilio_Longitud"))

    # Todos los nombres deben coincidir exactamente con los headers de Supervisiones_v2.
    payload = {
        "ID_Supervision": _safe_text(data.get("id_supervision")) or f"SUP-{int(now_peru_dt().timestamp())}",
        "ESTADO": "FINALIZADA",
        "Fecha_Creacion": start_str or now_peru_str(),
        "Fecha_Cierre": end_str,

        "Supervisor": _safe_text(data.get("supervisor")),
        "Operador": _safe_text(data.get("empresa")) or _safe_text(data.get("operador")),
        "Técnico": _safe_text(data.get("tecnico_1_nombre")),
        "Contrata": _safe_text(data.get("contrata")) or _safe_text(data.get("empresa")) or _safe_text(data.get("tecnico_1_empresa")),
        "Gestor": _safe_text(data.get("gestor")),
        "Código_Pedido": _safe_text(data.get("codigo_pedido")),
        "Tipo_Supervision": _safe_text(data.get("tipo_supervision")),
        "Distrito": _safe_text(data.get("distrito")),
        "Latitud": lat,
        "Longitud": lon,
        "Link_Ubicacion": _maps_link(lat, lon),

        "Obs_CTO": _get_obs_by_keywords(chat_id, ["CTO"]),
        "Obs_POSTE": _get_obs_by_keywords(chat_id, ["POSTE"]),
        "Obs_RUTA": _get_obs_by_keywords(chat_id, ["RUTA"]),
        "Obs_FALSO_TRAMO": _get_obs_by_keywords(chat_id, ["FALSO_TRAMO", "FALSO"]),
        "Obs_RESERVA_DOMICILIO": _get_obs_by_keywords(chat_id, ["RESERVA_DOMICILIO", "RESERVA"]),
        "Obs_ROSETA": _get_obs_by_keywords(chat_id, ["ROSETA"]),
        "Obs_EQUIPOS": _get_obs_by_keywords(chat_id, ["EQUIPOS", "EQUIPO"]),
        "Obs_TECNICOS": _get_obs_by_keywords(chat_id, ["TECNICOS", "TECNICO", "FOTO_TECNICOS"]),
        "Obs_SCTR": _get_obs_by_keywords(chat_id, ["SCTR"]),
        "Obs_ATS": _get_obs_by_keywords(chat_id, ["ATS"]),
        "Obs_LICENCIA": _get_obs_by_keywords(chat_id, ["LICENCIA"]),
        "Obs_UNIDAD": _get_obs_by_keywords(chat_id, ["UNIDAD", "VEHICULO"]),
        "Obs_SOAT": _get_obs_by_keywords(chat_id, ["SOAT"]),
        "Obs_HERRAMIENTAS": _get_obs_by_keywords(chat_id, ["HERRAMIENTAS", "HERRAMIENTA"]),
        "Obs_KIT_FIBRA": _get_obs_by_keywords(chat_id, ["KIT_FIBRA", "KIT"]),
        "Obs_ESCALERA_TELESCOPICA": _get_obs_by_keywords(chat_id, ["ESCALERA_TEL", "ESCALERA_TELESCOPICA"]),
        "Obs_ESCALERA_INTERNOS": _get_obs_by_keywords(chat_id, ["ESCALERA_INT", "ESCALERA_INTERNOS"]),
        "Obs_BOTIQUIN": _get_obs_by_keywords(chat_id, ["BOTIQUIN"]),
        "Obs_ADICIONALES": _get_obs_by_keywords(chat_id, ["ADICIONALES", "OPCIONALES"]),
        "Obs_FINALES": _safe_text(data.get("observaciones_finales")),

        "PlantillaUUID": _safe_text(data.get("PlantillaUUID")) or _safe_text(data.get("plantilla_uuid")),
        "Origin_Chat_ID": _safe_text(data.get("origin_chat_id")) or _safe_text(chat_id),
        "Evidence_Chat_ID": _safe_text(data.get("evidence_chat_id")),
        "Summary_Chat_ID": _safe_text(data.get("summary_chat_id")),
        "Creado_Por": _safe_text(data.get("creado_por")) or _safe_text(data.get("supervisor")),
        "Cancelado_Por": _safe_text(data.get("cancelado_por")),
        "Motivo_Cancelacion": _safe_text(data.get("motivo_cancelacion")),
        "Updated_At": now_peru_str(),
        "Estado_Final": _safe_text(data.get("estado_final")) or "CORRECTA",

        "Drop_Externo_CTO_Latitud": drop_cto_lat,
        "Drop_Externo_CTO_Longitud": drop_cto_lon,
        "Drop_Externo_CTO_Link_Ubicacion": _maps_link(drop_cto_lat, drop_cto_lon),
        "Drop_Externo_Domicilio_Latitud": drop_dom_lat,
        "Drop_Externo_Domicilio_Longitud": drop_dom_lon,
        "Drop_Externo_Domicilio_Link_Ubicacion": _maps_link(drop_dom_lat, drop_dom_lon),
        "Metraje_Drop_Externo": _safe_text(data.get("info_drop_ext_metraje")) or _safe_text(data.get("metraje_drop_externo")),
        "Metraje_Drop_Interno": _safe_text(data.get("info_drop_int")) or _safe_text(data.get("metraje_drop_interno")),
        "Cantidad_Postes_Usados": _safe_text(data.get("info_postes")) or _safe_text(data.get("cantidad_postes_usados")),
        "Cantidad_Falsos_Tramos": _safe_text(data.get("info_falsos")) or _safe_text(data.get("cantidad_falsos_tramos")),
        "Cantidad_Templadores_Aprox": _safe_text(data.get("info_templadores")) or _safe_text(data.get("cantidad_templadores_aprox")),
        "Captura_Recorrido_Obs": _safe_text(data.get("info_recorrido_obs")) or _safe_text(data.get("info_recorrido_file_id")),
        "Info_Tecnico_Acta_Correcta": _safe_text(data.get("info_validacion_acta")),
        "Captura_Recorrido_Cargado": "SI" if _safe_text(data.get("info_recorrido_file_id")) else "NO",
        "Updated_At_Info_Supervision": now_peru_str(),
        "Fecha_sup": (end_str or now_peru_str())[:10],
    }

    # Campos extra no se guardan en Sheet porque no existen como headers,
    # pero se dejan disponibles por si luego agregas columnas.
    payload.update({
        "evidencias_resumen": str(resumen_steps),
        "evidencias_detalle": _serialize_evidencias(chat_id),
        "modulos_resumen": _serialize_modules(chat_id),
        "duracion_total_segundos": int(duration_seconds),
        "duracion_total": _format_duration(duration_seconds),
    })

    return payload


# =========================
# TEXTO DE ÉXITO
# =========================
def _build_success_text(payload: dict, chat_id: int) -> str:
    cuadrilla = _safe_text(get_data(chat_id, "cuadrilla")) or "-"
    placa_unidad = _safe_text(get_data(chat_id, "placa_unidad")) or "-"
    codigo = _safe_text(payload.get("Código_Pedido")) or "-"
    estado = _safe_text(payload.get("ESTADO")) or "FINALIZADA"
    estado_final = _safe_text(payload.get("Estado_Final")) or "-"
    distrito = _safe_text(payload.get("Distrito")) or "-"
    duracion = _safe_text(payload.get("duracion_total")) or "-"
    observaciones = _safe_text(payload.get("Obs_FINALES")) or "-"

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
    lines.append("📊 Sheets: OK")

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
