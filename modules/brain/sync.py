# -*- coding: utf-8 -*-
"""
Modulo 4: The Brain - Sincronizacion
Job de agregacion para popular la coleccion productos_vigentes.
"""

import asyncio
from loguru import logger
from db.client import get_db


async def sync_productos_vigentes():
    """
    Job de agregacion post-ciclo para popular productos_vigentes.
    - Resuelve EANs internos de Coto via coto_mappings (lookup transparente).
    - Calcula mejor_precio y mejor_cadena (solo cadenas con stock).
    - Resultado: O(1) para el frontend en lugar de aggregation pesada.
    """
    db = get_db()
    logger.info("[Brain] Iniciando sincronizacion de productos_vigentes...")

    pipeline = [
        # 1. Resolver EANs internos de Coto -> GTIN real via coto_mappings.
        #    Si coto_mappings esta vacia, ean_efectivo == ean original (sin efecto).
        {
            "$lookup": {
                "from": "coto_mappings",
                "localField": "ean",
                "foreignField": "ean_interno",
                "as": "mapping",
            }
        },
        {
            "$addFields": {
                "ean_efectivo": {
                    "$cond": [
                        {"$gt": [{"$size": "$mapping"}, 0]},
                        {"$ifNull": [{"$arrayElemAt": ["$mapping.gtin", 0]}, "$ean"]},
                        "$ean",
                    ]
                }
            }
        },
        # 2. Tomar el registro mas reciente por (ean_efectivo, cadena_id)
        {"$sort": {"ean_efectivo": 1, "cadena_id": 1, "updated_at": -1}},
        {
            "$group": {
                "_id": {"ean": "$ean_efectivo", "cadena_id": "$cadena_id"},
                "nombre": {"$first": "$nombre"},
                "precio_lista": {"$first": "$ultimo_precio_lista"},
                "precio_oferta": {"$first": "$ultimo_precio_oferta"},
                "stock": {"$first": "$stock_disponible"},
                "url": {"$first": "$url_origen"},
                "updated_at": {"$first": "$updated_at"},
                "precio_por_unidad": {"$first": "$precio_por_unidad"},
                "unidad_medida": {"$first": "$unidad_medida"},
            }
        },
        # 3. Consolidar todas las cadenas bajo el mismo EAN efectivo
        {
            "$group": {
                "_id": "$_id.ean",
                "ean": {"$first": "$_id.ean"},
                "nombre": {"$first": "$nombre"},
                "ultima_actualizacion": {"$max": "$updated_at"},
                "cadenas_list": {
                    "$push": {
                        "k": "$_id.cadena_id",
                        "v": {
                            "p_lista": "$precio_lista",
                            "p_oferta": "$precio_oferta",
                            "stock": "$stock",
                            "url": "$url",
                            "updated_at": "$updated_at",
                            "p_unit": "$precio_por_unidad",
                            "u_med": "$unidad_medida",
                        },
                    }
                },
            }
        },
        # 4. Calcular mejor precio/cadena (solo cadenas con stock disponible)
        {
            "$addFields": {
                "cadenas": {"$arrayToObject": "$cadenas_list"},
                "mejor_item": {
                    "$reduce": {
                        "input": {
                            "$filter": {
                                "input": "$cadenas_list",
                                "as": "c",
                                "cond": {"$eq": ["$$c.v.stock", True]},
                            }
                        },
                        "initialValue": None,
                        "in": {
                            "$let": {
                                "vars": {
                                    "p_this": {"$ifNull": ["$$this.v.p_oferta", "$$this.v.p_lista"]},
                                    "p_val": {"$ifNull": ["$$value.v.p_oferta", "$$value.v.p_lista"]},
                                },
                                "in": {
                                    "$cond": [
                                        {"$eq": ["$$value", None]},
                                        "$$this",
                                        {"$cond": [{"$lt": ["$$p_this", "$$p_val"]}, "$$this", "$$value"]},
                                    ]
                                },
                            }
                        },
                    }
                },
            }
        },
        # 5. Extraer campos finales y limpiar temporales
        {
            "$addFields": {
                "mejor_precio": {"$ifNull": ["$mejor_item.v.p_oferta", "$mejor_item.v.p_lista"]},
                "mejor_cadena": "$mejor_item.k",
            }
        },
        {"$project": {"cadenas_list": 0, "mejor_item": 0, "mapping": 0}},
        # 6. Reemplazar coleccion destino
        {"$out": "productos_vigentes"},
    ]

    try:
        await db.historial_precios.aggregate(pipeline).to_list(length=None)

        # Asegurar indices para busqueda del frontend
        await db.productos_vigentes.create_index([("ean", 1)], unique=True)
        await db.productos_vigentes.create_index([("nombre", "text")])

        count = await db.productos_vigentes.estimated_document_count()
        logger.info(f"[Brain] Sincronizacion exitosa. {count} productos vigentes.")
        return count
    except Exception as e:
        logger.error(f"[Brain] Error en sincronizacion: {e}")
        return 0


if __name__ == "__main__":
    async def main():
        await sync_productos_vigentes()
    asyncio.run(main())
