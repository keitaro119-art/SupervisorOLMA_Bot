# =========================
# main.py
# Orquestador principal del bot
# =========================

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    DROP_PENDING_UPDATES,
    setup_logging,
    install_global_exception_handlers,
    validate_runtime_config,
    DAILY_SUMMARY_ENABLED,
    daily_summary_time,
    QUEUE_ENABLED,
    QUEUE_WORKER_INTERVAL_SEC,
    QUEUE_FIRST_RUN_SEC,
)

from utils.logger import log_event
from handlers.error_handler import error_handler
from handlers.health_handler import health_check, metrics_check

from core.router import (
    handle_callback,
    handle_message,
    register_message_handler,
    register_callback_handler,
)

from handlers.start_handler import start_command, start_menu_callback
from handlers.supervisor_handler import supervisor_callback
from handlers.empresa_handler import empresa_callback

from handlers.tecnico_handler import (
    tecnico_callback,
    tecnico_search_input,
    tecnico_manual_input,
    placa_unidad_input,
)

from handlers.cuadrilla_handler import (
    cuadrilla_callback,
    cuadrilla_search_input,
    cuadrilla_manual_input,
)

from handlers.distrito_handler import (
    distrito_callback,
    distrito_search_input,
    distrito_manual_input,
)

from handlers.tipo_supervision_handler import tipo_supervision_callback
from handlers.codigo_pedido_handler import codigo_pedido_input
from handlers.ubicacion_handler import ubicacion_input
from handlers.selfie_handler import selfie_input

from handlers.menu_handler import menu_callback
from handlers.step_handler import step_callback, step_input
from handlers.info_handler import info_selected, handle_info_input
from handlers.final_handler import final_callback, observaciones_finales_input
from handlers.almuerzo_handler import almuerzo_callback

from handlers.command_handler import (
    stop_command,
    forzar_cierre_command,
    reset_command,
    liberar_command,
    reload_sheet_command,
    reintentar_envio_command,
    logs_command,
)

from jobs.sheets_worker_job import sheets_worker_job
from services.summary_service import (
    get_completed_supervisions_for_day,
    group_supervisions_by_origin,
    build_daily_summary_text,
    resolve_summary_target,
)
from services.google_sheets_service import test_connection


# =========================
# DAILY SUMMARY JOB
# =========================
async def daily_summary_job(context):
    try:
        records = get_completed_supervisions_for_day()
        grouped = group_supervisions_by_origin(records)

        if not grouped:
            return

        from config import date_peru_ymd
        day = date_peru_ymd()

        for origin, recs in grouped.items():
            try:
                target = resolve_summary_target(int(origin))
                if not target:
                    continue

                text = build_daily_summary_text(recs, day)
                await context.bot.send_message(chat_id=target, text=text)

            except Exception as e:
                log_event("DAILY_SUMMARY_SEND_ERROR", origin=origin, error=str(e))

        log_event("DAILY_SUMMARY_DONE", groups=len(grouped))

    except Exception as e:
        log_event("DAILY_SUMMARY_JOB_ERROR", error=str(e))


