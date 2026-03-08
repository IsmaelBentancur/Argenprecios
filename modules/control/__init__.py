"""
Módulo 6 — The Control
Rutas FastAPI para el Dashboard y la API de consumo.
Se montan sobre la app principal en main.py.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from config.settings import settings


async def _require_api_key(x_api_key: str = Header(default="")) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")

from db.client import get_db
from modules.brain.calculator import comparar_ean, buscar_productos

router = APIRouter(prefix="/api", tags=["argenprecios"])


# ---------------------------------------------------------------------------
# Modelos de request/response
# ---------------------------------------------------------------------------

class WalletConfig(BaseModel):
    tarjetas: list[str] = []
    programas_fidelidad: list[str] = []


# ---------------------------------------------------------------------------
# Wallet del usuario (billetera virtual)
# ---------------------------------------------------------------------------

@router.get("/wallet")
async def get_wallet():
    """Devuelve la configuración actual de tarjetas del usuario."""
    doc = await get_db().config_usuario.find_one({"_id": "wallet"})
    if not doc:
        return WalletConfig()
    return {"tarjetas": doc.get("tarjetas", []), "programas_fidelidad": doc.get("programas_fidelidad", [])}


@router.post("/wallet", dependencies=[Depends(_require_api_key)])
async def save_wallet(config: WalletConfig):
    """Guarda la billetera del usuario (tarjetas y programas de fidelidad)."""
    await get_db().config_usuario.update_one(
        {"_id": "wallet"},
        {"$set": {"tarjetas": config.tarjetas, "programas_fidelidad": config.programas_fidelidad}},
        upsert=True,
    )
    return {"status": "ok", "saved": config.model_dump()}


# ---------------------------------------------------------------------------
# Productos y comparativa
# ---------------------------------------------------------------------------

@router.get("/productos")
async def get_productos(
    q: str = Query(default="", description="Búsqueda por nombre"),
    cadena: str = Query(default="", description="Filtrar por cadena (COTO, CARREFOUR)"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Lista de productos con comparativa de precios entre cadenas."""
    wallet = await get_db().config_usuario.find_one({"_id": "wallet"})
    tarjetas = wallet.get("tarjetas", []) if wallet else []
    programas = wallet.get("programas_fidelidad", []) if wallet else []

    result = await buscar_productos(
        q=q,
        cadena_id=cadena or None,
        page=page,
        limit=limit,
        tarjetas_usuario=tarjetas or None,
        programas_usuario=programas or None,
    )
    return result


@router.get("/comparar/{ean}")
async def comparar(ean: str):
    """Comparativa completa de un EAN entre todas las cadenas con descuentos del usuario."""
    if not (len(ean) in (8, 13) and ean.isdigit()):
        raise HTTPException(status_code=400, detail="EAN inválido. Debe ser de 8 o 13 dígitos.")

    wallet = await get_db().config_usuario.find_one({"_id": "wallet"})
    tarjetas = wallet.get("tarjetas", []) if wallet else []
    programas = wallet.get("programas_fidelidad", []) if wallet else []

    resultado = await comparar_ean(
        ean,
        tarjetas_usuario=tarjetas or None,
        programas_usuario=programas or None,
    )
    if not resultado:
        raise HTTPException(status_code=404, detail=f"EAN {ean} no encontrado.")

    return {
        "ean": resultado.ean,
        "nombre": resultado.nombre,
        "mejor_cadena": resultado.mejor_cadena,
        "mejor_precio_neto": resultado.mejor_precio_neto,
        "capturado_en": resultado.capturado_en,
        "cadenas": [
            {
                "cadena_id": c.cadena_id,
                "precio_lista": c.precio_lista,
                "precio_oferta": c.precio_oferta,
                "precio_neto": c.precio_neto,
                "precio_por_unidad": c.precio_por_unidad,
                "unidad_medida": c.unidad_medida,
                "ahorro_pct": c.ahorro_pct,
                "reglas_aplicadas": c.reglas_aplicadas,
            }
            for c in resultado.cadenas
        ],
    }


@router.get("/cadenas")
async def get_cadenas():
    """Lista de cadenas configuradas."""
    docs = await get_db().comercios_config.find({}, {"_id": 0}).to_list(length=None)
    return docs



@router.get("/stats")
async def get_stats():
    """Estadísticas rápidas del sistema para el Dashboard."""
    db = get_db()
    total_productos = await db.historial_precios.estimated_document_count()
    total_reglas = await db.reglas_descuento.estimated_document_count()
    ultimo_ciclo = await db.scraping_logs.find_one(sort=[("started_at", -1)])
    return {
        "total_productos": total_productos,
        "total_reglas_descuento": total_reglas,
        "ultimo_ciclo": {
            "estado": ultimo_ciclo.get("status") if ultimo_ciclo else None,
            "iniciado": str(ultimo_ciclo.get("started_at")) if ultimo_ciclo else None,
        },
    }
