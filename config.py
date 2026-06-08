# =========================
# config.py
# Configuración global enterprise
# =========================

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Optional


# =========================
# LOGGING
# =========================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper().strip()
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log").strip()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() in ("1", "true", "yes", "y")


def setup_logging() -> None:
    handlers = [logging.StreamHandler(sys.stdout)]

    if LOG_TO_FILE:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


# =========================
# EXCEPTION HANDLERS
# =========================
def install_global_exception_handlers() -> None:
    def _excepthook(exc_type, exc, tb):
        logging.critical("UNHANDLED EXCEPTION (sys.excepthook)", exc_info=(exc_type, exc, tb))
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass

    sys.excepthook = _excepthook

    try:
        loop = asyncio.get_event_loop()
    except Exception:
        loop = None

    if loop:
        def _loop_exception_handler(_loop, context):
            logging.critical("UNHANDLED ASYNCIO ERROR: %s", context.get("message", ""))
            exc = context.get("exception")
            if exc:
                logging.critical("Exception:", exc_info=exc)
            else:
                logging.critical("Context: %s", context)
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass

        loop.set_exception_handler(_loop_exception_handler)


# =========================
# TIMEZONE
# =========================
PERU_TZ = timezone(timedelta(hours=-5))


def now_peru_dt() -> datetime:
    return datetime.now(PERU_TZ)


def now_peru_str() -> str:
    return now_peru_dt().strftime("%Y-%m-%d %H:%M:%S")


def iso_peru(dt: datetime) -> str:
    return dt.astimezone(PERU_TZ).strftime("%Y-%m-%d %H:%M:%S")


def date_peru_ymd(dt: Optional[datetime] = None) -> str:
    d = (dt or now_peru_dt()).astimezone(PERU_TZ)
    return d.strftime("%Y-%m-%d")


def parse_dt_peru(s: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=PERU_TZ)
    except Exception:
        return None


def format_duration_between(start_str: str, end_str: str) -> str:
    try:
        dt_start = datetime.strptime(str(start_str).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=PERU_TZ)
        dt_end = datetime.strptime(str(end_str).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=PERU_TZ)
        total_seconds = max(0, int((dt_end - dt_start).total_seconds()))
    except Exception:
        return "N/D"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours} h {minutes} min {seconds} seg"
    if minutes > 0:
        return f"{minutes} min {seconds} seg"
    return f"{seconds} seg"


# =========================
# TELEGRAM
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TG_MAX_RETRIES = int(os.getenv("TG_MAX_RETRIES", "5"))
TG_RETRY_JITTER_SEC = float(os.getenv("TG_RETRY_JITTER_SEC", "0.7"))
DROP_PENDING_UPDATES = os.getenv("DROP_PENDING_UPDATES", "true").lower() in ("1", "true", "yes", "y")


# =========================
# GOOGLE SHEETS
# =========================
SHEET_ID = os.getenv("SHEET_ID", "").strip()
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON", "google_creds.json").strip()
GOOGLE_CREDS_JSON_TEXT = os.getenv("GOOGLE_CREDS_JSON_TEXT", "").strip()

SHEET_TAB_PLANTILLAS = os.getenv("SHEET_TAB_PLANTILLAS", "Plantillas").strip()
SHEET_TAB_SUPERVISIONES_V2 = os.getenv("SHEET_TAB_SUPERVISIONES_V2", "Supervisiones_v2").strip()
SHEET_TAB_SUPERVISORES = os.getenv("SHEET_TAB_SUPERVISORES", "SUPERVISORES").strip()
SHEET_TAB_TECNICOS_TUFIBRA = os.getenv("SHEET_TAB_TECNICOS_TUFIBRA", "TECNICOS_TUFIBRA").strip()
SHEET_TAB_INFO_TECNICOS = os.getenv("SHEET_TAB_INFO_TECNICOS", "INFO_TECNICOS").strip()
SHEET_TAB_SCTR = os.getenv("SHEET_TAB_SCTR", "SCTR").strip()
SHEET_TAB_CUADRILLAS_WIN = os.getenv("SHEET_TAB_CUADRILLAS_WIN", "CUADRILLAS_WIN").strip()
SHEET_TAB_DISTRITOS = os.getenv("SHEET_TAB_DISTRITOS", "DISTRITOS").strip()
SHEET_TAB_ROUTING = os.getenv("SHEET_TAB_ROUTING", "ROUTING").strip()
SHEET_TAB_PAIRING = os.getenv("SHEET_TAB_PAIRING", "PAIRING").strip()
SHEET_TAB_ALMUERZOS = os.getenv("SHEET_TAB_ALMUERZOS", "ALMUERZOS").strip()


