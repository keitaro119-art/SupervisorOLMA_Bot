# =========================
# handlers/step_handler.py
# Flujo real de evidencias
# Incluye flujo especial para Evidencias opcionales
# con resultado por ítem:
# Cumple / No cumple / No aplica / Observado
# El cierre de módulo YA NO se dispara al terminar cada ítem.
# Ahora solo vuelve al submenú; el cierre lo maneja menu_handler con "Volver".
# Al cerrar módulo, regresa al MENÚ DE SUPERVISIÓN.
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import (
    set_state,
    set_data,
    get_data,
)
from utils.logger import log_event, log_media
from utils.helpers import extract_file_id, now_str
from services.metrics_service import track_time
from services.rate_limit_service import is_allowed
from config import now_peru_dt


# =========================
# MENÚS DE PASOS
# =========================
INSTALACION_STEPS = {
    "CTO": "CTO",
    "POSTE": "POSTE",
    "RUTA": "RUTA",
    "FALSO_TRAMO": "FALSO_TRAMO",
    "ANCLAJE": "ANCLAJE",
    "RESERVA_DOMICILIO": "RESERVA_DOMICILIO",
    "ROSETA": "ROSETA",
    "EQUIPOS": "EQUIPOS",
}

HERRAMIENTAS_STEPS = {
    "ALICATE_CORTE": "ALICATE_CORTE",
    "ALICATE_PINZAS": "ALICATE_PINZAS",
    "ALICATE_UNIVERSAL": "ALICATE_UNIVERSAL",
    "CRIMPING_TOOL": "CRIMPING_TOOL",
    "DESTORNILLADOR_ESTRELLA": "DESTORNILLADOR_ESTRELLA",
    "DESTORNILLADOR_PLANO": "DESTORNILLADOR_PLANO",
    "MARTILLO": "MARTILLO",
    "TESTEADOR_UTP": "TESTEADOR_UTP",
    "TALADRO_PERCUSION": "TALADRO_PERCUSION",
    "BROCA_CEMENTO_30": "BROCA_CEMENTO_30",
    "BROCA_CEMENTO_15": "BROCA_CEMENTO_15",
    "BROCA_MADERA_15": "BROCA_MADERA_15",
    "WINCHA_PASACABLES": "WINCHA_PASACABLES",
    "EXTENSION_AC_20": "EXTENSION_AC_20",
    "ZUNCHADORA": "ZUNCHADORA",
    "PORTACARRETE": "PORTACARRETE",
}

EPP_STEPS = {
    "CASCO_SEGURIDAD": "CASCO_SEGURIDAD",
    "BARBIQUEJO": "BARBIQUEJO",
    "BOTAS_SEGURIDAD": "BOTAS_SEGURIDAD",
    "LENTES_SEGURIDAD": "LENTES_SEGURIDAD",
    "GUANTES_BADANA": "GUANTES_BADANA",
    "GUANTES_MULTIFLEX": "GUANTES_MULTIFLEX",
    "GUANTES_TELA": "GUANTES_TELA",
    "GUANTES_DIELECTRICOS": "GUANTES_DIELECTRICOS",
    "CINTURON_POSICIONAMIENTO": "CINTURON_POSICIONAMIENTO",
}

EPE_STEPS = {
    "CONOS": "CONOS",
    "BARRAS_RETRACTILES": "BARRAS_RETRACTILES",
    "ESCALERA_TIJERA_6": "ESCALERA_TIJERA_6",
    "ESCALERA_TELESCOPICA_28": "ESCALERA_TELESCOPICA_28",
    "REVELADOR_TENSION": "REVELADOR_TENSION",
}

UNIFORMES_STEPS = {
    "POLO": "POLO",
    "CHALECO": "CHALECO",
    "PANTALON": "PANTALON",
    "FOTOCHECK": "FOTOCHECK",
}

VEHICULO_STEPS = {
    "EXTINTOR": "EXTINTOR",
    "BOTIQUIN": "BOTIQUIN",
    "LICENCIA_CONDUCIR": "LICENCIA_CONDUCIR",
    "SOAT": "SOAT",
    "REVISION_TECNICA": "REVISION_TECNICA",
    "TARJETA_PROPIEDAD": "TARJETA_PROPIEDAD",
    "PARRILLA_PORTAESCALERAS": "PARRILLA_PORTAESCALERAS",
    "TACOS_SEGURIDAD": "TACOS_SEGURIDAD",
    "LOGOS": "LOGOS",
}

OPCIONAL_STEP_CODE = "OPCIONAL_GENERAL"


# =========================
# RESULTADOS
# =========================
RESULT_CUMPLE = "CUMPLE"
RESULT_NO_CUMPLE = "NO_CUMPLE"
RESULT_NO_APLICA = "NO_APLICA"
RESULT_OBSERVADO = "OBSERVADO"

MODULE_STATUS_CORRECTO = "CORRECTO"
MODULE_STATUS_OBSERVADO = "OBSERVADO"


# =========================
# HELPERS GENERALES
# =========================
def _get_evidencias(chat_id: int):
    evidencias = get_data(chat_id, "evidencias", [])
    if not isinstance(evidencias, list):
        evidencias = []
    return evidencias


def _save_evidencias(chat_id: int, evidencias: list):
    set_data(chat_id, "evidencias", evidencias)


def _get_current_step(chat_id: int) -> str:
    return str(get_data(chat_id, "current_step", "") or "").strip()


def _set_current_step(chat_id: int, step: str):
    set_data(chat_id, "current_step", step)


async def _edit_or_send(query, context, chat_id: int, text: str, reply_markup=None):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )


def _step_bucket(step: str) -> str:
    if step in INSTALACION_STEPS.values():
        return "instalacion"
    if step in HERRAMIENTAS_STEPS.values():
        return "herramientas"
    if step in EPP_STEPS.values():
        return "epp"
    if step in EPE_STEPS.values():
        return "epe"
    if step in UNIFORMES_STEPS.values():
        return "uniformes"
    if step in VEHICULO_STEPS.values():
        return "vehiculo"
    return "opcionales"


def _module_label(bucket: str) -> str:
    mapping = {
        "instalacion": "Supervision de Instalación",
        "herramientas": "Herramientas",
        "epp": "EPP",
        "epe": "EPE",
        "uniformes": "Uniformes",
        "vehiculo": "Vehículo",
        "opcionales": "Evidencias opcionales",
    }
    return mapping.get(bucket, "Módulo")


def _menu_code_for_step(step: str) -> str:
    bucket = _step_bucket(step)
    mapping = {
        "instalacion": "INSTALACION",
        "herramientas": "HERRAMIENTAS",
        "epp": "EPP",
        "epe": "EPE",
        "uniformes": "UNIFORMES",
        "vehiculo": "VEHICULO",
        "opcionales": "OPCIONAL",
    }
    return mapping.get(bucket, "BACK")


def _submenu_text_for_step(step: str) -> str:
    bucket = _step_bucket(step)
    mapping = {
        "instalacion": "SUPERVISION DE INSTALACIÓN",
        "herramientas": "HERRAMIENTAS",
        "epp": "EPP",
        "epe": "EPE",
        "uniformes": "UNIFORMES",
        "vehiculo": "VEHÍCULO",
        "opcionales": "EVIDENCIAS OPCIONALES",
    }
    return mapping.get(bucket, "MENÚ")


def _submenu_keyboard_for_step(step: str, chat_id: int):
    bucket = _step_bucket(step)

    if bucket == "instalacion":
        from handlers.menu_handler import build_menu_instalacion
        return build_menu_instalacion(chat_id)

    if bucket == "herramientas":
        from handlers.menu_handler import build_menu_herramientas
        return build_menu_herramientas(chat_id)

    if bucket == "epp":
        from handlers.menu_handler import build_menu_epp
        return build_menu_epp(chat_id)

    if bucket == "epe":
        from handlers.menu_handler import build_menu_epe
        return build_menu_epe(chat_id)

    if bucket == "uniformes":
        from handlers.menu_handler import build_menu_uniformes
        return build_menu_uniformes(chat_id)

    if bucket == "vehiculo":
        from handlers.menu_handler import build_menu_vehiculo
        return build_menu_vehiculo(chat_id)

    from handlers.menu_handler import build_menu_opcional
    return build_menu_opcional(chat_id)


def _build_back_menu_for_step(step: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Volver", callback_data=f"MENU|{_menu_code_for_step(step)}")]
    ])


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


def _set_module_data(chat_id: int, bucket: str, suffix: str, value):
    set_data(chat_id, f"mod_{bucket}_{suffix}", value)


