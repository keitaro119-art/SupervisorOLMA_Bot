# =========================
# utils/helpers.py
# Utilitarios generales (Enterprise)
# =========================

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# =========================
# TIMEZONE PERU (UTC-5)
# =========================
PERU_TZ = timezone(timedelta(hours=-5))


# =========================
# FECHAS
# =========================
def now_peru() -> datetime:
    return datetime.now(PERU_TZ)


def now_str() -> str:
    """
    Formato estándar usado en Sheets:
    26-03-2026 12:52
    """
    return now_peru().strftime("%d-%m-%Y %H:%M")


def date_only_str(dt: Optional[datetime] = None) -> str:
    dt = dt or now_peru()
    return dt.strftime("%d/%m/%Y")


def time_only_str(dt: Optional[datetime] = None) -> str:
    dt = dt or now_peru()
    return dt.strftime("%H:%M")


def iso_to_peru_str(iso_str: str) -> str:
    """
    Convierte ISO:
    2026-03-26T17:46:25.759728+00:00
    -> 26-03-2026 12:46
    """
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt = dt.astimezone(PERU_TZ)
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return iso_str


# =========================
# TEXTO
# =========================
def normalize_text(text: str) -> str:
    """
    Limpia texto para comparaciones:
    - lower
    - sin tildes
    - sin espacios extra
    """
    if not text:
        return ""

    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"\s+", " ", text)

    return text


def contains_partial(text: str, keywords: str) -> bool:
    """
    keywords = "juan; arucutipa; p32"
    """
    text_n = normalize_text(text)

    for k in keywords.split(";"):
        if normalize_text(k) in text_n:
            return True

    return False


# =========================
# LISTAS / SEGURIDAD
# =========================
def safe_get(d: Dict, key: str, default=None):
    return d[key] if key in d else default


def chunk_list(data: List[Any], size: int) -> List[List[Any]]:
    return [data[i:i + size] for i in range(0, len(data), size)]


# =========================
# VALIDACIONES
# =========================
def is_yes(text: str) -> bool:
    from constants import RESPUESTA_SI
    return normalize_text(text) in [normalize_text(x) for x in RESPUESTA_SI]


def is_no(text: str) -> bool:
    from constants import RESPUESTA_NO
    return normalize_text(text) in [normalize_text(x) for x in RESPUESTA_NO]


# =========================
# IDs / KEYS
# =========================
def build_id(prefix: str = "") -> str:
    """
    Genera ID único simple
    """
    ts = now_peru().strftime("%Y%m%d%H%M%S")
    return f"{prefix}{ts}"


# =========================
# TELEGRAM
# =========================
def extract_file_id(update) -> Optional[str]:
    """
    Extrae file_id de mensajes (foto/documento)
    """
    if update.message.photo:
        return update.message.photo[-1].file_id

    if update.message.document:
        return update.message.document.file_id

    if update.message.video:
        return update.message.video.file_id

    return None


def get_user_name(update) -> str:
    user = update.effective_user
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


# =========================
# TIEMPO / DURACIONES
# =========================
def calc_duration_minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() / 60)


def duration_text(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


# =========================
# RETRIES (UTIL)
# =========================
def retry(func, retries=3, delay=1, exceptions=(Exception,)):
    import time

    for i in range(retries):
        try:
            return func()
        except exceptions as e:
            if i == retries - 1:
                raise
            time.sleep(delay * (i + 1))


# =========================
# DEBUG
# =========================
def debug_print(*args):
    from constants import DEBUG_FLOW
    if DEBUG_FLOW:
        print("[DEBUG]", *args)