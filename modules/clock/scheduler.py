"""
Módulo 1: The Clock — Orquestador y Planificador
Responsabilidades:
  - Disparar scraping global a las 06:00 y 12:00 (hora Argentina)
  - Prevenir ejecuciones solapadas mediante asyncio.Lock
  - Gestionar reintentos automáticos cada RETRY_INTERVAL_MINUTES
  - Registrar cada ciclo en MongoDB (colección scraping_logs)
  - Exponer trigger manual para el Dashboard
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.settings import settings
from db.client import get_db

# Zona horaria Argentina
ARGENTINA_TZ = "America/Argentina/Buenos_Aires"

# Lock global: impide solapamiento de ciclos
_scraping_lock = asyncio.Lock()

# Evento de cancelación: se activa vía /clock/cancel para detener el ciclo activo
_cancel_event = asyncio.Event()

# Semáforo global: limita pestañas/contextos concurrentes del Harvester
scraping_semaphore = asyncio.Semaphore(settings.max_concurrent_scrapers)


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

async def _create_log(execution_id: str, cadenas: list[str]) -> None:
    doc = {
        "execution_id": execution_id,
        "started_at": datetime.now(tz=timezone.utc),
        "cadenas": cadenas,
        "checkpoints": {},          # {cadena_id: "pending"|"ok"|"error"}
        "status": "running",
        "finished_at": None,
        "error": None,
    }
    for cadena in cadenas:
        doc["checkpoints"][cadena] = "pending"
    await get_db().scraping_logs.insert_one(doc)
    logger.debug(f"[Clock] Log creado: {execution_id}")


async def _update_checkpoint(execution_id: str, cadena_id: str, status: str) -> None:
    await get_db().scraping_logs.update_one(
        {"execution_id": execution_id},
        {"$set": {f"checkpoints.{cadena_id}": status}},
    )


async def _close_log(execution_id: str, status: str, error: str | None = None) -> None:
    await get_db().scraping_logs.update_one(
        {"execution_id": execution_id},
        {
            "$set": {
                "status": status,
                "finished_at": datetime.now(tz=timezone.utc),
                "error": error,
            }
        },
    )
    logger.info(f"[Clock] Ciclo {execution_id} finalizado con estado: {status}")


# ---------------------------------------------------------------------------
# Lógica de obtención de cadenas activas
# ---------------------------------------------------------------------------

async def _get_active_cadenas() -> list[dict[str, Any]]:
    cursor = get_db().comercios_config.find({"activo": True}, {"cadena_id": 1, "url_base": 1})
    return await cursor.to_list(length=None)


# ---------------------------------------------------------------------------
# Ciclo principal de scraping
# ---------------------------------------------------------------------------

async def _run_scraping_cycle(triggered_by: str = "scheduler") -> None:
    if _scraping_lock.locked():
        logger.warning(
            "[Clock] Ciclo anterior aún en ejecución. "
            "Se cancela el nuevo disparo para evitar solapamiento."
        )
        return

    _cancel_event.clear()

    async with _scraping_lock:
        execution_id = str(uuid4())
        logger.info(f"[Clock] ▶ Iniciando ciclo | id={execution_id} | origen={triggered_by}")

        cadenas = await _get_active_cadenas()
        if not cadenas:
            logger.warning("[Clock] No hay cadenas activas en comercios_config.")
            return

        cadena_ids = [c["cadena_id"] for c in cadenas]
        await _create_log(execution_id, cadena_ids)

        failed: list[str] = []

        for cadena in cadenas:
            if _cancel_event.is_set():
                logger.info("[Clock] Ciclo cancelado por usuario entre cadenas.")
                break
            success = await _run_with_retries(execution_id, cadena)
            if not success:
                failed.append(cadena["cadena_id"])

        if _cancel_event.is_set():
            await _close_log(execution_id, "cancelled", "Cancelado manualmente.")
            logger.info(f"[Clock] Ciclo {execution_id} marcado como cancelado.")
            return

        # Fase 2: Promo Engine — desactivado hasta implementación estable
        # cadenas_ok = [c for c in cadenas if c["cadena_id"] not in failed]
        # if cadenas_ok:
        #     logger.info(f"[Clock] Iniciando Promo Engine para {len(cadenas_ok)} cadenas")
        #     await _run_promo_engine_phase(cadenas_ok)

        # Fase 3: Sincronización de productos_vigentes (pre-agregación para O(1) en frontend)
        if not _cancel_event.is_set():
            try:
                from modules.brain.sync import sync_productos_vigentes
                count = await sync_productos_vigentes()
                logger.info(f"[Clock] Fase 3 completa: {count} productos vigentes sincronizados.")
            except Exception as exc:
                logger.error(f"[Clock] Fase 3 (sync_productos_vigentes) falló: {exc}")

        final_status = "completed" if not failed else "partial"
        error_msg = f"Fallaron: {failed}" if failed else None
        await _close_log(execution_id, final_status, error_msg)

        logger.info(f"[Clock] ✔ Ciclo completo. Estado: {final_status}")


async def _run_with_retries(execution_id: str, cadena: dict[str, Any]) -> bool:
    cadena_id = cadena["cadena_id"]
    attempt = 0

    while attempt < settings.max_retries:
        attempt += 1
        logger.info(f"[Clock] → {cadena_id} | intento {attempt}/{settings.max_retries}")

        try:
            await _dispatch_harvester(cadena)
            await _update_checkpoint(execution_id, cadena_id, "ok")
            return True

        except Exception as exc:
            logger.error(f"[Clock] ✗ {cadena_id} falló (intento {attempt}): {exc}")
            await _update_checkpoint(execution_id, cadena_id, f"error_intento_{attempt}")

            if attempt < settings.max_retries:
                wait_secs = settings.retry_interval_minutes * 60
                logger.info(
                    f"[Clock] Reintentando {cadena_id} en "
                    f"{settings.retry_interval_minutes} min..."
                )
                # Wait interruptibly: returns early if cancel is requested
                try:
                    await asyncio.wait_for(_cancel_event.wait(), timeout=wait_secs)
                    # Event was set → cancel requested
                    logger.info(f"[Clock] Espera de reintento cancelada para {cadena_id}.")
                    await _update_checkpoint(execution_id, cadena_id, "cancelled")
                    return False
                except asyncio.TimeoutError:
                    pass  # Normal: wait elapsed, proceed with retry

    await _update_checkpoint(execution_id, cadena_id, "failed")
    return False


async def _dispatch_harvester(cadena: dict[str, Any]) -> None:
    from modules.harvester import run_harvester  # import diferido para evitar ciclos
    async with scraping_semaphore:
        await run_harvester(cadena, semaphore=scraping_semaphore)


async def _run_promo_engine_phase(cadenas: list[dict[str, Any]]) -> None:
    from modules.promo_engine import run_promo_engine  # import diferido
    tasks = [run_promo_engine(cadena) for cadena in cadenas]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for cadena, result in zip(cadenas, results):
        if isinstance(result, Exception):
            logger.error(
                f"[Clock] PromoEngine falló para {cadena['cadena_id']}: {result}"
            )
        else:
            logger.info(
                f"[Clock] PromoEngine {cadena['cadena_id']}: {result} reglas"
            )


# ---------------------------------------------------------------------------
# Scheduler (APScheduler)
# ---------------------------------------------------------------------------

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ARGENTINA_TZ)

    # Disparo 1: 06:00 AM Argentina
    scheduler.add_job(
        _run_scraping_cycle,
        trigger=CronTrigger(hour=settings.schedule_hour_1, minute=0, timezone=ARGENTINA_TZ),
        kwargs={"triggered_by": "scheduler_6am"},
        id="scraping_6am",
        replace_existing=True,
        max_instances=1,
    )

    # Disparo 2: 12:00 PM Argentina
    scheduler.add_job(
        _run_scraping_cycle,
        trigger=CronTrigger(hour=settings.schedule_hour_2, minute=0, timezone=ARGENTINA_TZ),
        kwargs={"triggered_by": "scheduler_12pm"},
        id="scraping_12pm",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------

async def trigger_manual() -> dict[str, str]:
    """Disparo manual desde el Dashboard (Módulo 6)."""
    if _scraping_lock.locked():
        return {"status": "busy", "message": "Ya hay un ciclo en ejecución."}

    asyncio.create_task(_run_scraping_cycle(triggered_by="manual"))
    return {"status": "started", "message": "Ciclo manual iniciado."}


async def cancel_scraping() -> dict[str, str]:
    """Cancela el ciclo activo lo antes posible (entre cadenas o retries)."""
    if not _scraping_lock.locked():
        return {"status": "idle", "message": "No hay ciclo en ejecución."}
    _cancel_event.set()
    logger.info("[Clock] Cancelación solicitada por usuario.")
    return {"status": "cancelling", "message": "Cancelación solicitada. El ciclo se detendrá pronto."}


async def get_last_log() -> dict | None:
    """Devuelve el último log de ejecución."""
    doc = await get_db().scraping_logs.find_one(
        sort=[("started_at", -1)]
    )
    if doc:
        doc.pop("_id", None)
    return doc