# =========================
# CACHE / QUEUE
# =========================
SUP_CACHE_TTL_SEC = int(os.getenv("SUP_CACHE_TTL_SEC", "180"))
CUAD_CACHE_TTL_SEC = int(os.getenv("CUAD_CACHE_TTL_SEC", "180"))
DIST_CACHE_TTL_SEC = int(os.getenv("DIST_CACHE_TTL_SEC", "180"))
ROUTING_CACHE_TTL_SEC = int(os.getenv("ROUTING_CACHE_TTL_SEC", "180"))

QUEUE_ENABLED = os.getenv("QUEUE_ENABLED", "true").lower() in ("1", "true", "yes", "y")
QUEUE_BATCH_SIZE = int(os.getenv("QUEUE_BATCH_SIZE", "10"))
QUEUE_MAX_RETRIES = int(os.getenv("QUEUE_MAX_RETRIES", "5"))
QUEUE_WORKER_INTERVAL_SEC = int(os.getenv("QUEUE_WORKER_INTERVAL_SEC", "15"))
QUEUE_FIRST_RUN_SEC = int(os.getenv("QUEUE_FIRST_RUN_SEC", "8"))


# =========================
# PAIRING / ROUTING
# =========================
PAIRING_TTL_MINUTES = int(os.getenv("PAIRING_TTL_MINUTES", "10"))
ROUTING_JSON = os.getenv("ROUTING_JSON", "").strip()


# =========================
# MEDIA
# =========================
MAX_MEDIA_PER_BUCKET = int(os.getenv("MAX_MEDIA_PER_BUCKET", "8"))
ENABLE_WATERMARK_PHOTOS = os.getenv("ENABLE_WATERMARK_PHOTOS", "false").lower() in ("1", "true", "yes", "y")
WM_DIR = os.getenv("WM_DIR", "wm_tmp").strip()
WM_FONT_SIZE = int(os.getenv("WM_FONT_SIZE", "22"))
MEDIA_NOTIFY_DEBOUNCE_SEC = float(os.getenv("MEDIA_NOTIFY_DEBOUNCE_SEC", "1.0"))


# =========================
# DAILY SUMMARY
# =========================
DAILY_SUMMARY_ENABLED = os.getenv("DAILY_SUMMARY_ENABLED", "true").lower() in ("1", "true", "yes", "y")
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "20"))
DAILY_SUMMARY_MINUTE = int(os.getenv("DAILY_SUMMARY_MINUTE", "0"))
DAILY_SUMMARY_SEND_TO_ORIGIN_IF_NO_SUMMARY = os.getenv(
    "DAILY_SUMMARY_SEND_TO_ORIGIN_IF_NO_SUMMARY",
    "true",
).lower() in ("1", "true", "yes", "y")


# =========================
# SEARCH / SUGGESTIONS
# =========================
WIN_SUGGEST_MAX = int(os.getenv("WIN_SUGGEST_MAX", "6"))
WIN_BUTTONS_MAX = int(os.getenv("WIN_BUTTONS_MAX", "5"))
DIST_SUGGEST_MAX = int(os.getenv("DIST_SUGGEST_MAX", "8"))
DIST_BUTTONS_MAX = int(os.getenv("DIST_BUTTONS_MAX", "6"))


# =========================
# SESSION / STORAGE
# =========================
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 6)))
SQLITE_PATH = os.getenv("SQLITE_PATH", "storage/bot_supervision.sqlite3").strip()
AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in ("1", "true", "yes", "y")


# =========================
# JOB TIMES
# =========================
def daily_summary_time() -> dtime:
    return dtime(hour=DAILY_SUMMARY_HOUR, minute=DAILY_SUMMARY_MINUTE, tzinfo=PERU_TZ)


# =========================
# VALIDATION
# =========================
def validate_runtime_config() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no configurado.")
    if not SHEET_ID:
        raise RuntimeError("SHEET_ID no configurado.")


def ensure_google_creds_file_if_needed() -> None:
    if GOOGLE_CREDS_JSON_TEXT and not os.path.exists(GOOGLE_CREDS_JSON):
        directory = os.path.dirname(GOOGLE_CREDS_JSON)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(GOOGLE_CREDS_JSON, "w", encoding="utf-8") as f:
            f.write(GOOGLE_CREDS_JSON_TEXT)


def gs_ready() -> bool:
    if not SHEET_ID:
        return False
    if GOOGLE_CREDS_JSON_TEXT:
        return True
    return os.path.exists(GOOGLE_CREDS_JSON)


def load_google_creds_dict() -> dict:
    if GOOGLE_CREDS_JSON_TEXT:
        data = json.loads(GOOGLE_CREDS_JSON_TEXT)
    else:
        ensure_google_creds_file_if_needed()
        with open(GOOGLE_CREDS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)

    pk = data.get("private_key", "")
    if isinstance(pk, str) and "\\n" in pk:
        data["private_key"] = pk.replace("\\n", "\n")

    return data