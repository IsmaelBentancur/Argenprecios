# -*- coding: utf-8 -*-
"""
Script de seed para la coleccion comercios_config.
Ejecutar una sola vez (o para sincronizar) las cadenas en MongoDB.

Uso:
  cd C:\\Users\\Isma\\Downloads\\argenprecios
  python scripts/seed_comercios.py

Lista aprobada (2026-03-09): Coto, Dia, Jumbo, Disco, Vea, MasOnline,
La Anonima, Cooperativa Obrera, Josimar, Toledo, Cordiez, Hipermercado Libertad
"""

import asyncio
from datetime import datetime, timezone

from db.client import get_db


_CADENAS = [
    {"cadena_id": "COTO",      "nombre": "Coto Digital",           "url_base": "https://www.cotodigital.com.ar"},
    {"cadena_id": "JUMBO",     "nombre": "Jumbo",                  "url_base": "https://www.jumbo.com.ar"},
    {"cadena_id": "DISCO",     "nombre": "Disco",                  "url_base": "https://www.disco.com.ar"},
    {"cadena_id": "VEA",       "nombre": "Vea",                    "url_base": "https://www.vea.com.ar"},
    {"cadena_id": "DIA",       "nombre": "Dia",                    "url_base": "https://diaonline.supermercadosdia.com.ar"},
    {"cadena_id": "CHANGOMAS", "nombre": "MasOnline",              "url_base": "https://www.masonline.com.ar"},
    {"cadena_id": "JOSIMAR",   "nombre": "Josimar",                "url_base": "https://www.josimar.com.ar"},
    {"cadena_id": "LIBERTAD",  "nombre": "Hipermercado Libertad",  "url_base": "https://www.hiperlibertad.com.ar"},
    {"cadena_id": "TOLEDO",    "nombre": "Toledo Digital",         "url_base": "https://www.toledodigital.com.ar"},
    {"cadena_id": "CORDIEZ",   "nombre": "Cordiez",                "url_base": "https://www.cordiez.com.ar"},
    {"cadena_id": "LACOOPE",   "nombre": "Cooperativa Obrera",     "url_base": "https://www.lacoopeencasa.coop"},
    {"cadena_id": "LAANONIMA", "nombre": "La Anonima",             "url_base": "https://www.laanonimaonline.com"},
]

# Cadenas a desactivar/eliminar si existen en DB
_CADENAS_OBSOLETAS = ["FARMACITY", "ELNENE", "SUPERMAMI", "ALMACOR"]


async def seed():
    db = get_db()
    now = datetime.now(tz=timezone.utc)
    seeded = 0

    # Insertar/actualizar cadenas activas
    for cadena in _CADENAS:
        doc = {**cadena, "activo": True, "creado_en": now}
        result = await db.comercios_config.update_one(
            {"cadena_id": cadena["cadena_id"]},
            {"$set": doc},
            upsert=True,
        )
        if result.upserted_id:
            print(f"  OK Insertado: {cadena['cadena_id']}")
            seeded += 1
        else:
            print(f"  - Actualizado: {cadena['cadena_id']}")

    # Eliminar cadenas obsoletas
    for cadena_id in _CADENAS_OBSOLETAS:
        result = await db.comercios_config.delete_one({"cadena_id": cadena_id})
        if result.deleted_count:
            print(f"  X Eliminado: {cadena_id}")

    print(f"\nSeed completo: {seeded} nuevas cadenas insertadas.")
    print(f"Activas: {[c['cadena_id'] for c in _CADENAS]}")


if __name__ == "__main__":
    asyncio.run(seed())
