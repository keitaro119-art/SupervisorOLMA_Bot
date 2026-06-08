# =========================
# utils/logger.py
# Logger centralizado (Enterprise)
# =========================

import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime


# =========================
# CONFIGURACIÓN GENERAL
# =========================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LOG_FILE = "logs/bot.log"
MAX_BYTES = 5 * 1024 * 1024   # 5 MB
BACKUP_COUNT = 3


# =========================
# CREAR LOGGER
# =========================
def setup_logger(name: str = "bot") -> logging.Logger:
    logger = logging.getLogger(name)

    # Evitar duplicados
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # =========================
    # CONSOLE HANDLER
    # =========================
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # =========================
    # FILE HANDLER (ROTATIVO)
    # =========================
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"No se pudo inicializar file logger: {e}")

    return logger


# =========================
# LOGGER GLOBAL
# =========================
logger = setup_logger("tufibra_bot")


# =========================
# HELPERS
# =========================
def log_info(msg: str):
    logger.info(msg)


def log_warning(msg: str):
    logger.warning(msg)


def log_error(msg: str):
    logger.error(msg)


def log_debug(msg: str):
    logger.debug(msg)


# =========================
# LOG ESTRUCTURADO
# =========================
def log_event(event: str, **kwargs):
    """
    Log estructurado para trazabilidad
    """
    details = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"{event} | {details}")


# =========================
# LOG DE ERRORES CRÍTICOS
# =========================
def log_exception(e: Exception, context: str = ""):
    logger.exception(f"ERROR en {context}: {str(e)}")


# =========================
# LOG DE TELEGRAM CALLBACK
# =========================
def log_callback(data: str, chat_id=None, user_id=None):
    logger.info(
        f"CALLBACK data={data} chat_id={chat_id} user_id={user_id}"
    )


# =========================
# LOG DE SHEETS
# =========================
def log_sheets(action: str, sheet: str, **kwargs):
    details = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"SHEETS {action} -> sheet={sheet} | {details}")


# =========================
# LOG DE MEDIA
# =========================
def log_media(step: str, file_id: str, **kwargs):
    details = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"MEDIA step={step} file_id={file_id} | {details}")


# =========================
# TIMESTAMP UTIL
# =========================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")