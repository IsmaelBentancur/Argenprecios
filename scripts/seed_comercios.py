"""
Script de seed para la colección comercios_config.
Ejecutar una sola vez para inicializar las cadenas en MongoDB.

Uso:
  cd C:\Users\Isma\Downloads\argenprecios
  python scripts/seed_comercios.py

Por defecto solo COTO y CARREFOUR quedan activos.
Para activar una cadena VTEX en staging, ejecutar en MongoDB:
  db.comercios_config.updateOne({cadena_id: "JUMBO"}, {$set: {activo: true}})
"""

import asyncio
from datetime import datetime, timezone

from db.client import get_db


# Cadenas activas en producción
_PRODUCCION = {"COTO", "CARREFOUR"}

_CADENAS = [
    # --- Producción ---
    {"cadena_id": "COTO",      "nombre": "Coto Digital",   "url_base": "https://www.cotodigital.com.ar"},
    {"cadena_id": "CARREFOUR", "nombre": "Carrefour",      "url_base": "https://www.carrefour.com.ar"},
    # --- Staging VTEX ---
    {"cadena_id": "JUMBO",     "nombre": "Jumbo",          "url_base": "https://www.jumbo.com.ar"},
    {"cadena_id": "DISCO",     "nombre": "Disco",          "url_base": "https://www.disco.com.ar"},
    {"cadena_id": "VEA",       "nombre": "Vea",            "url_base": "https://www.vea.com.ar"},
    {"cadena_id": "DIA",       "nombre": "Día%",           "url_base": "https://diaonline.com.ar"},
    {"cadena_id": "CHANGOMAS", "nombre": "ChangoMas",      "url_base": "https://www.masonline.com.ar"},
    {"cadena_id": "FARMACITY", "nombre": "Farmacity",      "url_base": "https://www.farmacity.com"},
    {"cadena_id": "JOSIMAR",   "nombre": "Josimar",        "url_base": "https://www.josimar.com.ar"},
    {"cadena_id": "LIBERTAD",  "nombre": "Libertad",       "url_base": "https://www.hiperlibertad.com.ar"},
    {"cadena_id": "TOLEDO",    "nombre": "Toledo Digital", "url_base": "https://www.toledodigital.com.ar"},
    {"cadena_id": "ELNENE",    "nombre": "El Nene",        "url_base": "https://www.supermercadoselnene.com.ar"},
    {"cadena_id": "CORDIEZ",   "nombre": "Cordiez",        "url_base": "https://www.cordiez.com.ar"},
]


async def seed():
    db = get_db()
    now = datetime.now(tz=timezone.utc)
    seeded = 0

    for cadena in _CADENAS:
        doc = {
            **cadena,
            "activo": cadena["cadena_id"] in _PRODUCCION,
            "creado_en": now,
        }
        result = await db.comercios_config.update_one(
            {"cadena_id": cadena["cadena_id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if result.upserted_id:
            print(f"  ✓ Insertado: {cadena['cadena_id']} (activo={doc['activo']})")
            seeded += 1
        else:
            print(f"  · Ya existe: {cadena['cadena_id']}")

    print(f"\nSeed completo: {seeded} nuevas cadenas insertadas.")
    print(f"Activas: {[c['cadena_id'] for c in _CADENAS if c['cadena_id'] in _PRODUCCION]}")
    print(f"Staging: {[c['cadena_id'] for c in _CADENAS if c['cadena_id'] not in _PRODUCCION]}")


if __name__ == "__main__":
    asyncio.run(seed())
