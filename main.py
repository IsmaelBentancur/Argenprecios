"""
Argenprecios — Punto de entrada principal
Inicia The Clock (orquestador) y la API FastAPI de forma concurrente.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: F401 (Header kept for unused import cleanliness)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from config.settings import settings
from db.client import init_indexes, close_client
from modules.auth import auth_router
from modules.auth.dependencies import require_auth
from modules.clock.scheduler import build_scheduler, trigger_manual, cancel_scraping, get_last_log
from modules.control import router as control_router


# ---------------------------------------------------------------------------
# Logging (Loguru — archivos rotativos)
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
)
logger.add(
    "logs/argenprecios_{time:YYYY-MM-DD}.log",
    rotation="00:00",        # nuevo archivo cada día
    retention="30 days",
    compression="zip",
    level="DEBUG",
    encoding="utf-8",
)


# ---------------------------------------------------------------------------
# FastAPI lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import os
    os.makedirs("logs", exist_ok=True)
    logger.info("=== Argenprecios iniciando ===")
    await init_indexes()

    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        f"[Clock] Programado: "
        f"{settings.schedule_hour_1:02d}:00 y "
        f"{settings.schedule_hour_2:02d}:00 (hora Argentina)"
    )
    logger.info(
        f"[Clock] Concurrencia: {settings.max_concurrent_browsers} navegadores, {settings.max_concurrent_pages} páginas totales"
    )

    yield

    # Shutdown
    logger.info("=== Argenprecios apagando ===")
    scheduler.shutdown(wait=False)
    await close_client()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Argenprecios API",
    version="0.1.0",
    description="Sistema de Inteligencia de Precios en Tiempo Real",
    lifespan=lifespan,
)

# Auth router (must be mounted before control_router)
app.include_router(auth_router)
# Módulo 6: rutas de API y Dashboard
app.include_router(control_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def dashboard():
    """Sirve el Dashboard principal."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    from db.client import get_client
    try:
        await get_client().admin.command("ping")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"
    return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status, "version": "0.1.0"}


@app.post("/clock/trigger", dependencies=[Depends(require_auth)])
async def manual_trigger():
    """Dispara un ciclo de scraping inmediatamente (uso desde Dashboard)."""
    result = await trigger_manual()
    return result


@app.post("/clock/cancel", dependencies=[Depends(require_auth)])
async def cancel_trigger():
    """Cancela el ciclo de scraping activo."""
    return await cancel_scraping()


@app.get("/clock/last-log")
async def last_log():
    """Devuelve el último registro de ejecución del orquestador."""
    log = await get_last_log()
    if not log:
        return {"message": "Sin ejecuciones registradas aún."}
    return log


@app.get("/clock/status")
async def clock_status():
    """Estado actual del scheduler."""
    scheduler = app.state.scheduler
    jobs = [
        {
            "id": job.id,
            "next_run": str(job.next_run_time),
        }
        for job in scheduler.get_jobs()
    ]
    return {"jobs": jobs}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )

