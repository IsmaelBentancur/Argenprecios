# -*- coding: utf-8 -*-
"""
Modulo 4 - The Brain
Price Change Tracker: detecta variaciones de precio entre ciclos de scraping.
Se ejecuta en Fase 3 del scheduler, despues de sync_productos_vigentes().
"""

from datetime import datetime, timezone

from loguru import logger

from db.client import get_db

# Umbral minimo de variacion para registrar (evita ruido por centavos)
_MIN_VARIACION_PCT = 1.0

# Maximas alertas a generar por ciclo (evita flood en DB)
_MAX_ALERTAS_POR_CICLO = 500


async def detectar_variaciones() -> int:
    """
    Compara el penultimo y ultimo precio de cada bucket activo.
    Persiste variaciones significativas en la coleccion price_alerts.
    Retorna la cantidad de variaciones detectadas.
    """
    db = get_db()
    now = datetime.now(tz=timezone.utc)

    # Buscar buckets con al menos 2 capturas
    pipeline = [
        {"$match": {"capturas.1": {"$exists": True}}},  # al menos 2 elementos
        {"$project": {
            "ean": 1,
            "cadena_id": 1,
            "nombre": 1,
            "precio_actual": {"$arrayElemAt": ["$capturas", -1]},
            "precio_anterior": {"$arrayElemAt": ["$capturas", -2]},
        }},
        {"$project": {
            "ean": 1,
            "cadena_id": 1,
            "nombre": 1,
            "precio_actual": "$precio_actual.precio_lista",
            "precio_anterior": "$precio_anterior.precio_lista",
            "ts_actual": "$precio_actual.ts",
        }},
        {"$match": {
            "precio_anterior": {"$gt": 0},
            "precio_actual": {"$gt": 0},
        }},
        {"$project": {
            "ean": 1,
            "cadena_id": 1,
            "nombre": 1,
            "precio_actual": 1,
            "precio_anterior": 1,
            "ts_actual": 1,
            "variacion_pct": {
                "$multiply": [
                    {"$divide": [
                        {"$subtract": ["$precio_actual", "$precio_anterior"]},
                        "$precio_anterior"
                    ]},
                    100
                ]
            }
        }},
        {"$match": {
            "$or": [
                {"variacion_pct": {"$lte": -_MIN_VARIACION_PCT}},
                {"variacion_pct": {"$gte": _MIN_VARIACION_PCT}},
            ]
        }},
        {"$sort": {"variacion_pct": 1}},  # bajas primero
        {"$limit": _MAX_ALERTAS_POR_CICLO},
    ]

    docs = await db.historial_precios.aggregate(pipeline).to_list(length=None)

    if not docs:
        logger.info("[Tracker] Sin variaciones de precio detectadas.")
        return 0

    from pymongo import UpdateOne
    ops = []
    for d in docs:
        variacion_pct = round(d["variacion_pct"], 2)
        key = {"ean": d["ean"], "cadena_id": d["cadena_id"], "ciclo_ts": d.get("ts_actual")}
        ops.append(UpdateOne(
            key,
            {"$set": {
                "ean": d["ean"],
                "cadena_id": d["cadena_id"],
                "nombre": d["nombre"],
                "precio_anterior": d["precio_anterior"],
                "precio_actual": d["precio_actual"],
                "variacion_pct": variacion_pct,
                "tipo": "baja" if variacion_pct < 0 else "suba",
                "detectado_en": now,
                "ciclo_ts": d.get("ts_actual"),
            }},
            upsert=True,
        ))

    result = await db.price_alerts.bulk_write(ops, ordered=False)
    total = (result.upserted_count or 0) + (result.modified_count or 0)

    bajas = sum(1 for d in docs if d["variacion_pct"] < 0)
    subas = len(docs) - bajas
    logger.info(f"[Tracker] {total} variaciones guardadas — {bajas} bajas, {subas} subas.")
    return total