def _get_module_data(chat_id: int, bucket: str, suffix: str, default=None):
    return get_data(chat_id, f"mod_{bucket}_{suffix}", default)


def _touch_module_start(chat_id: int, bucket: str):
    now_dt = now_peru_dt()

    _set_module_data(chat_id, bucket, "current", True)

    if not _get_module_data(chat_id, bucket, "inicio_ts"):
        _set_module_data(chat_id, bucket, "inicio_ts", now_dt.timestamp())
        _set_module_data(chat_id, bucket, "inicio_str", now_str())

    _set_module_data(chat_id, bucket, "fin_ts", "")
    _set_module_data(chat_id, bucket, "fin_str", "")
    _set_module_data(chat_id, bucket, "duracion_seg", "")
    _set_module_data(chat_id, bucket, "duracion", "")
    _set_module_data(chat_id, bucket, "estado", "")


def _close_module(chat_id: int, bucket: str, status_value: str):
    now_dt = now_peru_dt()
    start_ts = _get_module_data(chat_id, bucket, "inicio_ts", 0) or 0

    try:
        start_ts = float(start_ts)
    except Exception:
        start_ts = 0.0

    end_ts = now_dt.timestamp()
    duration_seconds = max(0.0, end_ts - start_ts) if start_ts > 0 else 0.0

    _set_module_data(chat_id, bucket, "fin_ts", end_ts)
    _set_module_data(chat_id, bucket, "fin_str", now_str())
    _set_module_data(chat_id, bucket, "duracion_seg", int(duration_seconds))
    _set_module_data(chat_id, bucket, "duracion", _format_duration(duration_seconds))
    _set_module_data(chat_id, bucket, "estado", status_value)
    _set_module_data(chat_id, bucket, "current", False)


def _reset_module_close_context(chat_id: int):
    set_data(chat_id, "module_close_bucket", "")
    set_data(chat_id, "module_close_step", "")


def _build_close_module_keyboard(step: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data=f"STEP|CLOSE_MODULE|SI|{step}"),
            InlineKeyboardButton("❌ NO", callback_data=f"STEP|CLOSE_MODULE|NO|{step}"),
        ]
    ])


def _build_module_status_keyboard(bucket: str, step: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ CORRECTO", callback_data=f"STEP|MODULE_STATUS|{bucket}|{step}|{MODULE_STATUS_CORRECTO}"),
            InlineKeyboardButton("⚠️ OBSERVADO", callback_data=f"STEP|MODULE_STATUS|{bucket}|{step}|{MODULE_STATUS_OBSERVADO}"),
        ]
    ])


async def _return_to_submenu(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    prefix_text: str = "",
):
    bucket = _step_bucket(step)
    state_map = {
        "instalacion": "MENU_INSTALACION",
        "herramientas": "MENU_HERRAMIENTAS",
        "epp": "MENU_EPP",
        "epe": "MENU_EPE",
        "uniformes": "MENU_UNIFORMES",
        "vehiculo": "MENU_VEHICULO",
        "opcionales": "MENU_OPCIONAL",
    }

    _set_current_step(chat_id, "")
    _reset_step_flow_context(chat_id)
    _reset_module_close_context(chat_id)
    set_state(chat_id, state_map.get(bucket, "MENU_SUPERVISION"))

    text = _submenu_text_for_step(step)
    if prefix_text:
        text = f"{prefix_text}\n\n{text}"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=_submenu_keyboard_for_step(step, chat_id)
    )


async def _return_to_main_menu(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    prefix_text: str = "",
):
    from handlers.menu_handler import build_menu_principal

    _set_current_step(chat_id, "")
    _reset_step_flow_context(chat_id)
    _reset_module_close_context(chat_id)
    set_state(chat_id, "MENU_SUPERVISION")

    text = "MENÚ DE SUPERVISIÓN"
    if prefix_text:
        text = f"{prefix_text}\n\n{text}"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=build_menu_principal(chat_id)
    )


def _resolve_step_from_callback(action: str):
    if action in INSTALACION_STEPS:
        return INSTALACION_STEPS[action]
    if action in HERRAMIENTAS_STEPS:
        return HERRAMIENTAS_STEPS[action]
    if action in EPP_STEPS:
        return EPP_STEPS[action]
    if action in EPE_STEPS:
        return EPE_STEPS[action]
    if action in UNIFORMES_STEPS:
        return UNIFORMES_STEPS[action]
    if action in VEHICULO_STEPS:
        return VEHICULO_STEPS[action]
    if action == "OPCIONAL":
        return OPCIONAL_STEP_CODE
    return None


