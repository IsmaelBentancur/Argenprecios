"""
Módulo 4 — The Brain
Inteligencia de precios: cruza historial de precios con reglas del Promo Engine
y el perfil de tarjetas del usuario para calcular el mejor precio neto final.
"""

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from db.client import get_db
from modules.promo_engine.parser import calcular_precio_neto


@dataclass
class PrecioCadena:
    cadena_id: str
    precio_lista: float
    precio_oferta: float | None
    precio_neto: float               # mejor precio tras aplicar descuentos del usuario
    precio_por_unidad: float | None  # ARS/kg, ARS/L, etc.
    unidad_medida: str | None
    ahorro_pct: float                # % de ahorro vs precio_lista
    reglas_aplicadas: list[str]      # descripción de reglas usadas


@dataclass
class ComparativaEAN:
    ean: str
    nombre: str
    cadenas: list[PrecioCadena]
    mejor_cadena: str
    mejor_precio_neto: float
    capturado_en: datetime | None


async def _resolve_ean(ean: str, db) -> str:
    """
    Si el EAN es un ID interno de Coto, lo resuelve al GTIN real usando coto_mappings.
    Retorna el GTIN real si existe mapeo, o el EAN original si no.
    La resolución es transparente: el historial almacenado no se modifica.
    """
    from modules.harvester.ean_utils import is_internal_coto_id
    if is_internal_coto_id(ean):
        mapping = await db.coto_mappings.find_one({"ean_interno": ean, "gtin": {"$ne": None}})
        if mapping and mapping.get("gtin"):
            return mapping["gtin"]
    return ean


async def comparar_ean(
    ean: str,
    tarjetas_usuario: list[str] | None = None,
    programas_usuario: list[str] | None = None,
) -> ComparativaEAN | None:
    """
    Devuelve la comparativa completa de un EAN entre todas las cadenas,
    aplicando los descuentos del perfil del usuario.
    Resuelve EANs internos de Coto al GTIN real antes de buscar.
    """
    db = get_db()

    # Resolver EAN interno → GTIN real (transparente, no altera el historial)
    ean = await _resolve_ean(ean, db)

    # Obtener último precio por cadena (documento más reciente del bucket)
    pipeline = [
        {"$match": {"ean": ean}},
        {"$sort": {"updated_at": -1}},
        {
            "$group": {
                "_id": "$cadena_id",
                "cadena_id": {"$first": "$cadena_id"},
                "nombre": {"$first": "$nombre"},
                "ultimo_precio_lista": {"$first": "$ultimo_precio_lista"},
                "ultimo_precio_oferta": {"$first": "$ultimo_precio_oferta"},
                "precio_por_unidad": {"$first": "$precio_por_unidad"},
                "unidad_medida": {"$first": "$unidad_medida"},
                "updated_at": {"$first": "$updated_at"},
            }
        },
    ]
    docs = await db.historial_precios.aggregate(pipeline).to_list(length=None)

    if not docs:
        return None

    nombre = docs[0].get("nombre", "")
    capturado_en = docs[0].get("updated_at")

    # Obtener reglas de descuento vigentes para el EAN
    reglas_cursor = db.reglas_descuento.find({
        "$or": [{"ean": ean}, {"ean": None}],
    })
    reglas_raw = await reglas_cursor.to_list(length=None)
    reglas = _hydrate_reglas(reglas_raw)

    cadenas: list[PrecioCadena] = []

    for doc in docs:
        cadena_id = doc["cadena_id"]
        precio_lista = float(doc.get("ultimo_precio_lista") or 0)
        precio_oferta = doc.get("ultimo_precio_oferta")
        if precio_oferta:
            precio_oferta = float(precio_oferta)

        # FIX 93.7% BUG: Si tenemos precio de oferta capturado del scraper, 
        # y precio_lista es absurdo (> 5x precio_oferta), ignoramos el precio_lista SEPA.
        # En scraping puro, precio_lista y precio_oferta vienen de la misma fuente.
        if precio_oferta and precio_lista > precio_oferta * 5:
            logger.warning(f"Precio lista sospechoso ({precio_lista}) para EAN {ean} en {cadena_id}. Usando precio_oferta como base.")
            precio_lista = precio_oferta

        # Filtrar reglas de esta cadena
        reglas_cadena = [r for r in reglas if r.cadena_id == cadena_id]

        # Precio de partida: oferta si existe, sino lista
        precio_base = precio_oferta if precio_oferta else precio_lista

        precio_neto = calcular_precio_neto(
            precio_base,
            reglas_cadena,
            tarjetas_usuario=tarjetas_usuario,
            programas_usuario=programas_usuario,
        )

        ahorro_pct = round((1 - precio_neto / precio_lista) * 100, 1) if precio_lista > 0 else 0
        reglas_desc = [
            f"{r.tipo.value}: {r.descuento_pct}% ({r.banco or r.programa_fidelidad or ''})"
            for r in reglas_cadena
            if r.descuento_pct and _regla_aplica(r, tarjetas_usuario, programas_usuario)  
        ]

        cadenas.append(PrecioCadena(
            cadena_id=cadena_id,
            precio_lista=precio_lista,
            precio_oferta=precio_oferta,
            precio_neto=precio_neto,
            precio_por_unidad=doc.get("precio_por_unidad"),
            unidad_medida=doc.get("unidad_medida"),
            ahorro_pct=ahorro_pct,
            reglas_aplicadas=reglas_desc,
        ))

    if not cadenas:
        return None

    mejor = min(cadenas, key=lambda c: c.precio_neto)
    return ComparativaEAN(
        ean=ean,
        nombre=nombre,
        cadenas=cadenas,
        mejor_cadena=mejor.cadena_id,
        mejor_precio_neto=mejor.precio_neto,
        capturado_en=capturado_en,
    )


