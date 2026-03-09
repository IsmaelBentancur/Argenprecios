# -*- coding: utf-8 -*-
"""
Modulo 1: The Clock - Orquestador y Planificador
Responsabilidades:
  - Disparar scraping global a las 06:00 y 12:00 (hora Argentina)
  - Prevenir ejecuciones solapadas mediante asyncio.Lock
  - Gestionar reintentos automaticos cada RETRY_INTERVAL_MINUTES
  - Registrar cada ciclo en MongoDB (coleccion scraping_logs)
  - Exponer trigger manual para el Dashboard
  - Ejecutar cadenas en PARALELO con doble semaforo:
      browser_semaphore: cuantos Chromium corren a la vez (pesado)
      page_semaphore:    cuantas paginas de categoria se procesan a la vez (liviano)
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

ARGENTINA_TZ = "America/Argentina/Buenos_Aires"

_scraping_lock = asyncio.Lock()
_cancel_event = asyncio.Event()

# Semaforo de browsers: cuantos Chromium arrancan en paralelo (recurso pesado)
browser_semaphore = asyncio.Semaphore(settings.max_concurrent_browsers)

# Semaforo de paginas: paginas de categoria concurrentes entre todos los browsers
page_semaphore = asyncio.Semaphore(settings.max_concurrent_pages)


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

async def _create_log(execution_id: str, cadenas: list[str]) -> None:
    doc = {
        "execution_id": execution_id,
        "started_at": datetime.now(tz=timezone.utc),
        "cadenas": cadenas,
        "checkpoints": {c: "pending" for c in cadenas},
        "status": "running",
        "finished_at": None,
        "error": None,
    }
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
        {"$set": {"status": status, "finished_at": datetime.now(tz=timezone.utc), "error": error}},
    )
    logger.info(f"[Clock] Ciclo {execution_id} finalizado con estado: {status}")


# ---------------------------------------------------------------------------
# Logica de obtencion de cadenas activas
# ---------------------------------------------------------------------------

async def _get_active_cadenas() -> list[dict[str, Any]]:
    cursor = get_db().comercios_config.find({"activo": True}, {"cadena_id": 1, "url_base": 1})
    return await cursor.to_list(length=None)


# ---------------------------------------------------------------------------
# Ciclo principal de scraping
# ---------------------------------------------------------------------------

async def _run_scraping_cycle(triggered_by: str = "scheduler") -> None:
    if _scraping_lock.locked():
        logger.warning("[Clock] Ciclo anterior aun en ejecucion. Se cancela el nuevo disparo.")
        return

    _cancel_event.clear()

    async with _scraping_lock:
        execution_id = str(uuid4())
        logger.info(f"[Clock] Iniciando ciclo | id={execution_id} | origen={triggered_by}")

        cadenas = await _get_active_cadenas()
        if not cadenas:
            logger.warning("[Clock] No hay cadenas activas en comercios_config.")
            return

        cadena_ids = [c["cadena_id"] for c in cadenas]
        await _create_log(execution_id, cadena_ids)

        # Fase 1: Scraping paralelo de todas las cadenas
        logger.info(
            f"[Clock] Fase 1: scraping paralelo de {len(cadenas)} cadenas "
            f"(max_browsers={settings.max_concurrent_browsers}, max_pages={settings.max_concurrent_pages})"
        )
        results = await asyncio.gather(
            *[_run_with_retries(execution_id, cadena) for cadena in cadenas],
            return_exceptions=True,
        )

        failed: list[str] = []
        for cadena, result in zip(cadenas, results):
            if isinstance(result, Exception) or not result:
                failed.append(cadena["cadena_id"])

        if _cancel_event.is_set():
            await _close_log(execution_id, "cancelled", "Cancelado manualmente.")
            return

        # Fase 2: Promo Engine
        cadenas_ok = [c for c in cadenas if c["cadena_id"] not in failed]
        if cadenas_ok:
            logger.info(f"[Clock] Fase 2: Promo Engine para {len(cadenas_ok)} cadenas")
            await _run_promo_engine_phase(cadenas_ok)

        # Fase 3: Sincronizacion de productos_vigentes
        if not _cancel_event.is_set():
            try:
                from modules.brain.sync import sync_productos_vigentes
                count = await sync_productos_vigentes()
                logger.info(f"[Clock] Fase 3 completa: {count} productos vigentes sincronizados.")
            except Exception as exc:
                logger.error(f"[Clock] Fase 3 (sync) fallo: {exc}")

        # Fase 4: Price Change Tracker
        if not _cancel_event.is_set():
            try:
                from modules.brain.tracker import detectar_variaciones
                alertas = await detectar_variaciones()
                logger.info(f"[Clock] Fase 4 completa: {alertas} variaciones de precio detectadas.")
            except Exception as exc:
                logger.error(f"[Clock] Fase 4 (tracker) fallo: {exc}")

        final_status = "completed" if not failed else "partial"
        error_msg = f"Fallaron: {failed}" if failed else None
        await _close_log(execution_id, final_status, error_msg)
        logger.info(f"[Clock] Ciclo completo. Estado: {final_status}")


async def _run_with_retries(execution_id: str, cadena: dict[str, Any]) -> bool:
    cadena_id = cadena["cadena_id"]
    attempt = 0

    while attempt < settings.max_retries:
        attempt += 1
        logger.info(f"[Clock] -> {cadena_id} | intento {attempt}/{settings.max_retries}")
        try:
            count = await _dispatch_harvester(cadena)
            if count == 0:
                logger.error(f"[Clock] {cadena_id} finalizó con 0 productos.")
                await _update_checkpoint(execution_id, cadena_id, "empty")
                # Un run con 0 productos se considera fallo para el orquestador
                return False
            await _update_checkpoint(execution_id, cadena_id, "ok")
            return True
        except Exception as exc:
            logger.error(f"[Clock] {cadena_id} fallo (intento {attempt}): {exc}")
            await _update_checkpoint(execution_id, cadena_id, f"error_intento_{attempt}")
            if attempt < settings.max_retries:
                wait_secs = settings.retry_interval_minutes * 60
                logger.info(f"[Clock] Reintentando {cadena_id} en {settings.retry_interval_minutes} min...")
                try:
                    await asyncio.wait_for(_cancel_event.wait(), timeout=wait_secs)
                    await _update_checkpoint(execution_id, cadena_id, "cancelled")
                    return False
                except asyncio.TimeoutError:
                    pass

    await _update_checkpoint(execution_id, cadena_id, "failed")
    return False


async def _dispatch_harvester(cadena: dict[str, Any]) -> int:
    from modules.harvester import run_harvester
    async with browser_semaphore:
        return await run_harvester(cadena, semaphore=page_semaphore)


async def _run_promo_engine_phase(cadenas: list[dict[str, Any]]) -> None:
    from modules.promo_engine import run_promo_engine
    results = await asyncio.gather(*[run_promo_engine(c) for c in cadenas], return_exceptions=True)
    for cadena, result in zip(cadenas, results):
        if isinstance(result, Exception):
            logger.error(f"[Clock] PromoEngine fallo para {cadena['cadena_id']}: {result}")
        else:
            logger.info(f"[Clock] PromoEngine {cadena['cadena_id']}: {result} reglas")


# ---------------------------------------------------------------------------
# Scheduler (APScheduler)
# ---------------------------------------------------------------------------

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ARGENTINA_TZ)
    scheduler.add_job(
        _run_scraping_cycle,
        trigger=CronTrigger(hour=settings.schedule_hour_1, minute=0, timezone=ARGENTINA_TZ),
        kwargs={"triggered_by": "scheduler_6am"},
        id="scraping_6am", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _run_scraping_cycle,
        trigger=CronTrigger(hour=settings.schedule_hour_2, minute=0, timezone=ARGENTINA_TZ),
        kwargs={"triggered_by": "scheduler_12pm"},
        id="scraping_12pm", replace_existing=True, max_instances=1,
    )
    return scheduler


# ---------------------------------------------------------------------------
# API publica del modulo
# ---------------------------------------------------------------------------

async def trigger_manual() -> dict[str, str]:
    """Disparo manual desde el Dashboard."""
    if _scraping_lock.locked():
        return {"status": "busy", "message": "Ya hay un ciclo en ejecucion."}
    asyncio.create_task(_run_scraping_cycle(triggered_by="manual"))
    return {"status": "started", "message": "Ciclo manual iniciado."}


async def cancel_scraping() -> dict[str, str]:
    """Cancela el ciclo activo lo antes posible."""
    if not _scraping_lock.locked():
        return {"status": "idle", "message": "No hay ciclo en ejecucion."}
    _cancel_event.set()
    logger.info("[Clock] Cancelacion solicitada por usuario.")
    return {"status": "cancelling", "message": "Cancelacion solicitada. El ciclo se detendra pronto."}


async def get_last_log() -> dict | None:
    """Devuelve el ultimo log de ejecucion."""
    doc = await get_db().scraping_logs.find_one(sort=[("started_at", -1)])
    if doc:
        doc.pop("_id", None)
    return doc

