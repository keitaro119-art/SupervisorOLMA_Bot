# =========================
# services/summary_service.py
# Resúmenes de supervisión
# =========================

import logging
from typing import Dict, Any, List, Optional

from config import (
    DAILY_SUMMARY_ENABLED,
    DAILY_SUMMARY_SEND_TO_ORIGIN_IF_NO_SUMMARY,
    SHEET_TAB_SUPERVISIONES_V2,
    date_peru_ymd,
)
from services.google_sheets_service import get_all_records
from services.routing_service import route_dest_summary

logger = logging.getLogger("summary_service")


# =========================
# HELPERS
# =========================
def _safe_date_from_str(s: str) -> Optional[str]:
    ss = (s or "").strip()
    if not ss:
        return None
    if len(ss) >= 10:
        return ss[:10]
    return None


def _norm_key(v: Any) -> str:
    return str(v or "").strip() or "N/D"


def _parse_duration_seconds(fecha_ini: str, fecha_fin: str) -> int:
    from config import parse_dt_peru

    dt_ini = parse_dt_peru(fecha_ini)
    dt_fin = parse_dt_peru(fecha_fin)
    if not dt_ini or not dt_fin:
        return 0

    total = int((dt_fin - dt_ini).total_seconds())
    return max(0, total)


def _format_total_duration(seconds_total: int) -> str:
    seconds_total = max(0, int(seconds_total))
    hours = seconds_total // 3600
    minutes = (seconds_total % 3600) // 60

    if hours > 0:
        if minutes > 0:
            return f"{hours} horas {minutes} min"
        return f"{hours} horas"
    return f"{minutes} min"


def _fmt_count_map(d: Dict[str, int], top: Optional[int] = None) -> str:
    items = sorted(d.items(), key=lambda x: (-x[1], x[0].lower()))
    if top is not None:
        items = items[:top]
    return "\n".join([f"• {k}: {v}" for k, v in items]) if items else "• (sin data)"


def _fmt_percent_map(d: Dict[str, int], total: int) -> str:
    items = sorted(d.items(), key=lambda x: (-x[1], x[0].lower()))
    out = []
    for k, v in items:
        pct = round((v / total) * 100) if total > 0 else 0
        out.append(f"• {k}: {v} ({pct}%)")
    return "\n".join(out) if out else "• (sin data)"


# =========================
# RESUMEN INDIVIDUAL
# =========================
def build_summary(data: Dict[str, Any]) -> str:
    """
    Resumen individual de una supervisión.
    Se deja este nombre porque final_handler.py lo importa así.
    """
    if not isinstance(data, dict):
        data = {}

    supervisor = (
        data.get("Supervisor")
        or data.get("supervisor")
        or "N/D"
    )
    tecnico = (
        data.get("Técnico")
        or data.get("Tecnico")
        or data.get("tecnico")
        or "N/D"
    )
    cuadrilla = (
        data.get("Cuadrilla")
        or data.get("cuadrilla")
        or "N/D"
    )
    empresa = (
        data.get("Empresa")
        or data.get("empresa")
        or data.get("Operador")
        or data.get("operador")
        or "N/D"
    )
    distrito = (
        data.get("Distrito")
        or data.get("distrito")
        or "N/D"
    )
    tipo_supervision = (
        data.get("Tipo_Supervision")
        or data.get("tipo_supervision")
        or "N/D"
    )
    estado_final = (
        data.get("Estado_Final")
        or data.get("estado_final")
        or "N/D"
    )
    observacion = (
        data.get("Observacion")
        or data.get("observacion")
        or "-"
    )
    fecha_creacion = (
        data.get("Fecha_Creacion")
        or data.get("fecha_creacion")
        or "N/D"
    )
    fecha_cierre = (
        data.get("Fecha_Cierre")
        or data.get("fecha_cierre")
        or "N/D"
    )

    return (
        "📋 RESUMEN DE SUPERVISIÓN\n\n"
        f"• Supervisor: {supervisor}\n"
        f"• Técnico: {tecnico}\n"
        f"• Cuadrilla: {cuadrilla}\n"
        f"• Empresa: {empresa}\n"
        f"• Distrito: {distrito}\n"
        f"• Tipo de supervisión: {tipo_supervision}\n"
        f"• Estado final: {estado_final}\n"
        f"• Observación: {observacion}\n"
        f"• Fecha creación: {fecha_creacion}\n"
        f"• Fecha cierre: {fecha_cierre}"
    )


# =========================
# DATASET DEL DÍA
# =========================
def get_completed_supervisions_for_day(day_ymd: Optional[str] = None) -> List[Dict[str, Any]]:
    if not DAILY_SUMMARY_ENABLED:
        return []

    day = day_ymd or date_peru_ymd()

    try:
        recs = get_all_records(SHEET_TAB_SUPERVISIONES_V2)
    except Exception as e:
        logger.warning("No pude leer %s: %s", SHEET_TAB_SUPERVISIONES_V2, e)
        return []

    out: List[Dict[str, Any]] = []
    for r in recs:
        fecha = _safe_date_from_str(str(r.get("Fecha_Creacion", "")).strip())
        estado = str(r.get("ESTADO", "")).strip().lower()

        if fecha == day and estado == "completado":
            out.append(r)

    return out


def group_supervisions_by_origin(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for r in records:
        origin = str(r.get("Origin_Chat_ID", "")).strip()
        if not origin:
            continue
        grouped.setdefault(origin, []).append(r)

    return grouped


# =========================
# RESUMEN DIARIO
# =========================
def build_daily_summary_text(records: List[Dict[str, Any]], day_ymd: str) -> str:
    total = len(records)

    by_estado_final: Dict[str, int] = {}
    by_operador: Dict[str, int] = {}
    by_tipo: Dict[str, int] = {}
    by_distrito: Dict[str, int] = {}
    by_tecnico: Dict[str, int] = {}

    total_duration_sec = 0
    min_inicio = None
    max_fin = None

    from config import parse_dt_peru

    for r in records:
        estado_final = _norm_key(r.get("Estado_Final"))
        operador = _norm_key(r.get("Operador") or r.get("Empresa"))
        tipo = _norm_key(r.get("Tipo_Supervision"))
        distrito = _norm_key(r.get("Distrito"))
        tecnico = _norm_key(r.get("Técnico") or r.get("Tecnico"))

        by_estado_final[estado_final] = by_estado_final.get(estado_final, 0) + 1
        by_operador[operador] = by_operador.get(operador, 0) + 1
        by_tipo[tipo] = by_tipo.get(tipo, 0) + 1
        by_distrito[distrito] = by_distrito.get(distrito, 0) + 1
        by_tecnico[tecnico] = by_tecnico.get(tecnico, 0) + 1

        dt_ini = parse_dt_peru(str(r.get("Fecha_Creacion", "")).strip())
        dt_fin = parse_dt_peru(str(r.get("Fecha_Cierre", "")).strip())

        if dt_ini:
            if min_inicio is None or dt_ini < min_inicio:
                min_inicio = dt_ini

        if dt_fin:
            if max_fin is None or dt_fin > max_fin:
                max_fin = dt_fin

        if dt_ini and dt_fin and dt_fin >= dt_ini:
            total_duration_sec += int((dt_fin - dt_ini).total_seconds())

    inicio_txt = min_inicio.strftime("%H:%M") if min_inicio else "N/D"
    fin_txt = max_fin.strftime("%H:%M") if max_fin else "N/D"
    duracion_txt = _format_total_duration(total_duration_sec)

    return (
        f"📊 CIERRE DEL DIA ({day_ymd})\n\n"
        f"Total supervisiones: {total}\n"
        f"⏱️ Duración total de supervisiones: {duracion_txt}\n\n"
        f"Estado final:\n{_fmt_percent_map(by_estado_final, total)}\n\n"
        f"Por operador:\n{_fmt_count_map(by_operador)}\n\n"
        f"Tipo Supervisión:\n{_fmt_count_map(by_tipo)}\n\n"
        f"Distritos supervisados:\n{_fmt_count_map(by_distrito)}\n\n"
        f"Técnicos supervisados:\n{_fmt_count_map(by_tecnico, top=10)}\n\n"
        f"🕒 Jornada\n"
        f"Inicio: {inicio_txt}\n"
        f"Fin: {fin_txt}"
    )


# =========================
# TARGETS
# =========================
def resolve_summary_target(origin_chat_id: int) -> Optional[int]:
    summary_dest = route_dest_summary(origin_chat_id)
    if summary_dest:
        return summary_dest

    if DAILY_SUMMARY_SEND_TO_ORIGIN_IF_NO_SUMMARY:
        return origin_chat_id

    return None