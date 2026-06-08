# =========================
# handlers/menu_handler.py
# Menú principal de supervisión
# Con control secuencial por submenú
# - No permite saltar pasos
# - Volver solo funciona si no se inició el módulo
# - Si el módulo está completo, Volver pregunta cierre del módulo
# - Bloquea reingreso a módulos ya cerrados
# - Advertencias como ventanas emergentes
# - Agrega Fotocheck en Uniformes
# - Agrega Logos en Vehículo
# =========================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.session_manager import set_state, get_state, get_data
from utils.logger import log_event


# =========================
# HELPERS DE ESTADO VISUAL
# =========================
def _get_evidencias(chat_id: int) -> list:
    evidencias = get_data(chat_id, "evidencias", [])
    if not isinstance(evidencias, list):
        return []
    return evidencias


def _step_done(chat_id: int, step_code: str) -> bool:
    evidencias = _get_evidencias(chat_id)
    for ev in evidencias:
        if str(ev.get("tipo", "")).strip() == step_code:
            return True
    return False


def _module_state_key(menu_code: str) -> str:
    return {
        "INSTALACION": "MENU_INSTALACION",
        "HERRAMIENTAS": "MENU_HERRAMIENTAS",
        "EPP": "MENU_EPP",
        "EPE": "MENU_EPE",
        "UNIFORMES": "MENU_UNIFORMES",
        "VEHICULO": "MENU_VEHICULO",
        "OPCIONAL": "MENU_OPCIONAL",
        "INFO": "MENU_INFO",
    }.get(menu_code, "MENU_SUPERVISION")


def _module_title(menu_code: str) -> str:
    return {
        "INSTALACION": "SUPERVISION DE INSTALACIÓN",
        "HERRAMIENTAS": "HERRAMIENTAS",
        "EPP": "EPP",
        "EPE": "EPE",
        "UNIFORMES": "UNIFORMES",
        "VEHICULO": "VEHÍCULO",
        "OPCIONAL": "EVIDENCIAS OPCIONALES",
        "INFO": "INFORMACIÓN DE SUPERVISIÓN",
    }.get(menu_code, "MENÚ")


def _menu_code_from_state(state: str) -> str:
    return {
        "MENU_INSTALACION": "INSTALACION",
        "MENU_HERRAMIENTAS": "HERRAMIENTAS",
        "MENU_EPP": "EPP",
        "MENU_EPE": "EPE",
        "MENU_UNIFORMES": "UNIFORMES",
        "MENU_VEHICULO": "VEHICULO",
        "MENU_OPCIONAL": "OPCIONAL",
        "MENU_INFO": "INFO",
    }.get(state, "")


def _module_closed(chat_id: int, menu_code: str) -> bool:
    key_map = {
        "INSTALACION": "instalacion",
        "HERRAMIENTAS": "herramientas",
        "EPP": "epp",
        "EPE": "epe",
        "UNIFORMES": "uniformes",
        "VEHICULO": "vehiculo",
        "OPCIONAL": "opcionales",
        "INFO": "info",
    }

    key = key_map.get(menu_code, "")
    if not key:
        return False

    estado = str(get_data(chat_id, f"mod_{key}_estado", "") or "").strip()
    return estado != ""


def _module_main_label(chat_id: int, menu_code: str, base_text: str) -> str:
    return f"✅ {base_text}" if _module_closed(chat_id, menu_code) else base_text


# =========================
# SECUENCIA DE SUBMENÚS
# =========================
INSTALACION_SEQUENCE = [
    ("1. CTO", "CTO"),
    ("2. POSTE", "POSTE"),
    ("3. RUTA", "RUTA"),
    ("4. FALSO TRAMO", "FALSO_TRAMO"),
    ("5. ANCLAJE", "ANCLAJE"),
    ("6. RESERVA DOMICILIO", "RESERVA_DOMICILIO"),
    ("7. ROSETA", "ROSETA"),
    ("8. EQUIPOS", "EQUIPOS"),
]