# =========================
# REGISTRO DEL ROUTER
# =========================
def register_routes():
    # -------- MESSAGE STATES --------

    # Técnicos
    register_message_handler("SEARCH_TECNICO", tecnico_search_input)
    register_message_handler("INPUT_TECNICO_MANUAL", tecnico_manual_input)
    register_message_handler("INPUT_PLACA_UNIDAD", placa_unidad_input)

    # Cuadrilla
    register_message_handler("SEARCH_CUADRILLA", cuadrilla_search_input)
    register_message_handler("INPUT_CUADRILLA_MANUAL", cuadrilla_manual_input)

    # Código pedido / distrito / ubicación / selfie
    register_message_handler("INPUT_CODIGO_PEDIDO", codigo_pedido_input)
    register_message_handler("SEARCH_DISTRITO", distrito_search_input)
    register_message_handler("INPUT_DISTRITO_MANUAL", distrito_manual_input)
    register_message_handler("WAIT_LOCATION_CLIENTE", ubicacion_input)
    register_message_handler("WAIT_SELFIE_FACHADA", selfie_input)

    # Evidencias / info
    register_message_handler("UPLOAD_EVIDENCIA", step_input)
    register_message_handler("MENU_INFO", handle_info_input)

    # Finalización
    register_message_handler("INPUT_OBSERVACIONES_FINALES", observaciones_finales_input)

    # -------- CALLBACK PREFIX --------
    register_callback_handler("START_", start_menu_callback)
    register_callback_handler("SUPERVISOR|", supervisor_callback)
    register_callback_handler("EMPRESA|", empresa_callback)

    register_callback_handler("TECNICO|", tecnico_callback)
    register_callback_handler("TIPO_SUP|", tipo_supervision_callback)

    register_callback_handler("CUADRILLA|", cuadrilla_callback)
    register_callback_handler("DISTRITO|", distrito_callback)

    register_callback_handler("MENU|", menu_callback)
    register_callback_handler("STEP|", step_callback)
    register_callback_handler("INFO|", info_selected)
    register_callback_handler("FINAL|", final_callback)
    register_callback_handler("ALMUERZO|", almuerzo_callback)


# =========================
# STARTUP
# =========================
async def post_init(app: Application):
    log_event("BOT_POST_INIT_START")

    try:
        health = test_connection()
        if health.get("ok"):
            log_event("SHEETS_CONNECTED_OK", title=health.get("title"))
        else:
            log_event("SHEETS_CONNECTED_ERROR", error=health.get("error"))
    except Exception as e:
        log_event("SHEETS_CONNECTED_ERROR", error=str(e))

    if QUEUE_ENABLED and app.job_queue:
        app.job_queue.run_repeating(
            sheets_worker_job,
            interval=QUEUE_WORKER_INTERVAL_SEC,
            first=QUEUE_FIRST_RUN_SEC,
            name="sheets_worker_job",
        )
        log_event(
            "JOB_REGISTERED",
            job="sheets_worker_job",
            interval=QUEUE_WORKER_INTERVAL_SEC,
            first=QUEUE_FIRST_RUN_SEC,
        )

    if DAILY_SUMMARY_ENABLED and app.job_queue:
        app.job_queue.run_daily(
            daily_summary_job,
            time=daily_summary_time(),
            name="daily_summary_job",
        )
        log_event(
            "JOB_REGISTERED",
            job="daily_summary_job",
            time=str(daily_summary_time()),
        )

    log_event("BOT_POST_INIT_DONE")


# =========================
# BUILD APP
# =========================
def build_app() -> Application:
    register_routes()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_command))

    app.add_handler(CommandHandler("health", health_check))
    app.add_handler(CommandHandler("metrics", metrics_check))

    app.add_handler(CommandHandler("forzar_cierre", forzar_cierre_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("liberar", liberar_command))
    app.add_handler(CommandHandler("reload_sheet", reload_sheet_command))
    app.add_handler(CommandHandler("reintentar_envio", reintentar_envio_command))
    app.add_handler(CommandHandler("logs", logs_command))

    app.add_handler(CallbackQueryHandler(handle_callback), group=0)

    app.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.LOCATION
            | filters.PHOTO
            | filters.VIDEO
            | filters.Document.ALL,
            handle_message,
        ),
        group=1,
    )

    app.add_error_handler(error_handler)

    return app


# =========================
# MAIN
# =========================
def main():
    setup_logging()
    install_global_exception_handlers()
    validate_runtime_config()

    log_event("BOT_STARTING")

    app = build_app()

    log_event("RUN_POLLING", drop_pending_updates=DROP_PENDING_UPDATES)
    app.run_polling(drop_pending_updates=DROP_PENDING_UPDATES)


if __name__ == "__main__":
    main()