# =========================
# core/session_manager.py
# Gestor único de sesiones en memoria
# =========================

import threading
from typing import Any, Dict

from config import now_peru_dt, SESSION_TTL_SECONDS
from utils.logger import log_event

# =========================
# STORAGE
# =========================
_sessions: Dict[int, Dict[str, Any]] = {}
_lock = threading.Lock()


# =========================
# HELPERS
# =========================
def _new_session(chat_id: int) -> Dict[str, Any]:
    now = now_peru_dt()
    return {
        "chat_id": int(chat_id),
        "state": "START",
        "data": {},
        "created_at": now,
        "updated_at": now,
    }


def _is_expired(session: Dict[str, Any]) -> bool:
    updated_at = session.get("updated_at", now_peru_dt())
    return (now_peru_dt() - updated_at).total_seconds() > SESSION_TTL_SECONDS


def _touch(session: Dict[str, Any]) -> None:
    session["updated_at"] = now_peru_dt()


def _remove_keys(data: Dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        data.pop(key, None)


def _cleanup_supervision_keys(data: Dict[str, Any], keep_partial_data: bool = False) -> None:
    """
    Limpia claves relacionadas al flujo de supervisión.
    keep_partial_data=False  -> limpia todo lo relacionado a la supervisión
    keep_partial_data=True   -> limpia flags/estado operativo pero conserva data cargada
    """
    flow_keys = [
        # Flujo general
        "current_step_number",
        "menu_actual",
        "awaiting_input_for",
        "last_menu",
        "flow_started_at",

        # Supervisor / empresa / cuadrilla / distrito
        "supervisor",
        "empresa",
        "cuadrilla",
        "distrito",

        # Técnicos / pedido / tipo
        "codigo_pedido",
        "tipo_supervision",
        "tecnico_slot",
        "tecnicos_cache",
        "tecnico_1_nombre",
        "tecnico_1_empresa",
        "tecnico_2_nombre",
        "tecnico_2_empresa",
        "tecnico_3_nombre",
        "tecnico_3_empresa",

        # Ubicación / selfie
        "ubicacion_lat",
        "ubicacion_lon",
        "ubicacion_url",
        "ubicacion_texto",
        "selfie_fachada_file_id",
        "selfie_fachada_file_unique_id",

        # Evidencias / pasos / media
        "evidencias",
        "current_step_code",
        "current_step_name",
        "current_step_tipo",
        "current_step_resultado",
        "current_step_observacion",
        "current_media_group",
        "current_media_group_id",
        "current_media_items",
        "pending_media",
        "pending_step",
        "pending_resultado",
        "pending_observacion",

        # Info adicional
        "info_drop_ext",
        "info_drop_ext_metraje",
        "info_drop_int",
        "info_postes",
        "info_falsos",
        "info_templadores",
        "info_recorrido_file_id",
        "info_recorrido_file_unique_id",
        "info_validacion_acta",

        # Confirmaciones
        "final_confirm_pending",
    ]

    runtime_only_keys = [
        # Flags operativos / bloqueo
        "supervision_activa",
        "supervision_bloqueada",
        "grupo_bloqueado",
        "locked_by",
        "lock_reason",
        "lock_at",
        "force_close_requested",
        "stop_requested",
        "liberado_por_admin",
        "closed_forced",
        "closed_forced_at",
        "closed_forced_by",
    ]

    if keep_partial_data:
        _remove_keys(data, runtime_only_keys)
    else:
        _remove_keys(data, flow_keys + runtime_only_keys)


# =========================
# CORE
# =========================
def init_sessions() -> None:
    global _sessions
    with _lock:
        _sessions = {}
    log_event("SESSIONS_INIT")


def create_session(chat_id: int) -> Dict[str, Any]:
    with _lock:
        session = _new_session(chat_id)
        _sessions[int(chat_id)] = session

    log_event("SESSION_CREATE", chat_id=chat_id)
    return session


def get_session(chat_id: int) -> Dict[str, Any]:
    cid = int(chat_id)

    with _lock:
        session = _sessions.get(cid)

        if session is None:
            session = _new_session(cid)
            _sessions[cid] = session
            log_event("SESSION_CREATE_AUTO", chat_id=cid)
            return session

        if _is_expired(session):
            session = _new_session(cid)
            _sessions[cid] = session
            log_event("SESSION_EXPIRED_RESET", chat_id=cid)
            return session

        _touch(session)
        return session


def clear_session(chat_id: int) -> None:
    cid = int(chat_id)
    with _lock:
        _sessions.pop(cid, None)

    log_event("SESSION_CLEAR", chat_id=cid)


def reset_session(chat_id: int) -> Dict[str, Any]:
    cid = int(chat_id)
    with _lock:
        session = _new_session(cid)
        _sessions[cid] = session

    log_event("SESSION_RESET", chat_id=cid)
    return session


# =========================
# STATE
# =========================
def set_state(chat_id: int, state: str) -> None:
    session = get_session(chat_id)
    with _lock:
        session["state"] = state
        _touch(session)

    log_event("STATE_SET", chat_id=chat_id, state=state)


def get_state(chat_id: int) -> str:
    session = get_session(chat_id)
    return str(session.get("state", "START"))


# =========================
# DATA
# =========================
def set_data(chat_id: int, key: str, value: Any) -> None:
    session = get_session(chat_id)
    with _lock:
        session["data"][key] = value
        _touch(session)

    log_event("SESSION_DATA_SET", chat_id=chat_id, key=key)


def get_data(chat_id: int, key: str, default=None) -> Any:
    session = get_session(chat_id)
    return session.get("data", {}).get(key, default)


def get_all_data(chat_id: int) -> Dict[str, Any]:
    session = get_session(chat_id)
    return dict(session.get("data", {}))


def update_data(chat_id: int, patch: Dict[str, Any]) -> None:
    session = get_session(chat_id)
    with _lock:
        session["data"].update(patch)
        _touch(session)

    log_event("SESSION_DATA_UPDATE", chat_id=chat_id, keys=",".join(patch.keys()))


def clear_data(chat_id: int) -> None:
    session = get_session(chat_id)
    with _lock:
        session["data"] = {}
        _touch(session)

    log_event("SESSION_DATA_CLEAR", chat_id=chat_id)


# =========================
# MEDIA / LIST HELPERS
# =========================
def append_to_list(chat_id: int, key: str, item: Any) -> None:
    session = get_session(chat_id)
    with _lock:
        if key not in session["data"] or not isinstance(session["data"][key], list):
            session["data"][key] = []
        session["data"][key].append(item)
        _touch(session)

    log_event("SESSION_LIST_APPEND", chat_id=chat_id, key=key)


# =========================
# HELPERS DE SUPERVISIÓN
# =========================
def has_active_supervision(chat_id: int) -> bool:
    """
    Detecta si hay una supervisión en curso en base a flags o data relevante.
    """
    session = get_session(chat_id)
    data = session.get("data", {})

    if bool(data.get("supervision_activa")):
        return True

    state = str(session.get("state", "START")).strip().upper()
    if state not in ("START", "", "DONE", "CLOSED", "FINALIZED"):
        if any([
            data.get("supervisor"),
            data.get("empresa"),
            data.get("codigo_pedido"),
            data.get("tecnico_1_nombre"),
            data.get("evidencias"),
        ]):
            return True

    return False


def mark_supervision_active(chat_id: int, active: bool = True) -> None:
    session = get_session(chat_id)
    with _lock:
        session["data"]["supervision_activa"] = bool(active)
        _touch(session)

    log_event("SUPERVISION_ACTIVE_SET", chat_id=chat_id, active=bool(active))


def set_group_lock(chat_id: int, locked: bool = True, by_user_id: int | None = None, reason: str = "") -> None:
    session = get_session(chat_id)
    with _lock:
        session["data"]["grupo_bloqueado"] = bool(locked)
        session["data"]["supervision_bloqueada"] = bool(locked)

        if locked:
            session["data"]["locked_by"] = by_user_id
            session["data"]["lock_reason"] = str(reason or "").strip()
            session["data"]["lock_at"] = now_peru_dt().isoformat()
        else:
            _remove_keys(session["data"], ["locked_by", "lock_reason", "lock_at"])

        _touch(session)

    log_event(
        "GROUP_LOCK_SET",
        chat_id=chat_id,
        locked=bool(locked),
        by_user_id=by_user_id,
        reason=str(reason or "").strip(),
    )


def is_group_locked(chat_id: int) -> bool:
    data = get_all_data(chat_id)
    return bool(data.get("grupo_bloqueado") or data.get("supervision_bloqueada"))


def stop_supervision(chat_id: int) -> Dict[str, Any]:
    """
    /stop
    Cancela la supervisión del grupo/chat actual y limpia toda la data del flujo.
    """
    session = get_session(chat_id)

    with _lock:
        _cleanup_supervision_keys(session["data"], keep_partial_data=False)
        session["state"] = "START"
        _touch(session)

    log_event("SUPERVISION_STOP", chat_id=chat_id)
    return dict(session)


def release_group(chat_id: int) -> Dict[str, Any]:
    """
    /liberar
    Libera el grupo quitando bloqueos y flags operativos,
    pero conserva la data ya registrada.
    """
    session = get_session(chat_id)

    with _lock:
        _cleanup_supervision_keys(session["data"], keep_partial_data=True)
        if session["state"] == "CONFIRM_FINAL":
            session["state"] = "MENU_SUPERVISION"
        _touch(session)

    log_event("GROUP_RELEASE", chat_id=chat_id)
    return dict(session)


def force_close_supervision(chat_id: int, closed_by_user_id: int | None = None) -> Dict[str, Any]:
    """
    /forzar_cierre
    Marca cierre forzado, libera el grupo y deja la sesión lista para nuevo inicio.
    Conserva trazas mínimas de cierre hasta que luego se limpie por flujo normal.
    """
    session = get_session(chat_id)

    with _lock:
        session["data"]["closed_forced"] = True
        session["data"]["closed_forced_at"] = now_peru_dt().isoformat()
        session["data"]["closed_forced_by"] = closed_by_user_id
        session["data"]["supervision_activa"] = False
        session["data"]["grupo_bloqueado"] = False
        session["data"]["supervision_bloqueada"] = False
        session["state"] = "START"
        _touch(session)

    log_event(
        "SUPERVISION_FORCE_CLOSE",
        chat_id=chat_id,
        closed_by_user_id=closed_by_user_id,
    )
    return dict(session)


def reset_supervision_runtime(chat_id: int) -> Dict[str, Any]:
    """
    Helper adicional:
    limpia flags de ejecución y devuelve al menú si aplica,
    sin borrar todo el contenido.
    """
    session = get_session(chat_id)

    with _lock:
        _cleanup_supervision_keys(session["data"], keep_partial_data=True)
        if session["state"] not in ("START", "MENU_SUPERVISION"):
            session["state"] = "MENU_SUPERVISION"
        _touch(session)

    log_event("SUPERVISION_RUNTIME_RESET", chat_id=chat_id)
    return dict(session)


# =========================
# MONITOREO
# =========================
def get_active_sessions() -> Dict[int, Dict[str, Any]]:
    with _lock:
        out = {}
        for chat_id, session in list(_sessions.items()):
            if _is_expired(session):
                continue
            out[chat_id] = session
        return out


def cleanup_sessions() -> int:
    removed = 0
    with _lock:
        expired = [chat_id for chat_id, s in _sessions.items() if _is_expired(s)]
        for chat_id in expired:
            _sessions.pop(chat_id, None)
            removed += 1

    if removed:
        log_event("SESSION_CLEANUP", removed=removed)

    return removed