# =========================
# HELPERS RESULTADO
# =========================
def _build_resultado_keyboard(step: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Cumple", callback_data=f"STEP|RESULT|{step}|{RESULT_CUMPLE}"),
            InlineKeyboardButton("❌ No cumple", callback_data=f"STEP|RESULT|{step}|{RESULT_NO_CUMPLE}"),
        ],
        [
            InlineKeyboardButton("➖ No aplica", callback_data=f"STEP|RESULT|{step}|{RESULT_NO_APLICA}"),
            InlineKeyboardButton("⚠️ Observado", callback_data=f"STEP|RESULT|{step}|{RESULT_OBSERVADO}"),
        ],
        [
            InlineKeyboardButton("⬅️ Volver", callback_data=f"MENU|{_menu_code_for_step(step)}")
        ]
    ])


def _result_label(result_code: str) -> str:
    labels = {
        RESULT_CUMPLE: "Cumple",
        RESULT_NO_CUMPLE: "No cumple",
        RESULT_NO_APLICA: "No aplica",
        RESULT_OBSERVADO: "Observado",
    }
    return labels.get(result_code, result_code)


def _result_requires_photo(result_code: str) -> bool:
    return result_code in (RESULT_NO_CUMPLE, RESULT_OBSERVADO)


def _result_allows_optional_photo(result_code: str) -> bool:
    return result_code == RESULT_CUMPLE


def _result_requires_comment_question(result_code: str) -> bool:
    return result_code in (RESULT_NO_CUMPLE, RESULT_OBSERVADO)


def _reset_step_flow_context(chat_id: int):
    set_data(chat_id, "step_resultado_actual", "")
    set_data(chat_id, "step_waiting_for_photo", False)
    set_data(chat_id, "step_waiting_for_comment_decision", False)
    set_data(chat_id, "step_waiting_for_comment_text", False)
    set_data(chat_id, "step_photo_required", False)
    set_data(chat_id, "step_photo_loaded", False)
    set_data(chat_id, "step_comentario_actual", "")
    set_data(chat_id, "step_temp_file_id", "")
    set_data(chat_id, "step_temp_media_type", "")


def _build_comment_yes_no_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data="STEP|COMMENT|SI"),
            InlineKeyboardButton("❌ NO", callback_data="STEP|COMMENT|NO"),
        ]
    ])


def _build_item_record(
    chat_id: int,
    step: str,
    result_code: str,
    file_id: str = "",
    media_type: str = "",
) -> dict:
    return {
        "tipo": step,
        "bucket": _step_bucket(step),
        "file_id": file_id,
        "media_type": media_type,
        "timestamp": now_str(),
        "estado": "PENDING",
        "observacion": str(get_data(chat_id, "step_comentario_actual", "") or "").strip(),
        "resultado": result_code,
        "foto_obligatoria": _result_requires_photo(result_code),
        "foto_cargada": bool(file_id),
        "opcional_tipo": str(get_data(chat_id, "opcional_tipo_texto", "") or "").strip(),
        "opcional_subopcion": str(get_data(chat_id, "opcional_subopcion", "") or "").strip(),
    }


def _append_item_record(chat_id: int, item: dict):
    evidencias = _get_evidencias(chat_id)
    evidencias.append(item)
    _save_evidencias(chat_id, evidencias)


# =========================
# HELPERS OPCIONALES
# =========================
def _build_opcional_4_opciones_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1. Opción 1", callback_data="STEP|OPCIONAL_OPT|1")],
        [InlineKeyboardButton("2. Opción 2", callback_data="STEP|OPCIONAL_OPT|2")],
        [InlineKeyboardButton("3. Opción 3", callback_data="STEP|OPCIONAL_OPT|3")],
        [InlineKeyboardButton("4. Opción 4", callback_data="STEP|OPCIONAL_OPT|4")],
        [InlineKeyboardButton("⬅️ Volver", callback_data="MENU|OPCIONAL")],
    ])


def _build_opcional_repeat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data="STEP|OPCIONAL_REPEAT|SI"),
            InlineKeyboardButton("❌ NO", callback_data="STEP|OPCIONAL_REPEAT|NO"),
        ]
    ])


