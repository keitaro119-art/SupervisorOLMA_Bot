# =========================
# services/google_sheets_service.py
# Integración definitiva con Google Sheets + descarga desde Google Drive
# =========================

import io
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import (
    SHEET_ID,
    GOOGLE_CREDS_JSON,
    GOOGLE_CREDS_JSON_TEXT,
    SHEET_TAB_PLANTILLAS,
    SHEET_TAB_SUPERVISIONES_V2,
    SHEET_TAB_SUPERVISORES,
    SHEET_TAB_TECNICOS_TUFIBRA,
    SHEET_TAB_INFO_TECNICOS,
    SHEET_TAB_SCTR,
    SHEET_TAB_CUADRILLAS_WIN,
    SHEET_TAB_DISTRITOS,
    SHEET_TAB_ROUTING,
    SHEET_TAB_PAIRING,
    SHEET_TAB_ALMUERZOS,
    now_peru_str,
    gs_ready,
    load_google_creds_dict,
)

logger = logging.getLogger("google_sheets_service")

# =========================
# CACHE INTERNO
# =========================
_GS_CLIENT: Optional[gspread.Client] = None
_GS_SHEET = None
_DRIVE_SERVICE = None
_HEADERS_CACHE: Dict[str, List[str]] = {}


# =========================
# CREDENCIALES BASE
# =========================
def get_google_credentials() -> Credentials:
    if not gs_ready():
        raise RuntimeError("Google Sheets no está configurado correctamente.")

    creds_dict = load_google_creds_dict()
    return Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )


# =========================
# CONEXIÓN SHEETS
# =========================
def get_client() -> gspread.Client:
    global _GS_CLIENT

    if _GS_CLIENT is not None:
        return _GS_CLIENT

    creds = get_google_credentials()
    _GS_CLIENT = gspread.authorize(creds)
    logger.info("✅ Cliente Google Sheets autenticado")
    return _GS_CLIENT


def get_sheet():
    global _GS_SHEET

    if _GS_SHEET is not None:
        return _GS_SHEET

    client = get_client()
    _GS_SHEET = client.open_by_key(SHEET_ID)
    logger.info("✅ Spreadsheet conectado")
    return _GS_SHEET


def get_worksheet(tab_name: str):
    return get_sheet().worksheet(tab_name)


# =========================
# CONEXIÓN DRIVE
# =========================
def get_drive_service():
    global _DRIVE_SERVICE

    if _DRIVE_SERVICE is not None:
        return _DRIVE_SERVICE

    creds = get_google_credentials()
    _DRIVE_SERVICE = build("drive", "v3", credentials=creds, cache_discovery=False)
    logger.info("✅ Google Drive service conectado")
    return _DRIVE_SERVICE


def clear_sheet_cache() -> None:
    global _GS_CLIENT, _GS_SHEET, _DRIVE_SERVICE
    _GS_CLIENT = None
    _GS_SHEET = None
    _DRIVE_SERVICE = None
    _HEADERS_CACHE.clear()


# =========================
# HEADERS
# =========================
def get_headers(tab_name: str) -> List[str]:
    if tab_name in _HEADERS_CACHE:
        return _HEADERS_CACHE[tab_name]

    ws = get_worksheet(tab_name)
    headers = ws.row_values(1)
    headers = [str(h).strip() for h in headers if str(h).strip()]
    _HEADERS_CACHE[tab_name] = headers
    return headers


# =========================
# LECTURA
# =========================
def get_all_values(tab_name: str) -> List[List[str]]:
    ws = get_worksheet(tab_name)
    return ws.get_all_values()


def get_all_records(tab_name: str) -> List[Dict[str, Any]]:
    ws = get_worksheet(tab_name)
    headers = get_headers(tab_name)
    values = ws.get_all_values()

    if not values or len(values) < 2:
        return []

    out: List[Dict[str, Any]] = []
    for r in values[1:]:
        rec: Dict[str, Any] = {}
        for i, h in enumerate(headers):
            rec[h] = r[i] if i < len(r) else ""
        out.append(rec)

    return out


# =========================
# ESCRITURA
# =========================
def append_row(tab_name: str, row: List[Any]) -> None:
    ws = get_worksheet(tab_name)
    ws.append_row(
        ["" if v is None else str(v) for v in row],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )


def append_dict(tab_name: str, data: Dict[str, Any]) -> None:
    headers = get_headers(tab_name)
    row = []

    for h in headers:
        v = data.get(h, "")
        row.append("" if v is None else str(v))

    append_row(tab_name, row)