HERRAMIENTAS_SEQUENCE = [
    ("1. Alicate de corte", "ALICATE_CORTE"),
    ("2. Alicate de pinzas", "ALICATE_PINZAS"),
    ("3. Alicate universal", "ALICATE_UNIVERSAL"),
    ("4. Crimping Tool RJ45/RJ11", "CRIMPING_TOOL"),
    ("5. Destornillador estrella", "DESTORNILLADOR_ESTRELLA"),
    ("6. Destornillador plano", "DESTORNILLADOR_PLANO"),
    ("7. Martillo", "MARTILLO"),
    ("8. Testeador cable UTP", "TESTEADOR_UTP"),
    ("9. Taladro de percusión", "TALADRO_PERCUSION"),
    ("10. Broca cemento 30cm", "BROCA_CEMENTO_30"),
    ("11. Broca cemento 15cm", "BROCA_CEMENTO_15"),
    ("12. Broca madera 15cm", "BROCA_MADERA_15"),
    ("13. Wincha pasacables", "WINCHA_PASACABLES"),
    ("14. Extensión AC 20mts", "EXTENSION_AC_20"),
    ("15. Zunchadora", "ZUNCHADORA"),
    ("16. Portacarrete", "PORTACARRETE"),
]

EPP_SEQUENCE = [
    ("1. Casco de Seguridad", "CASCO_SEGURIDAD"),
    ("2. Barbiquejo", "BARBIQUEJO"),
    ("3. Botas de Seguridad", "BOTAS_SEGURIDAD"),
    ("4. Lentes de seguridad", "LENTES_SEGURIDAD"),
    ("5. Guantes de Badana", "GUANTES_BADANA"),
    ("6. Guantes Multiflex", "GUANTES_MULTIFLEX"),
    ("7. Guantes de tela", "GUANTES_TELA"),
    ("8. Guantes dieléctricos Clase 0", "GUANTES_DIELECTRICOS"),
    ("9. Cinturón de posicionamiento doble soga", "CINTURON_POSICIONAMIENTO"),
]

EPE_SEQUENCE = [
    ("1. Conos", "CONOS"),
    ("2. Barras retractiles", "BARRAS_RETRACTILES"),
    ("3. Escalera de Tijera de 6 pasos", "ESCALERA_TIJERA_6"),
    ("4. Escalera telescópica de 28 pasos", "ESCALERA_TELESCOPICA_28"),
    ("5. Revelador de tensión", "REVELADOR_TENSION"),
]

UNIFORMES_SEQUENCE = [
    ("1. Polo", "POLO"),
    ("2. Chaleco", "CHALECO"),
    ("3. Pantalon", "PANTALON"),
    ("4. Fotocheck", "FOTOCHECK"),
]

VEHICULO_SEQUENCE = [
    ("1. Extintor", "EXTINTOR"),
    ("2. Botiquin", "BOTIQUIN"),
    ("3. Licencia de conducir", "LICENCIA_CONDUCIR"),
    ("4. SOAT", "SOAT"),
    ("5. Revision Tecnica", "REVISION_TECNICA"),
    ("6. Tarjeta de propiedad", "TARJETA_PROPIEDAD"),
    ("7. Parrilla portaescaleras", "PARRILLA_PORTAESCALERAS"),
    ("8. Tacos de seguridad", "TACOS_SEGURIDAD"),
    ("9. Logos", "LOGOS"),
]

OPCIONAL_SEQUENCE = [
    ("1. Cargar evidencia opcional", "OPCIONAL_GENERAL"),
]

INFO_SEQUENCE = [
    ("1. Metraje drop externo", "INFO_DROP_EXT"),
    ("2. Metraje drop interno", "INFO_DROP_INT"),
    ("3. Cantidad de postes usados", "INFO_POSTES"),
    ("4. Cantidad de falsos tramos usados", "INFO_FALSOS"),
    ("5. Cantidad aprox. de templadores usados", "INFO_TEMPLADORES"),
    ("6. Captura de recorrido", "INFO_RECORRIDO"),
    ("7. Información en Acta", "INFO_VALIDACION_ACTA"),
]


