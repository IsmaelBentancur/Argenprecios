# -*- coding: utf-8 -*-
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid
from loguru import logger
from config.settings import settings


_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5000,
            socketTimeoutMS=30000,
            connectTimeoutMS=10000,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_indexes() -> None:
    db = get_db()

    # scraping_logs: execution_id es la clave de busqueda en cada checkpoint/close
    await db.scraping_logs.create_indexes([
        IndexModel([("execution_id", ASCENDING)], unique=True),  # update_one por ciclo
        IndexModel([("started_at", DESCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    # historial_precios: TTL + query indexes
    ttl_seconds = settings.ttl_days * 86400
    await db.historial_precios.create_indexes([
        IndexModel([("captured_at", DESCENDING)], expireAfterSeconds=ttl_seconds),        
        IndexModel([("bucket_id", ASCENDING)], unique=True),          # upsert lookup - critico
        IndexModel([("ean", ASCENDING), ("cadena_id", ASCENDING)]),   # comparar_ean      
        IndexModel([("updated_at", DESCENDING)]),                     # sort en agregaciones
        IndexModel([("semana", ASCENDING)]),                          # bucketing pattern 
        IndexModel([("nombre", "text")]),                             # busqueda por nombre
    ])

    # reglas_descuento: indexes para upsert por clave única
    await db.reglas_descuento.create_indexes([
        IndexModel([("cadena_id", ASCENDING), ("tipo", ASCENDING)]),
        IndexModel([("cadena_id", ASCENDING), ("banco", ASCENDING)]),
        IndexModel([("cadena_id", ASCENDING), ("programa_fidelidad", ASCENDING)]),
        IndexModel([("cadena_id", ASCENDING), ("ean", ASCENDING)]),  # filtro compuesto frecuente
        IndexModel([("ean", ASCENDING)]),
    ])

    # coto_mappings: EAN interno → GTIN real (lookup en sync y enricher)
    await db.coto_mappings.create_indexes([
        IndexModel([("ean_interno", ASCENDING)], unique=True),
        IndexModel([("gtin", ASCENDING)]),
    ])

    # productos_vigentes: colección pre-agregada para frontend O(1)
    await db.productos_vigentes.create_indexes([
        IndexModel([("ean", ASCENDING)], unique=True),
        IndexModel([("nombre", "text")]),
        IndexModel([("mejor_cadena", ASCENDING)]),
        IndexModel([("ultima_actualizacion", DESCENDING)]),  # pruning query en sync.py
    ])

    # price_alerts: variaciones de precio entre ciclos
    await db.price_alerts.create_indexes([
        IndexModel([("ean", ASCENDING), ("cadena_id", ASCENDING), ("ciclo_ts", DESCENDING)], unique=True),
        IndexModel([("tipo", ASCENDING)]),
        IndexModel([("detectado_en", DESCENDING)]),
        IndexModel([("variacion_pct", ASCENDING)]),
    ])

    # comercios_config: simple lookup
    await db.comercios_config.create_indexes([
        IndexModel([("cadena_id", ASCENDING)], unique=True),
        IndexModel([("activo", ASCENDING)]),
    ])

    logger.info("MongoDB indexes initialized")


async def close_client() -> None:
    global _client
    if _client:
        _client.close()
        _client = None