def batch_append_dicts(tab_name: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    headers = get_headers(tab_name)
    values: List[List[str]] = []

    for data in rows:
        row = []
        for h in headers:
            v = data.get(h, "")
            row.append("" if v is None else str(v))
        values.append(row)

    ws = get_worksheet(tab_name)
    ws.append_rows(
        values,
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )


# =========================
# ACTUALIZACIÓN
# =========================
def find_row_index_first(tab_name: str, criteria: Dict[str, str]) -> Optional[int]:
    headers = get_headers(tab_name)
    h2i = {h: i for i, h in enumerate(headers)}
    values = get_all_values(tab_name)

    if not values or len(values) < 2:
        return None

    for r in range(2, len(values) + 1):
        row = values[r - 1]
        ok = True
        for k, v in criteria.items():
            if k not in h2i:
                ok = False
                break

            idx = h2i[k]
            cell = row[idx] if idx < len(row) else ""
            if str(cell).strip() != str(v).strip():
                ok = False
                break

        if ok:
            return r

    return None


def update_row_by_headers(tab_name: str, row_index: int, patch: Dict[str, Any]) -> None:
    ws = get_worksheet(tab_name)
    headers = get_headers(tab_name)
    h2c = {h: i + 1 for i, h in enumerate(headers)}

    for k, v in patch.items():
        col = h2c.get(k)
        if col:
            ws.update_cell(row_index, col, "" if v is None else str(v))


def delete_row(tab_name: str, row_index: int) -> None:
    ws = get_worksheet(tab_name)
    ws.delete_rows(row_index)


# =========================
# ENQUEUE COMPATIBLE
# =========================
def enqueue_row(tab_name: str, data: Dict[str, Any], source: str = "app") -> None:
    """
    Wrapper para mantener compatibilidad con la cola.
    Si quieres escritura directa, usa append_dict.
    """
    from services.sheets_queue_service import enqueue_row as queue_enqueue_row
    queue_enqueue_row(tab_name, data, source=source)


# =========================
# DRIVE DOWNLOAD
# =========================
def get_drive_file_metadata(file_id: str) -> Dict[str, Any]:
    fid = str(file_id or "").strip()
    if not fid:
        raise ValueError("file_id vacío")

    service = get_drive_service()
    meta = service.files().get(
        fileId=fid,
        fields="id,name,mimeType,size"
    ).execute()

    return {
        "id": str(meta.get("id", "")).strip(),
        "name": str(meta.get("name", "")).strip(),
        "mimeType": str(meta.get("mimeType", "")).strip(),
        "size": str(meta.get("size", "")).strip(),
    }


def download_drive_file_bytes(file_id: str) -> Tuple[bytes, str, str]:
    """
    Devuelve: (contenido_bytes, nombre_archivo, mime_type)
    """
    fid = str(file_id or "").strip()
    if not fid:
        raise ValueError("file_id vacío")

    service = get_drive_service()
    meta = get_drive_file_metadata(fid)

    request = service.files().get_media(fileId=fid)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = buffer.getvalue()
    filename = meta.get("name", "") or f"{fid}.bin"
    mime_type = meta.get("mimeType", "") or "application/octet-stream"

    logger.info("✅ Archivo descargado desde Drive: %s", filename)
    return content, filename, mime_type


# =========================
# HELPERS DE DOMINIO
# =========================
def fetch_last_plantilla_for_codigo(codigo: str) -> Optional[Dict[str, str]]:
    records = get_all_records(SHEET_TAB_PLANTILLAS)
    last = None

    for r in records:
        if str(r.get("CódigoPedido", "")).strip() == str(codigo).strip():
            last = r

    if not last:
        return None

    return {
        "Contrata": str(last.get("Contrata", "")).strip(),
        "Distrito": str(last.get("Distrito", "")).strip(),
        "Gestor": str(last.get("Gestor", "")).strip(),
        "PlantillaUUID": str(last.get("PlantillaUUID", "")).strip(),
    }


def get_supervisores() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_SUPERVISORES)


def get_tecnicos_tufibra() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_TECNICOS_TUFIBRA)


def get_info_tecnicos() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_INFO_TECNICOS)


def get_sctr_records() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_SCTR)


def get_cuadrillas_win() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_CUADRILLAS_WIN)


def get_distritos() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_DISTRITOS)


def get_routing_records() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_ROUTING)


def get_pairing_records() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_PAIRING)


def get_almuerzos_records() -> List[Dict[str, Any]]:
    return get_all_records(SHEET_TAB_ALMUERZOS)


# =========================
# GUARDADOS ESPECÍFICOS
# =========================
def save_supervision_row(data: Dict[str, Any], queued: bool = True) -> None:
    if queued:
        enqueue_row(SHEET_TAB_SUPERVISIONES_V2, data, source="save_supervision_row")
    else:
        append_dict(SHEET_TAB_SUPERVISIONES_V2, data)


def save_pairing_row(data: Dict[str, Any], queued: bool = False) -> None:
    if queued:
        enqueue_row(SHEET_TAB_PAIRING, data, source="save_pairing_row")
    else:
        append_dict(SHEET_TAB_PAIRING, data)


def save_almuerzo_row(data: Dict[str, Any], queued: bool = False) -> None:
    if queued:
        enqueue_row(SHEET_TAB_ALMUERZOS, data, source="save_almuerzo_row")
    else:
        append_dict(SHEET_TAB_ALMUERZOS, data)


# =========================
# SALUD
# =========================
def test_connection() -> Dict[str, Any]:
    try:
        sh = get_sheet()
        return {
            "ok": True,
            "title": sh.title,
            "checked_at": now_peru_str(),
        }
    except Exception as e:
        logger.exception("❌ Error en test_connection")
        return {
            "ok": False,
            "error": str(e),
            "checked_at": now_peru_str(),
        }