# =========================
# HELPERS DE COMPLETITUD
# =========================
def _info_step_done(chat_id: int, step_code: str) -> bool:
    if step_code == "INFO_DROP_EXT":
        drop_ext = get_data(chat_id, "info_drop_ext", {})
        metraje = str(get_data(chat_id, "info_drop_ext_metraje", "") or "").strip()
        return bool(drop_ext) and metraje != ""

    if step_code == "INFO_DROP_INT":
        return str(get_data(chat_id, "info_drop_int", "") or "").strip() != ""

    if step_code == "INFO_POSTES":
        return str(get_data(chat_id, "info_postes", "") or "").strip() != ""

    if step_code == "INFO_FALSOS":
        return str(get_data(chat_id, "info_falsos", "") or "").strip() != ""

    if step_code == "INFO_TEMPLADORES":
        return str(get_data(chat_id, "info_templadores", "") or "").strip() != ""

    if step_code == "INFO_RECORRIDO":
        return str(get_data(chat_id, "info_recorrido_file_id", "") or "").strip() != ""

    if step_code == "INFO_VALIDACION_ACTA":
        return str(get_data(chat_id, "info_validacion_acta", "") or "").strip() != ""

    return False


def _sequence_done(chat_id: int, sequence: list[tuple[str, str]], is_info: bool = False) -> list[bool]:
    out = []
    for _, code in sequence:
        done = _info_step_done(chat_id, code) if is_info else _step_done(chat_id, code)
        out.append(done)
    return out


def _module_started(chat_id: int, sequence: list[tuple[str, str]], is_info: bool = False) -> bool:
    return any(_sequence_done(chat_id, sequence, is_info=is_info))


def _module_completed(chat_id: int, sequence: list[tuple[str, str]], is_info: bool = False) -> bool:
    done_list = _sequence_done(chat_id, sequence, is_info=is_info)
    return bool(done_list) and all(done_list)


def _item_allowed(done_list: list[bool], idx: int) -> bool:
    if idx == 0:
        return True
    return all(done_list[:idx])


def _button_for_step(
    chat_id: int,
    label: str,
    code: str,
    allowed: bool,
    done: bool,
    is_info: bool = False,
):
    shown_label = f"🟢 {label}" if done else label

    if allowed:
        callback = f"INFO|{code.split('INFO_', 1)[1]}" if is_info else f"STEP|{code}"
        return InlineKeyboardButton(shown_label, callback_data=callback)

    return InlineKeyboardButton(f"🔒 {label}", callback_data="MENU|LOCKED")


def _build_grid_buttons(
    chat_id: int,
    sequence: list[tuple[str, str]],
    row_size: int = 2,
    is_info: bool = False,
):
    done_list = _sequence_done(chat_id, sequence, is_info=is_info)
    rows = []
    current_row = []

    for idx, (label, code) in enumerate(sequence):
        allowed = _item_allowed(done_list, idx)
        done = done_list[idx]
        current_row.append(
            _button_for_step(
                chat_id,
                label,
                code,
                allowed,
                done,
                is_info=is_info,
            )
        )

        if len(current_row) >= row_size:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    return rows


def _build_close_module_keyboard(menu_code: str, last_step_code: str) -> InlineKeyboardMarkup:
    if menu_code == "INFO":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ CORRECTO", callback_data="INFO|MODULE_STATUS|CORRECTO"),
                InlineKeyboardButton("⚠️ OBSERVADO", callback_data="INFO|MODULE_STATUS|OBSERVADO"),
            ]
        ])

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ SI", callback_data=f"STEP|CLOSE_MODULE|SI|{last_step_code}"),
            InlineKeyboardButton("❌ NO", callback_data=f"STEP|CLOSE_MODULE|NO|{last_step_code}"),
        ]
    ])