def _reset_opcional_context(chat_id: int):
    set_data(chat_id, "opcional_flow_stage", "")
    set_data(chat_id, "opcional_tipo_texto", "")
    set_data(chat_id, "opcional_subopcion", "")


def _get_opcional_stage(chat_id: int) -> str:
    return str(get_data(chat_id, "opcional_flow_stage", "") or "").strip()


# =========================
# CALLBACK PRINCIPAL
# =========================
@track_time("step_callback")
async def step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data

    if not is_allowed("chat_step_callback", chat_id, limit=20, window_sec=10):
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Espera unos segundos antes de seguir."
        )
        return

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    # =========================
    # CIERRE DE MÓDULO: SI / NO
    # =========================
    if action == "CLOSE_MODULE" and len(parts) >= 4:
        decision = str(parts[2]).strip().upper()
        step = str(parts[3]).strip()
        bucket = _step_bucket(step)

        if decision == "NO":
            await _return_to_submenu(
                chat_id,
                context,
                step=step,
                prefix_text="↩️ Módulo continúa abierto."
            )
            return

        if decision == "SI":
            set_state(chat_id, "MODULE_STATUS_SELECT")
            await _edit_or_send(
                query,
                context,
                chat_id,
                (
                    f"{_module_label(bucket)}\n\n"
                    "Selecciona el estado general del módulo:"
                ),
                reply_markup=_build_module_status_keyboard(bucket, step)
            )
            return

    # =========================
    # CIERRE DE MÓDULO: ESTADO
    # =========================
    if action == "MODULE_STATUS" and len(parts) >= 5:
        bucket = str(parts[2]).strip()
        step = str(parts[3]).strip()
        status_value = str(parts[4]).strip().upper()

        _close_module(chat_id, bucket, status_value)

        duration_text = str(_get_module_data(chat_id, bucket, "duracion", "-") or "-").strip()
        await _return_to_main_menu(
            chat_id,
            context,
            prefix_text=(
                f"✅ Módulo cerrado: {_module_label(bucket)}\n"
                f"Estado: {status_value}\n"
                f"Tiempo: {duration_text}"
            )
        )
        return

    # =========================
    # RESULTADO POR ÍTEM
    # =========================
    if action == "RESULT" and len(parts) >= 4:
        step = str(parts[2]).strip()
        result_code = str(parts[3]).strip()

        _set_current_step(chat_id, step)
        set_data(chat_id, "step_resultado_actual", result_code)
        set_data(chat_id, "step_comentario_actual", "")
        set_data(chat_id, "step_photo_loaded", False)

        if result_code == RESULT_NO_APLICA:
            item = _build_item_record(
                chat_id=chat_id,
                step=step,
                result_code=result_code,
                file_id="",
                media_type="",
            )
            _append_item_record(chat_id, item)

            log_event("STEP_RESULT_NO_APLICA", chat_id=chat_id, step=step)

            if step == OPCIONAL_STEP_CODE:
                set_data(chat_id, "opcional_flow_stage", "WAIT_REPEAT")
                await _edit_or_send(
                    query,
                    context,
                    chat_id,
                    "➖ Evidencia opcional registrada como No aplica.\n\n¿Deseas cargar más evidencias opcionales?",
                    reply_markup=_build_opcional_repeat_keyboard()
                )
                return

            await _return_to_submenu(
                chat_id,
                context,
                step=step,
                prefix_text=f"➖ {step} registrado como {_result_label(result_code)}."
            )
            return

        if _result_allows_optional_photo(result_code):
            set_data(chat_id, "step_waiting_for_photo", True)
            set_data(chat_id, "step_photo_required", False)
            set_state(chat_id, "UPLOAD_EVIDENCIA")

            await _edit_or_send(
                query,
                context,
                chat_id,
                (
                    f"✅ {step}: {_result_label(result_code)}\n\n"
                    "La foto es opcional.\n"
                    "Puedes enviar una foto ahora o escribir FIN para finalizar sin foto."
                ),
                reply_markup=_build_back_menu_for_step(step)
            )
            return

        if _result_requires_photo(result_code):
            set_data(chat_id, "step_waiting_for_photo", True)
            set_data(chat_id, "step_photo_required", True)
            set_state(chat_id, "UPLOAD_EVIDENCIA")

            await _edit_or_send(
                query,
                context,
                chat_id,
                (
                    f"{'❌' if result_code == RESULT_NO_CUMPLE else '⚠️'} {step}: {_result_label(result_code)}\n\n"
                    "Debes cargar una foto obligatoriamente."
                ),
                reply_markup=_build_back_menu_for_step(step)
            )
            return

    # =========================
    # DECISIÓN DE COMENTARIO
    # =========================
    if action == "COMMENT" and len(parts) >= 3:
        decision = str(parts[2]).strip().upper()
        step = _get_current_step(chat_id)

        if decision == "SI":
            set_data(chat_id, "step_waiting_for_comment_text", True)
            set_data(chat_id, "step_waiting_for_comment_decision", False)
            set_state(chat_id, "UPLOAD_EVIDENCIA")

            await _edit_or_send(
                query,
                context,
                chat_id,
                f"✍️ Escribe el comentario para {step}."
            )
            return

        if decision == "NO":
            result_code = str(get_data(chat_id, "step_resultado_actual", "")).strip()
            file_id = str(get_data(chat_id, "step_temp_file_id", "") or "").strip()
            media_type = str(get_data(chat_id, "step_temp_media_type", "") or "").strip()

            item = _build_item_record(
                chat_id=chat_id,
                step=step,
                result_code=result_code,
                file_id=file_id,
                media_type=media_type,
            )
            _append_item_record(chat_id, item)

            set_data(chat_id, "step_temp_file_id", "")
            set_data(chat_id, "step_temp_media_type", "")

            if step == OPCIONAL_STEP_CODE:
                set_data(chat_id, "opcional_flow_stage", "WAIT_REPEAT")
                set_data(chat_id, "step_waiting_for_comment_decision", False)

                await _edit_or_send(
                    query,
                    context,
                    chat_id,
                    "✅ Evidencia opcional guardada.\n\n¿Deseas cargar más evidencias opcionales?",
                    reply_markup=_build_opcional_repeat_keyboard()
                )
                return

            await _return_to_submenu(
                chat_id,
                context,
                step=step,
                prefix_text=f"✅ {step} registrado correctamente."
            )
            return

    # =========================
    # FLUJO ESPECIAL OPCIONALES: elegir una de 4 opciones
    # =========================
    if action == "OPCIONAL_OPT" and len(parts) >= 3:
        opcion = str(parts[2]).strip()

        set_data(chat_id, "opcional_subopcion", opcion)
        set_data(chat_id, "opcional_flow_stage", "WAIT_RESULT")
        _set_current_step(chat_id, OPCIONAL_STEP_CODE)
        set_state(chat_id, "UPLOAD_EVIDENCIA")

        log_event("OPCIONAL_SUBOPCION_SELECTED", chat_id=chat_id, opcion=opcion)

        await _edit_or_send(
            query,
            context,
            chat_id,
            (
                "📸 EVIDENCIA OPCIONAL\n\n"
                f"Tipo: {get_data(chat_id, 'opcional_tipo_texto', '')}\n"
                f"Opción: {opcion}\n\n"
                "Selecciona el resultado:"
            ),
            reply_markup=_build_resultado_keyboard(OPCIONAL_STEP_CODE),
        )
        return

    # =========================
    # FLUJO ESPECIAL OPCIONALES: repetir o cerrar carga
    # =========================
    if action == "OPCIONAL_REPEAT" and len(parts) >= 3:
        decision = str(parts[2]).strip().upper()

        if decision == "SI":
            set_state(chat_id, "UPLOAD_EVIDENCIA")
            _set_current_step(chat_id, OPCIONAL_STEP_CODE)
            _reset_step_flow_context(chat_id)
            set_data(chat_id, "opcional_flow_stage", "WAIT_TYPE")
            set_data(chat_id, "opcional_tipo_texto", "")
            set_data(chat_id, "opcional_subopcion", "")

            await _edit_or_send(
                query,
                context,
                chat_id,
                "📸 EVIDENCIAS OPCIONALES\n\n¿Qué tipo de evidencia deseas cargar?\n\nEscríbelo en un mensaje."
            )
            return

        _set_current_step(chat_id, "")
        _reset_step_flow_context(chat_id)
        _reset_opcional_context(chat_id)
        set_state(chat_id, "MENU_OPCIONAL")

        await _edit_or_send(
            query,
            context,
            chat_id,
            "✅ Finalizó el flujo de evidencias opcionales.\n\nEVIDENCIAS OPCIONALES",
            reply_markup=_submenu_keyboard_for_step(OPCIONAL_STEP_CODE, chat_id)
        )
        return

    # =========================
    # FLUJO NORMAL / ENTRADA A OPCIONAL
    # =========================
    resolved_step = _resolve_step_from_callback(action)
    if not resolved_step:
        await _edit_or_send(query, context, chat_id, "⚠️ Paso de evidencia inválido.")
        return

    if resolved_step == OPCIONAL_STEP_CODE:
        _touch_module_start(chat_id, "opcionales")
        _set_current_step(chat_id, OPCIONAL_STEP_CODE)
        _reset_step_flow_context(chat_id)
        set_state(chat_id, "UPLOAD_EVIDENCIA")
        set_data(chat_id, "opcional_flow_stage", "WAIT_TYPE")
        set_data(chat_id, "opcional_tipo_texto", "")
        set_data(chat_id, "opcional_subopcion", "")

        log_event("OPCIONAL_FLOW_START", chat_id=chat_id)

        await _edit_or_send(
            query,
            context,
            chat_id,
            "📸 EVIDENCIAS OPCIONALES\n\n¿Qué tipo de evidencia deseas cargar?\n\nEscríbelo en un mensaje."
        )
        return

    bucket = _step_bucket(resolved_step)
    _touch_module_start(chat_id, bucket)
    _set_current_step(chat_id, resolved_step)
    _reset_step_flow_context(chat_id)
    set_state(chat_id, "UPLOAD_EVIDENCIA")

    log_event("STEP_SELECTED", chat_id=chat_id, step=resolved_step, bucket=bucket)

    await _edit_or_send(
        query,
        context,
        chat_id,
        f"📋 Ítem seleccionado: {resolved_step}\n\nSelecciona el resultado:",
        reply_markup=_build_resultado_keyboard(resolved_step),
    )