async def buscar_productos(
    q: str = "",
    cadena_id: str | None = None,
    page: int = 1,
    limit: int = 20,
    tarjetas_usuario: list[str] | None = None,
    programas_usuario: list[str] | None = None,
) -> dict:
    """
    Búsqueda paginada de productos con precio neto calculado.
    Usa productos_vigentes (pre-agregada) para O(1). Si está vacía, devuelve vacío
    hasta el próximo ciclo de scraping.
    """
    db = get_db()
    skip = (page - 1) * limit

    # Filtro sobre productos_vigentes
    match: dict = {}
    if q:
        match["$text"] = {"$search": q}
    if cadena_id:
        # Cadena presente como clave del mapa
        match[f"cadenas.{cadena_id.upper()}"] = {"$exists": True}

    pipeline = [
        {"$match": match},
        {"$sort": {"nombre": 1}},
        {"$facet": {
            "metadata": [{"$count": "total"}],
            "data": [{"$skip": skip}, {"$limit": limit}],
        }},
    ]

    result = await db.productos_vigentes.aggregate(pipeline).to_list(length=1)
    if not result:
        return {"total": 0, "page": page, "items": []}

    total = result[0]["metadata"][0]["total"] if result[0]["metadata"] else 0

    # Reglas globales para aplicar descuentos
    reglas_cursor = db.reglas_descuento.find({"ean": None})
    reglas_raw = await reglas_cursor.to_list(length=None)
    reglas_globales = _hydrate_reglas(reglas_raw)

    items = []
    for doc in result[0]["data"]:
        cadenas_map: dict = doc.get("cadenas") or {}
        cadenas_out = []
        mejor_precio = None
        mejor_cadena = None

        for cad_id, c in cadenas_map.items():
            precio_lista = float(c.get("p_lista") or 0)
            precio_oferta = c.get("p_oferta")
            if precio_oferta:
                precio_oferta = float(precio_oferta)

            if precio_oferta and precio_lista > precio_oferta * 5:
                precio_lista = precio_oferta

            precio_base = precio_oferta if precio_oferta else precio_lista
            reglas_cadena = [r for r in reglas_globales if r.cadena_id == cad_id]

            precio_neto = calcular_precio_neto(
                precio_base,
                reglas_cadena,
                tarjetas_usuario=tarjetas_usuario,
                programas_usuario=programas_usuario,
            )

            ahorro_pct = round((1 - precio_neto / precio_lista) * 100, 1) if precio_lista > 0 else 0

            cadenas_out.append({
                "cadena_id": cad_id,
                "precio_lista": precio_lista,
                "precio_oferta": precio_oferta,
                "precio_neto": precio_neto,
                "precio_por_unidad": c.get("p_unit"),
                "unidad_medida": c.get("u_med"),
                "stock": c.get("stock", True),
                "ahorro_pct": ahorro_pct,
            })

            if c.get("stock", True) and (mejor_precio is None or precio_neto < mejor_precio):
                mejor_precio = precio_neto
                mejor_cadena = cad_id

        items.append({
            "ean": doc["ean"],
            "nombre": doc["nombre"],
            "cadenas": cadenas_out,
            "mejor_cadena": mejor_cadena,
            "mejor_precio": mejor_precio,
        })

    return {"total": total, "page": page, "limit": limit, "items": items}


def _hydrate_reglas(raw_list: list[dict]):
    from modules.promo_engine.models import ReglaDescuento, TipoPromo, DiaSemana
    reglas = []
    for r in raw_list:
        try:
            regla = ReglaDescuento(
                cadena_id=r["cadena_id"],
                tipo=TipoPromo(r["tipo"]),
                texto_original=r.get("texto_original", ""),
                ean=r.get("ean"),
                descuento_pct=r.get("descuento_pct"),
                factor_multiplicador=r.get("factor_multiplicador"),
                banco=r.get("banco"),
                tarjeta=r.get("tarjeta"),
                medio_pago=r.get("medio_pago"),
                dia_semana=DiaSemana(r["dia_semana"]) if r.get("dia_semana") else None,   
                tope_reintegro=r.get("tope_reintegro"),
                programa_fidelidad=r.get("programa_fidelidad"),
                fecha_inicio=r.get("fecha_inicio"),
                fecha_fin=r.get("fecha_fin"),
            )
            reglas.append(regla)
        except Exception:
            continue
    return reglas


def _regla_aplica(regla, tarjetas: list[str] | None, programas: list[str] | None) -> bool:
    from modules.promo_engine.models import TipoPromo
    if regla.tipo == TipoPromo.BANCARIA and tarjetas is not None:
        return any(
            t.lower() in (regla.banco or "").lower()
            or t.lower() in (regla.tarjeta or "").lower()
            for t in tarjetas
        )
    if regla.tipo == TipoPromo.FIDELIDAD and programas is not None:
        return (regla.programa_fidelidad or "").lower() in [p.lower() for p in (programas or [])]
    return True
