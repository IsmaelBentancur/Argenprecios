"""
Inicializacion minima de Argenprecios.

Configura las cadenas en comercios_config.
Ejecutar una vez al levantar el proyecto:
    python scripts/seed_demo.py
"""

import asyncio
import motor.motor_asyncio

MONGO_URI = "mongodb://localhost:27017"
MONGO_DB  = "argenprecios"

CADENAS = [
    {"cadena_id": "COTO", "nombre": "Coto CICSA", "url_base": "https://www.cotodigital.com.ar", "activo": True, "adaptador": "coto", "prioridad": 1},
]


async def init():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    try:
        await client.admin.command("ping")
        print("Conectado a MongoDB")
    except Exception as e:
        print(f"Error conectando a MongoDB: {e}")
        return
    for cadena in CADENAS:
        await db.comercios_config.update_one({"cadena_id": cadena["cadena_id"]}, {"$set": cadena}, upsert=True)
        print(f"  {cadena['cadena_id']} configurado")
    print("Listo.")
    client.close()


if __name__ == "__main__":
    asyncio.run(init())