# =========================
# INPUT DE EVIDENCIAS
# =========================
@track_time("step_input")
async def step_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_step = _get_current_step(chat_id)

    if not current_step:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ No hay un paso de evidencia activo."
        )
        return

    if not is_allowed("chat_step_input", chat_id, limit=30, window_sec=20):
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Vas muy rápido. Espera unos segundos."
        )
        return

    # =========================
    # FLUJO ESPECIAL OPCIONALES - TIPO Y OPCIONES
    # =========================
    if current_step == OPCIONAL_STEP_CODE:
        opcional_stage = _get_opcional_stage(chat_id)

        if opcional_stage == "WAIT_TYPE":
            text = (update.message.text or "").strip()
            if not text:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Escribe el tipo de evidencia opcional."
                )
                return

            set_data(chat_id, "opcional_tipo_texto", text)
            set_data(chat_id, "opcional_flow_stage", "WAIT_OPTION")

            log_event("OPCIONAL_TIPO_SET", chat_id=chat_id, tipo=text)

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Tipo registrado: {text}\n\n"
                    "Ahora selecciona una de las 4 opciones:"
                ),
                reply_markup=_build_opcional_4_opciones_keyboard()
            )
            return

        if opcional_stage == "WAIT_OPTION":
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Selecciona una de las 4 opciones usando los botones."
            )
            return

    # =========================
    # ESPERA COMENTARIO TEXTO
    # =========================
    if bool(get_data(chat_id, "step_waiting_for_comment_text", False)):
        text = (update.message.text or "").strip()
        if not text:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Escribe un comentario válido."
            )
            return

        set_data(chat_id, "step_comentario_actual", text)
        set_data(chat_id, "step_waiting_for_comment_text", False)

        result_code = str(get_data(chat_id, "step_resultado_actual", "")).strip()
        file_id = str(get_data(chat_id, "step_temp_file_id", "") or "").strip()
        media_type = str(get_data(chat_id, "step_temp_media_type", "") or "").strip()

        item = _build_item_record(
            chat_id=chat_id,
            step=current_step,
            result_code=result_code,
            file_id=file_id,
            media_type=media_type,
        )
        _append_item_record(chat_id, item)

        set_data(chat_id, "step_temp_file_id", "")
        set_data(chat_id, "step_temp_media_type", "")

        log_event("STEP_COMMENT_SET", chat_id=chat_id, step=current_step)

        if current_step == OPCIONAL_STEP_CODE:
            set_data(chat_id, "opcional_flow_stage", "WAIT_REPEAT")
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Evidencia opcional guardada con comentario.\n\n¿Deseas cargar más evidencias opcionales?",
                reply_markup=_build_opcional_repeat_keyboard()
            )
            return

        await _return_to_submenu(
            chat_id,
            context,
            step=current_step,
            prefix_text=f"✅ {current_step} registrado con comentario."
        )
        return

    # =========================
    # ESPERA FOTO
    # =========================
    if bool(get_data(chat_id, "step_waiting_for_photo", False)):
        if update.message.text:
            text = (update.message.text or "").strip().upper()
            result_code = str(get_data(chat_id, "step_resultado_actual", "")).strip()

            if text == "FIN" and result_code == RESULT_CUMPLE and not bool(get_data(chat_id, "step_photo_required", False)):
                item = _build_item_record(
                    chat_id=chat_id,
                    step=current_step,
                    result_code=result_code,
                    file_id="",
                    media_type="",
                )
                _append_item_record(chat_id, item)

                if current_step == OPCIONAL_STEP_CODE:
                    set_data(chat_id, "opcional_flow_stage", "WAIT_REPEAT")
                    set_data(chat_id, "step_waiting_for_photo", False)

                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="✅ Evidencia opcional guardada sin foto.\n\n¿Deseas cargar más evidencias opcionales?",
                        reply_markup=_build_opcional_repeat_keyboard()
                    )
                    return

                await _return_to_submenu(
                    chat_id,
                    context,
                    step=current_step,
                    prefix_text=f"✅ {current_step} registrado como Cumple."
                )
                return

        file_id = extract_file_id(update)
        if not file_id:
            if bool(get_data(chat_id, "step_photo_required", False)):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Debes cargar una foto válida."
                )
                return

            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Envía una foto válida o escribe FIN para finalizar sin foto."
            )
            return

        media_type = "photo"
        if update.message.video:
            media_type = "video"
        elif update.message.document:
            media_type = "document"

        result_code = str(get_data(chat_id, "step_resultado_actual", "")).strip()

        set_data(chat_id, "step_temp_file_id", file_id)
        set_data(chat_id, "step_temp_media_type", media_type)
        set_data(chat_id, "step_photo_loaded", True)
        set_data(chat_id, "step_waiting_for_photo", False)

        log_media(step=current_step, file_id=file_id, chat_id=chat_id, media_type=media_type)

        if _result_requires_comment_question(result_code):
            set_data(chat_id, "step_waiting_for_comment_decision", True)

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Foto registrada para {current_step}.\n\n"
                    "¿Deseas ingresar un comentario?"
                ),
                reply_markup=_build_comment_yes_no_keyboard()
            )
            return

        item = _build_item_record(
            chat_id=chat_id,
            step=current_step,
            result_code=result_code,
            file_id=file_id,
            media_type=media_type,
        )
        _append_item_record(chat_id, item)

        set_data(chat_id, "step_temp_file_id", "")
        set_data(chat_id, "step_temp_media_type", "")

        if current_step == OPCIONAL_STEP_CODE:
            set_data(chat_id, "opcional_flow_stage", "WAIT_REPEAT")
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Evidencia opcional guardada.\n\n¿Deseas cargar más evidencias opcionales?",
                reply_markup=_build_opcional_repeat_keyboard()
            )
            return

        await _return_to_submenu(
            chat_id,
            context,
            step=current_step,
            prefix_text=f"✅ {current_step} registrado correctamente."
        )
        return

    # =========================
    # ESPERA DECISIÓN DE COMENTARIO
    # =========================
    if bool(get_data(chat_id, "step_waiting_for_comment_decision", False)):
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Responde usando los botones SI o NO."
        )
        return

    # =========================
    # TEXTO FUERA DE FLUJO
    # =========================
    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ Usa los botones del flujo actual o envía la foto solicitada."
    )


# =========================
# HELPERS DE CONSULTA
# =========================
def get_step_summary(chat_id: int, step: str) -> dict:
    evidencias = _get_evidencias(chat_id)
    items = [ev for ev in evidencias if str(ev.get("tipo")) == step]

    return {
        "step": step,
        "count": len(items),
        "items": items,
    }


def get_all_steps_summary(chat_id: int) -> dict:
    evidencias = _get_evidencias(chat_id)
    grouped = {}

    for ev in evidencias:
        step = str(ev.get("tipo", ""))
        grouped.setdefault(step, 0)
        grouped[step] += 1

    return grouped