"""
Módulo 6 — The Control
Rutas FastAPI para el Dashboard y la API de consumo.
Se montan sobre la app principal en main.py.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from modules.auth.dependencies import require_auth
from db.client import get_db
from modules.brain.calculator import comparar_ean, buscar_productos, obtener_historial_ean

router = APIRouter(prefix="/api", tags=["argenprecios"])


# ---------------------------------------------------------------------------
# Modelos de request/response
# ---------------------------------------------------------------------------

class WalletConfig(BaseModel):
    tarjetas: list[str] = []
    programas_fidelidad: list[str] = []


FEEDBACK_TIPOS = {"bug", "sugerencia", "otro"}

class FeedbackInput(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=1000)
    tipo: str = Field(default="otro")

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v: str) -> str:
        if v not in FEEDBACK_TIPOS:
            raise ValueError(f"tipo debe ser uno de: {', '.join(sorted(FEEDBACK_TIPOS))}")
        return v


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Inicializacion consolidada
# ---------------------------------------------------------------------------

@router.get("/init")
async def get_init():
    """Consolidado de inicio para el Dashboard (evita múltiples round-trips)."""
    db = get_db()
    cadenas = await db.comercios_config.find({"activo": True}, {"_id": 0}).to_list(length=None)
    wallet_doc = await db.config_usuario.find_one({"_id": "wallet"})
    wallet = {
        "tarjetas": wallet_doc.get("tarjetas", []) if wallet_doc else [],
        "programas_fidelidad": wallet_doc.get("programas_fidelidad", []) if wallet_doc else []
    }
    total_productos = await db.historial_precios.estimated_document_count()
    total_reglas = await db.reglas_descuento.estimated_document_count()
    ultimo_ciclo_doc = await db.scraping_logs.find_one(sort=[("started_at", -1)])
    
    metadata = {
        "tarjetas": [
            {"id": "Visa", "label": "Visa"}, {"id": "Mastercard", "label": "Mastercard"},
            {"id": "Amex", "label": "American Express"}, {"id": "Débito", "label": "Débito"},
            {"id": "Cuenta DNI", "label": "Cuenta DNI"}, {"id": "MODO", "label": "MODO"},
            {"id": "BUEPP", "label": "BUEPP"}, {"id": "Naranja", "label": "Naranja X"},
            {"id": "Mercado Pago", "label": "Mercado Pago"}, {"id": "Ualá", "label": "Ualá"},
            {"id": "Personal Pay", "label": "Personal Pay"}, {"id": "ANSES", "label": "ANSES"},
            {"id": "Jubilados", "label": "Jubilados"}
        ],
        "fidelidad": {
            "COTO": [{"id": "Comunidad Coto", "label": "Comunidad Coto"}],
            "JUMBO": [{"id": "Jumbo+", "label": "Jumbo+"}],
            "DISCO": [{"id": "Disco+", "label": "Disco+"}],
            "VEA": [{"id": "Vea Más", "label": "Vea Más"}],
            "DIA": [{"id": "Club Dia", "label": "Club Dia"}],
            "CHANGOMAS": [{"id": "Mas Online", "label": "Mas Online"}],
            "GLOBAL": [{"id": "Club La Nación", "label": "Club La Nación"}, {"id": "Clarín 365", "label": "Clarín 365"}]
        }
    }
    
    return {
        "cadenas": cadenas,
        "wallet": wallet,
        "stats": {
            "total_productos": total_productos,
            "total_reglas_descuento": total_reglas,
            "ultimo_ciclo": {
                "estado": ultimo_ciclo_doc.get("status") if ultimo_ciclo_doc else None,
                "iniciado": str(ultimo_ciclo_doc.get("started_at")) if ultimo_ciclo_doc else None,
            }
        },
        "metadata": metadata
    }


# Wallet del usuario (billetera virtual)
# ---------------------------------------------------------------------------

@router.get("/wallet")
async def get_wallet():
    """Devuelve la configuración actual de tarjetas del usuario."""
    doc = await get_db().config_usuario.find_one({"_id": "wallet"})
    if not doc:
        return WalletConfig()
    return {"tarjetas": doc.get("tarjetas", []), "programas_fidelidad": doc.get("programas_fidelidad", [])}


@router.post("/wallet", dependencies=[Depends(require_auth)])
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
    cadena: str = Query(default="", description="Filtrar por cadena (ej: COTO, JUMBO)"),
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


@router.post("/feedback")
async def submit_feedback(body: FeedbackInput):
    """Recibe feedback del usuario y lo almacena en la colección 'feedback'."""
    doc = {
        "mensaje": body.mensaje,
        "tipo": body.tipo,
        "capturado_en": datetime.now(tz=timezone.utc),
    }
    await get_db().feedback.insert_one(doc)
    return {"status": "ok"}


@router.get("/cadenas")
async def get_cadenas():
    """Lista de cadenas configuradas."""
    docs = await get_db().comercios_config.find({}, {"_id": 0}).to_list(length=None)
    return docs



@router.get("/alertas")
async def get_alertas(
    tipo: str = Query(default="", description="'baja' o 'suba'"),
    cadena: str = Query(default="", description="Filtrar por cadena"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Variaciones de precio detectadas en el ultimo ciclo."""
    db = get_db()
    filtro: dict = {}
    if tipo in ("baja", "suba"):
        filtro["tipo"] = tipo
    if cadena:
        filtro["cadena_id"] = cadena.upper()

    docs = await db.price_alerts.find(filtro, {"_id": 0}).sort(
        "variacion_pct", 1
    ).limit(limit).to_list(length=None)
    return {"total": len(docs), "items": docs}


@router.get("/historial/{ean}")
async def get_historial(ean: str):
    if not (len(ean) in (8, 13) and ean.isdigit()):
        raise HTTPException(status_code=400, detail="EAN inválido.")
    resultado = await obtener_historial_ean(ean)
    if not resultado:
        raise HTTPException(status_code=404, detail="No hay historial para este EAN.")
    return resultado

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



