# =========================
# services/routing_service.py
# =========================

import json
import logging
import time
from typing import Dict, Any, Optional

from config import (
    ROUTING_CACHE_TTL_SEC,
    ROUTING_JSON,
    SHEET_TAB_ROUTING,
)

from constants import VALID_TRUE
from services.google_sheets_service import get_all_records

logger = logging.getLogger("routing_service")


# =========================
# CACHE
# =========================
_ROUTING_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "routes": {},
}


# =========================
# HELPERS
# =========================
def _parse_int_chat_id(v: Any) -> Optional[int]:
    try:
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _is_truthy(v: Any) -> bool:
    return str(v).strip().upper() in VALID_TRUE


# =========================
# LOAD ROUTING
# =========================
def load_routing_cache(force: bool = False) -> Dict[str, Any]:
    now = time.time()

    if (
        not force
        and _ROUTING_CACHE["routes"]
        and (now - _ROUTING_CACHE["ts"]) < ROUTING_CACHE_TTL_SEC
    ):
        return _ROUTING_CACHE["routes"]

    routes: Dict[str, Any] = {}

    # =========================
    # 1. GOOGLE SHEETS
    # =========================
    try:
        records = get_all_records(SHEET_TAB_ROUTING)

        for r in records:
            origin = str(r.get("origin_chat_id", "")).strip()
            if not origin:
                continue

            routes[origin] = {
                "origin_chat_id": origin,
                "evidence_chat_id": str(r.get("evidence_chat_id", "")).strip(),
                "summary_chat_id": str(r.get("summary_chat_id", "")).strip(),
                "alias": str(r.get("alias", "")).strip(),
                "activo": _is_truthy(r.get("activo", "1")),
            }

        _ROUTING_CACHE["routes"] = routes
        _ROUTING_CACHE["ts"] = now

        logger.info("✅ Routing cargado desde Sheets (%s rutas)", len(routes))
        return routes

    except Exception as e:
        logger.warning("⚠️ Error leyendo ROUTING desde Sheets: %s", e)

    # =========================
    # 2. FALLBACK JSON
    # =========================
    if ROUTING_JSON:
        try:
            parsed = json.loads(ROUTING_JSON)

            for origin, v in (parsed or {}).items():
                origin_s = str(origin).strip()
                if not origin_s:
                    continue

                routes[origin_s] = {
                    "origin_chat_id": origin_s,
                    "evidence_chat_id": str(v.get("evidence", "")).strip(),
                    "summary_chat_id": str(v.get("summary", "")).strip(),
                    "alias": str(v.get("alias", "")).strip(),
                    "activo": True,
                }

            logger.info("✅ Routing cargado desde JSON (%s rutas)", len(routes))

        except Exception as e:
            logger.warning("⚠️ ROUTING_JSON inválido: %s", e)

    _ROUTING_CACHE["routes"] = routes
    _ROUTING_CACHE["ts"] = now

    return routes


# =========================
# CACHE CONTROL
# =========================
def clear_routing_cache() -> None:
    _ROUTING_CACHE["ts"] = 0.0
    _ROUTING_CACHE["routes"] = {}


# =========================
# GET ROUTES
# =========================
def get_route_for_chat(origin_chat_id: int) -> Optional[Dict[str, Any]]:
    routes = load_routing_cache()
    return routes.get(str(origin_chat_id))


def route_dest_evidence(origin_chat_id: int) -> Optional[int]:
    r = get_route_for_chat(origin_chat_id)
    if not r or not r.get("activo"):
        return None
    return _parse_int_chat_id(r.get("evidence_chat_id"))


def route_dest_summary(origin_chat_id: int) -> Optional[int]:
    r = get_route_for_chat(origin_chat_id)
    if not r or not r.get("activo"):
        return None
    return _parse_int_chat_id(r.get("summary_chat_id"))


# =========================
# DEBUG / INFO
# =========================
def get_route_snapshot_text(origin_chat_id: int) -> str:
    r = get_route_for_chat(origin_chat_id)

    if not r:
        return "📌 Este grupo no tiene routing configurado."

    return (
        "📌 RUTA ACTUAL\n\n"
        f"• origin_chat_id: {r.get('origin_chat_id','')}\n"
        f"• alias: {r.get('alias','')}\n"
        f"• evidence_chat_id: {r.get('evidence_chat_id','') or '(no vinculado)'}\n"
        f"• summary_chat_id: {r.get('summary_chat_id','') or '(no vinculado)'}\n"
        f"• activo: {'✅' if r.get('activo') else '❌'}"
    )