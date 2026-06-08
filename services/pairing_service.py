# =========================
# services/pairing_service.py
# Generación y validación de códigos de vinculación
# =========================

import logging
import secrets
import string
from typing import Dict, Any, Optional, Tuple

from config import (
    PAIRING_TTL_MINUTES,
    now_peru_dt,
    now_peru_str,
    parse_dt_peru,
)
from services.google_sheets_service import (
    get_all_records,
    append_dict,
    get_worksheet,
)
from config import SHEET_TAB_PAIRING

logger = logging.getLogger("pairing_service")


def gen_pairing_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def pairing_expires_at_str(ttl_minutes: int = PAIRING_TTL_MINUTES) -> str:
    dt = now_peru_dt()
    from datetime import timedelta
    dt = dt + timedelta(minutes=ttl_minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def is_expired(expires_at: str) -> bool:
    dt = parse_dt_peru(expires_at)
    if not dt:
        return True
    return now_peru_dt() > dt


def create_pairing_code(origin_chat_id: int, purpose: str, created_by: str = "") -> Dict[str, Any]:
    code = gen_pairing_code(8)

    row = {
        "code": code,
        "origin_chat_id": str(origin_chat_id),
        "purpose": str(purpose).strip().upper(),
        "expires_at": pairing_expires_at_str(PAIRING_TTL_MINUTES),
        "used": "0",
        "created_by": str(created_by or ""),
        "created_at": now_peru_str(),
        "used_by": "",
        "used_at": "",
    }

    append_dict(SHEET_TAB_PAIRING, row)
    logger.info("✅ Pairing creado code=%s purpose=%s origin=%s", code, purpose, origin_chat_id)
    return row


def find_pairing_code(code: str) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    records = get_all_records(SHEET_TAB_PAIRING)
    normalized = str(code).strip().upper()

    for idx, row in enumerate(records, start=2):
        if str(row.get("code", "")).strip().upper() == normalized:
            return idx, row

    return None, None


def validate_pairing_code(code: str, expected_purpose: str) -> Tuple[bool, str, Optional[int], Optional[Dict[str, Any]]]:
    row_idx, row = find_pairing_code(code)
    if not row_idx or not row:
        return False, "❌ Código no encontrado.", None, None

    row_purpose = str(row.get("purpose", "")).strip().upper()
    if row_purpose != str(expected_purpose).strip().upper():
        return False, f"❌ El código es para {row_purpose}, no para {expected_purpose}.", row_idx, row

    used_val = str(row.get("used", "")).strip().lower()
    if used_val in ("1", "true", "yes", "y"):
        return False, "❌ Código ya fue usado.", row_idx, row

    expires_at = str(row.get("expires_at", "")).strip()
    if not expires_at or is_expired(expires_at):
        return False, "❌ Código expirado. Genera uno nuevo.", row_idx, row

    origin_chat_id = str(row.get("origin_chat_id", "")).strip()
    if not origin_chat_id:
        return False, "❌ Código inválido (sin origin_chat_id).", row_idx, row

    return True, "OK", row_idx, row


def mark_pairing_code_used(row_index: int, used_by: str = "") -> None:
    ws = get_worksheet(SHEET_TAB_PAIRING)
    headers = ws.row_values(1)
    h2c = {h: i + 1 for i, h in enumerate(headers)}

    patch = {
        "used": "1",
        "used_by": str(used_by or ""),
        "used_at": now_peru_str(),
    }

    for k, v in patch.items():
        col = h2c.get(k)
        if col:
            ws.update_cell(row_index, col, v)

    logger.info("✅ Pairing marcado como usado row=%s", row_index)