def _module_sequence(menu_code: str):
    return {
        "INSTALACION": INSTALACION_SEQUENCE,
        "HERRAMIENTAS": HERRAMIENTAS_SEQUENCE,
        "EPP": EPP_SEQUENCE,
        "EPE": EPE_SEQUENCE,
        "UNIFORMES": UNIFORMES_SEQUENCE,
        "VEHICULO": VEHICULO_SEQUENCE,
        "OPCIONAL": OPCIONAL_SEQUENCE,
        "INFO": INFO_SEQUENCE,
    }.get(menu_code, [])


def _is_info_module(menu_code: str) -> bool:
    return menu_code == "INFO"


def _module_last_step(menu_code: str) -> str:
    seq = _module_sequence(menu_code)
    return seq[-1][1] if seq else ""


# =========================
# KEYBOARDS
# =========================
def build_menu_principal(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_module_main_label(chat_id, "INSTALACION", "🏗️ Supervision de Instalación"), callback_data="MENU|INSTALACION")],
        [InlineKeyboardButton(_module_main_label(chat_id, "HERRAMIENTAS", "🧰 Herramientas"), callback_data="MENU|HERRAMIENTAS")],
        [InlineKeyboardButton(_module_main_label(chat_id, "EPP", "🦺 EPP"), callback_data="MENU|EPP")],
        [InlineKeyboardButton(_module_main_label(chat_id, "EPE", "🚧 EPE"), callback_data="MENU|EPE")],
        [InlineKeyboardButton(_module_main_label(chat_id, "UNIFORMES", "👕 Uniformes"), callback_data="MENU|UNIFORMES")],
        [InlineKeyboardButton(_module_main_label(chat_id, "VEHICULO", "🚗 Vehículo"), callback_data="MENU|VEHICULO")],
        [InlineKeyboardButton(_module_main_label(chat_id, "OPCIONAL", "📸 Evidencias opcionales"), callback_data="MENU|OPCIONAL")],
        [InlineKeyboardButton(_module_main_label(chat_id, "INFO", "📊 Información de Supervision"), callback_data="MENU|INFO")],
        [InlineKeyboardButton("✅ Finalizar Supervisión", callback_data="FINAL|ASK")],
    ])


