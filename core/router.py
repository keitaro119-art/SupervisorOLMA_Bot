# =========================
# core/router.py
# Router central del bot (decide qué handler ejecutar)
# =========================

from typing import Callable, Dict, Any

from core.session_manager import get_state
from utils.logger import log_event

# =========================
# REGISTROS
# =========================
_MESSAGE_ROUTES: Dict[str, Callable] = {}
_CALLBACK_ROUTES: Dict[str, Callable] = {}

_DEFAULT_MESSAGE_HANDLER: Callable = None
_DEFAULT_CALLBACK_HANDLER: Callable = None


# =========================
# REGISTRO DE HANDLERS
# =========================
def register_message_handler(state: str, handler: Callable):
    _MESSAGE_ROUTES[state] = handler


def register_callback_handler(prefix: str, handler: Callable):
    _CALLBACK_ROUTES[prefix] = handler


def register_default_message(handler: Callable):
    global _DEFAULT_MESSAGE_HANDLER
    _DEFAULT_MESSAGE_HANDLER = handler


def register_default_callback(handler: Callable):
    global _DEFAULT_CALLBACK_HANDLER
    _DEFAULT_CALLBACK_HANDLER = handler


# =========================
# RESOLUCIÓN DE HANDLERS
# =========================
def _resolve_message_handler(state: str) -> Callable:
    return _MESSAGE_ROUTES.get(state, _DEFAULT_MESSAGE_HANDLER)


def _resolve_callback_handler(data: str) -> Callable:
    if not data:
        return _DEFAULT_CALLBACK_HANDLER

    # Busca por prefijo
    for prefix, handler in _CALLBACK_ROUTES.items():
        if data.startswith(prefix):
            return handler

    return _DEFAULT_CALLBACK_HANDLER


# =========================
# ENTRYPOINTS (Telegram)
# =========================
async def handle_message(update, context):
    try:
        chat_id = update.effective_chat.id
        state = get_state(chat_id)

        handler = _resolve_message_handler(state)

        if handler is None:
            log_event("ROUTER_NO_HANDLER", chat_id=chat_id, state=state)
            return

        log_event("ROUTER_MESSAGE", chat_id=chat_id, state=state)

        await handler(update, context)

    except Exception as e:
        log_event("ROUTER_ERROR_MESSAGE", error=str(e))
        raise


async def handle_callback(update, context):
    try:
        query = update.callback_query
        data = query.data if query else ""

        chat_id = update.effective_chat.id if update.effective_chat else None

        handler = _resolve_callback_handler(data)

        if handler is None:
            log_event("ROUTER_NO_CALLBACK_HANDLER", data=data)
            return

        log_event("ROUTER_CALLBACK", chat_id=chat_id, data=data)

        await handler(update, context)

    except Exception as e:
        log_event("ROUTER_ERROR_CALLBACK", error=str(e))
        raise


# =========================
# DEBUG / VISUALIZACIÓN
# =========================
def get_registered_routes() -> Dict[str, Any]:
    return {
        "message_routes": list(_MESSAGE_ROUTES.keys()),
        "callback_routes": list(_CALLBACK_ROUTES.keys()),
        "has_default_message": _DEFAULT_MESSAGE_HANDLER is not None,
        "has_default_callback": _DEFAULT_CALLBACK_HANDLER is not None,
    }