# =========================
# services/almuerzo_service.py
# Gestión de almuerzos (inicio / fin / validación)
# =========================

import logging
from typing import Optional, Dict, Any

from config import now_peru_str, parse_dt_peru, SHEET_TAB_ALMUERZOS
from constants import ALM_ESTADO_ACTIVO, ALM_ESTADO_CERRADO
from services.google_sheets_service import get_all_records, append_dict, get_worksheet

logger = logging.getLogger("almuerzo_service")


# =========================
# HELPERS
# =========================
def _format_hora(dt_text: str) -> str:
    dt = parse_dt_peru(dt_text)
    if not dt:
        return ""
    return dt.strftime("%H:%M")


def _find_active_almuerzo(chat_id: str) -> Optional[Dict[str, Any]]:
    records = get_all_records(SHEET_TAB_ALMUERZOS)

    for r in reversed(records):
        if str(r.get("Chat_ID")) == str(chat_id) and str(r.get("Estado")) == ALM_ESTADO_ACTIVO:
            return r
    return None


def _find_active_row_index(chat_id: str) -> Optional[int]:
    ws = get_worksheet(SHEET_TAB_ALMUERZOS)
    records = ws.get_all_records()

    for idx, r in enumerate(records, start=2):
        if str(r.get("Chat_ID")) == str(chat_id) and str(r.get("Estado")) == ALM_ESTADO_ACTIVO:
            return idx
    return None


def _calc_duracion(inicio: str, fin: str) -> tuple[int, str]:
    dt_ini = parse_dt_peru(inicio)
    dt_fin = parse_dt_peru(fin)

    if not dt_ini or not dt_fin:
        return 0, "N/D"

    total_sec = max(0, int((dt_fin - dt_ini).total_seconds()))

    minutos_total = total_sec // 60
    segundos = total_sec % 60

    horas = minutos_total // 60
    minutos = minutos_total % 60

    if horas > 0:
        txt = f"{horas} h {minutos} min {segundos} seg"
    elif minutos_total > 0:
        txt = f"{minutos_total} min {segundos} seg"
    else:
        txt = f"{segundos} seg"

    return minutos_total, txt


# =========================
# INICIO ALMUERZO
# =========================
def iniciar_almuerzo(data: Dict[str, Any]) -> Dict[str, Any]:
    chat_id = str(data.get("Chat_ID"))

    activo = _find_active_almuerzo(chat_id)
    if activo:
        inicio = str(activo.get("Hora_Inicio", "") or "")
        return {
            "ok": False,
            "msg": (
                "⛔️ Ya tienes un almuerzo en curso.\n"
                f"🕒 Inicio de almuerzo: {_format_hora(inicio)}"
            ),
            "hora_inicio": _format_hora(inicio),
            "hora_inicio_full": inicio,
        }

    ahora = now_peru_str()

    row = {
        "ID_Almuerzo": "",
        "Fecha": ahora.split(" ")[0],
        "Supervisor": data.get("Supervisor", ""),
        "Supervisor_ID": data.get("Supervisor_ID", ""),
        "Chat_ID": chat_id,
        "Hora_Inicio": ahora,
        "Hora_Fin": "",
        "Duracion_Minutos": "",
        "Duracion_Texto": "",
        "Estado": ALM_ESTADO_ACTIVO,
        "Creado_En": ahora,
        "Cerrado_En": "",
    }

    append_dict(SHEET_TAB_ALMUERZOS, row)

    hora_inicio = _format_hora(ahora)

    logger.info("🍽️ Almuerzo iniciado chat_id=%s hora=%s", chat_id, hora_inicio)

    return {
        "ok": True,
        "msg": (
            "🍽️ Inicio de almuerzo\n"
            f"🕒 Hora de inicio: {hora_inicio}"
        ),
        "hora_inicio": hora_inicio,
        "hora_inicio_full": ahora,
    }


# =========================
# FIN ALMUERZO
# =========================
def finalizar_almuerzo(chat_id: str) -> Dict[str, Any]:
    row_index = _find_active_row_index(chat_id)

    if not row_index:
        return {
            "ok": False,
            "msg": "⚠️ No tienes almuerzo activo.",
        }

    ws = get_worksheet(SHEET_TAB_ALMUERZOS)
    headers = ws.row_values(1)
    h2c = {h: i + 1 for i, h in enumerate(headers)}

    inicio_col = h2c.get("Hora_Inicio")
    inicio = ws.cell(row_index, inicio_col).value if inicio_col else ""

    fin = now_peru_str()

    minutos, duracion_texto = _calc_duracion(inicio, fin)

    updates = {
        "Hora_Fin": fin,
        "Duracion_Minutos": minutos,
        "Duracion_Texto": duracion_texto,
        "Estado": ALM_ESTADO_CERRADO,
        "Cerrado_En": fin,
    }

    for k, v in updates.items():
        col = h2c.get(k)
        if col:
            ws.update_cell(row_index, col, v)

    hora_inicio = _format_hora(inicio)
    hora_fin = _format_hora(fin)

    logger.info("🍽️ Almuerzo finalizado chat_id=%s duración=%s", chat_id, duracion_texto)

    return {
        "ok": True,
        "msg": (
            "🍽️ Fin de almuerzo\n"
            f"🕒 Hora de inicio: {hora_inicio}\n"
            f"🕒 Hora de fin: {hora_fin}\n"
            f"⏱️ Tiempo total: {duracion_texto}"
        ),
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "duracion_texto": duracion_texto,
        "hora_inicio_full": inicio,
        "hora_fin_full": fin,
    }


# =========================
# VALIDAR ESTADO
# =========================
def tiene_almuerzo_activo(chat_id: str) -> bool:
    return _find_active_almuerzo(chat_id) is not None


def obtener_almuerzo_activo(chat_id: str) -> Optional[Dict[str, Any]]:
    activo = _find_active_almuerzo(chat_id)
    if not activo:
        return None

    inicio = str(activo.get("Hora_Inicio", "") or "")

    activo["Hora_Inicio_Formato"] = _format_hora(inicio)
    return activo