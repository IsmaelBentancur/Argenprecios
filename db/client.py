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
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_indexes() -> None:
    db = get_db()

    # scraping_logs: index by execution time
    await db.scraping_logs.create_indexes([
        IndexModel([("started_at", DESCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("cadena_id", ASCENDING)]),
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

    # reglas_descuento: removido por solicitud del usuario (verificacion de datos)
    # await db.reglas_descuento.create_indexes([...])

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