def build_menu_instalacion(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, INSTALACION_SEQUENCE, row_size=2, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_herramientas(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, HERRAMIENTAS_SEQUENCE, row_size=3, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_epp(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, EPP_SEQUENCE, row_size=2, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_epe(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, EPE_SEQUENCE, row_size=1, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_uniformes(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, UNIFORMES_SEQUENCE, row_size=1, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_vehiculo(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, VEHICULO_SEQUENCE, row_size=2, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_opcional(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, OPCIONAL_SEQUENCE, row_size=1, is_info=False)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


def build_menu_info(chat_id: int) -> InlineKeyboardMarkup:
    rows = _build_grid_buttons(chat_id, INFO_SEQUENCE, row_size=1, is_info=True)
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data="MENU|BACK")])
    return InlineKeyboardMarkup(rows)


# =========================
# HELPERS
# =========================
def _menu_title(chat_id: int) -> str:
    current_step = int(get_data(chat_id, "current_step_number", 5))
    return f"PASO {current_step} - MENÚ DE SUPERVISIÓN"


async def _edit_or_send_menu(query, context, chat_id: int, text: str, reply_markup):
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


async def _open_module(query, context, chat_id: int, menu_code: str):
    if _module_closed(chat_id, menu_code):
        await query.answer(
            f"⚠️ El módulo {_module_title(menu_code)} ya fue cerrado.",
            show_alert=True
        )
        set_state(chat_id, "MENU_SUPERVISION")
        return

    set_state(chat_id, _module_state_key(menu_code))

    builders = {
        "INSTALACION": build_menu_instalacion,
        "HERRAMIENTAS": build_menu_herramientas,
        "EPP": build_menu_epp,
        "EPE": build_menu_epe,
        "UNIFORMES": build_menu_uniformes,
        "VEHICULO": build_menu_vehiculo,
        "OPCIONAL": build_menu_opcional,
        "INFO": build_menu_info,
    }

    await _edit_or_send_menu(
        query,
        context,
        chat_id,
        _module_title(menu_code),
        builders[menu_code](chat_id)
    )


async def _handle_back_from_submenu(query, context, chat_id: int, current_state: str):
    menu_code = _menu_code_from_state(current_state)

    if not menu_code:
        set_state(chat_id, "MENU_SUPERVISION")
        await _edit_or_send_menu(
            query,
            context,
            chat_id,
            _menu_title(chat_id),
            build_menu_principal(chat_id)
        )
        return

    sequence = _module_sequence(menu_code)
    is_info = _is_info_module(menu_code)
    started = _module_started(chat_id, sequence, is_info=is_info)
    completed = _module_completed(chat_id, sequence, is_info=is_info)

    if not started:
        set_state(chat_id, "MENU_SUPERVISION")
        await _edit_or_send_menu(
            query,
            context,
            chat_id,
            _menu_title(chat_id),
            build_menu_principal(chat_id)
        )
        return

    if started and not completed:
        await query.answer(
            f"⚠️ Debes completar todo el módulo {_module_title(menu_code)} antes de salir.",
            show_alert=True
        )
        return

    last_step = _module_last_step(menu_code)

    if menu_code == "INFO":
        await _edit_or_send_menu(
            query,
            context,
            chat_id,
            f"¿Qué estado tendrá el módulo {_module_title(menu_code)}?",
            _build_close_module_keyboard(menu_code, last_step)
        )
        return

    await _edit_or_send_menu(
        query,
        context,
        chat_id,
        f"¿Desea cerrar la supervisión del módulo {_module_title(menu_code)}?",
        _build_close_module_keyboard(menu_code, last_step)
    )


# =========================
# CALLBACK PRINCIPAL
# =========================
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    chat_id = update.effective_chat.id
    data = query.data or ""
    current_state = get_state(chat_id)

    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    log_event("MENU_ACTION", chat_id=chat_id, action=action, state=current_state)

    current_step = str(get_data(chat_id, "current_step", "") or "").strip()

    if current_step and current_state == "UPLOAD_EVIDENCIA":
        await query.answer(
            "⚠️ Primero debes finalizar el paso actual antes de volver o cambiar de módulo.",
            show_alert=True
        )
        return

    if action == "LOCKED":
        await query.answer(
            "⚠️ Debes completar el paso anterior primero.",
            show_alert=True
        )
        return

    if action == "BACK":
        await _handle_back_from_submenu(query, context, chat_id, current_state)
        return

    if action == "INSTALACION":
        await query.answer()
        await _open_module(query, context, chat_id, "INSTALACION")
        return

    if action == "HERRAMIENTAS":
        await query.answer()
        await _open_module(query, context, chat_id, "HERRAMIENTAS")
        return

    if action == "EPP":
        await query.answer()
        await _open_module(query, context, chat_id, "EPP")
        return

    if action == "EPE":
        await query.answer()
        await _open_module(query, context, chat_id, "EPE")
        return

    if action == "UNIFORMES":
        await query.answer()
        await _open_module(query, context, chat_id, "UNIFORMES")
        return

    if action == "VEHICULO":
        await query.answer()
        await _open_module(query, context, chat_id, "VEHICULO")
        return

    if action == "OPCIONAL":
        await query.answer()
        await _open_module(query, context, chat_id, "OPCIONAL")
        return

    if action == "INFO":
        await query.answer()
        await _open_module(query, context, chat_id, "INFO")
        return

    await query.answer()

    try:
        await query.edit_message_text("⚠️ Opción no válida en menú.")
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Opción no válida en menú."
        )