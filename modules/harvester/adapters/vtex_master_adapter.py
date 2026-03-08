# -*- coding: utf-8 -*-
"""
VtexMasterAdapter: Adaptador universal para cadenas basadas en VTEX IO.
Cubre ~90% del retail digital argentino con el mismo codigo base.

STAGING: Todos los adaptadores estan registrados pero inactivos en MongoDB.
Para activar una cadena sin tocar codigo:
  db.comercios_config.updateOne({cadena_id: "JUMBO"}, {$set: {activo: true}})
"""

import asyncio
import random
import re
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import Page, Response

from modules.harvester.adapters.base_adapter import BaseAdapter
from modules.harvester.models import ProductData


class VtexMasterAdapter(BaseAdapter):
    """
    Clase base para todos los adaptadores VTEX IO.
    Subclases deben definir: cadena_id, base_url, categories.
    """
    cadena_id: str = ""
    base_url: str = ""
    search_api_pattern: str = r"/_v/segment/graphql/v1"
    categories: list[str] = []

    async def get_category_urls(self) -> list[str]:
        if not self.base_url or not self.categories:
            logger.warning(f"[{self.cadena_id}] base_url o categories no configurados.")  
            return []
        return [f"{self.base_url.rstrip('/')}/{cat}" for cat in self.categories]

    async def parse_product_list(self, page: Page) -> AsyncIterator[ProductData]:
        api_results = []
        pattern = re.compile(self.search_api_pattern)

        async def _handle_response(response: Response):
            if pattern.search(response.url):
                try:
                    data = await response.json()
                    products = self._detect_products(data)
                    if products:
                        api_results.append(products)
                except Exception:
                    pass

        page.on("response", _handle_response)
        await self._human_behavior(page)

        processed_eans = set()
        for products in api_results:
            for p in products:
                ean = self._extract_vtex_ean(p)
                if not ean or ean in processed_eans:
                    continue

                nombre = p.get("productName")
                items = p.get("items") or []
                if not items:
                    continue

                item = items[0]
                sellers = item.get("sellers") or []
                if not sellers:
                    continue

                comm = sellers[0].get("commertialOffer") or {}
                precio_lista = float(comm.get("ListPrice") or 0)
                precio_venta = float(comm.get("Price") or 0)

                if precio_lista <= 0 or precio_lista == precio_venta:
                    precio_lista = precio_venta
                    precio_oferta = None
                else:
                    precio_oferta = precio_venta

                if precio_lista <= 0:
                    continue

                # Unidades y Pesos Variables (Sprint 2)
                unit = item.get("measurementUnit")
                multiplier = float(item.get("unitMultiplier") or 1)
                p_unit = None
                if multiplier > 0 and multiplier != 1:
                    p_unit = round(precio_venta / multiplier, 2)
                elif unit and unit.lower() in ("kg", "l", "kg.", "l."):
                    p_unit = precio_venta

                stock = comm.get("AvailableQuantity", 0) > 0
                processed_eans.add(ean)

                yield ProductData(
                    ean=ean,
                    nombre=nombre,
                    cadena_id=self.cadena_id,
                    precio_lista=precio_lista,
                    precio_oferta=precio_oferta,
                    stock_disponible=stock,
                    url_origen=page.url,
                    precio_por_unidad=p_unit,
                    unidad_medida=unit
                )

    def _detect_products(self, data: dict) -> list:
        """Auto-detecta el campo de productos segun el schema VTEX de la cadena."""      
        if not isinstance(data, dict):
            return []

        # 1. Intelligent Search standard (GraphQL)
        if "data" in data and "productSearch" in data.get("data", {}):
            return data["data"]["productSearch"].get("products", [])

        # 2. VTEX Search v2 (Legacy/Headless direct)
        if "products" in data and isinstance(data["products"], list):
            return data["products"]

        # 3. Search API direct response (Array of products)
        if isinstance(data, list):
            return data

        # 4. GraphQL direct products
        if "data" in data and "products" in data.get("data", {}):
            return data["data"]["products"]

        return []

    def _extract_vtex_ean(self, product: dict) -> str | None:
        """Extrae el EAN real de un objeto producto VTEX con fallbacks."""
        items = product.get("items", [])
        if items:
            item = items[0]
            ean = item.get("ean")
            if ean and len(ean) in (8, 13) and ean.isdigit():
                return ean
            ref_ids = item.get("referenceId") or []
            if isinstance(ref_ids, list) and ref_ids:
                val = str(ref_ids[0].get("Value", ""))
                if val.isdigit() and len(val) in (8, 13):
                    return val
        return product.get("productReference") or product.get("productId")

    @staticmethod
    async def _human_behavior(page: Page) -> None:
        for _ in range(8):
            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(random.uniform(1.0, 2.5))


# ---------------------------------------------------------------------------
# Adaptadores concretos - todos en staging (activo: False en MongoDB)
# ---------------------------------------------------------------------------

class JumboAdapter(VtexMasterAdapter):
    cadena_id = "JUMBO"
    base_url = "https://www.jumbo.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria",
        "lacteos", "quesos-y-fiambres", "carnes", "frutas-y-verduras",
        "congelados", "panaderia-y-reposteria",
    ]


class DiscoAdapter(VtexMasterAdapter):
    cadena_id = "DISCO"
    base_url = "https://www.disco.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria",
        "lacteos", "carniceria", "frutas-y-verduras", "congelados", "panaderia"
    ]


class VeaAdapter(VtexMasterAdapter):
    cadena_id = "VEA"
    base_url = "https://www.vea.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria",
        "lacteos", "carnes", "frutas-y-verduras", "congelados", "panaderia-y-reposteria"  
    ]


class DiaAdapter(VtexMasterAdapter):
    cadena_id = "DIA"
    base_url = "https://diaonline.supermercadosdia.com.ar"
    categories = [
        "almacen", "bebidas", "frescos", "limpieza", "perfumeria", "congelados", "bebes"  
    ]


class ChangomasAdapter(VtexMasterAdapter):
    cadena_id = "CHANGOMAS"
    base_url = "https://www.masonline.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria",
        "lacteos", "carnes", "frutas-y-verduras", "congelados",
    ]


class FarmacityAdapter(VtexMasterAdapter):
    cadena_id = "FARMACITY"
    base_url = "https://www.farmacity.com"
    categories = [
        "hogar-y-alimentos/alimentos-y-bebidas",
        "hogar-y-alimentos/limpieza-y-desinfeccion",
        "cuidado-personal", "dermocosmetica", "bebes", "salud"
    ]


class JosimarAdapter(VtexMasterAdapter):
    cadena_id = "JOSIMAR"
    base_url = "https://www.josimar.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"  
    ]


class LibertadAdapter(VtexMasterAdapter):
    cadena_id = "LIBERTAD"
    base_url = "https://www.hiperlibertad.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"  
    ]


class ToledoAdapter(VtexMasterAdapter):
    cadena_id = "TOLEDO"
    base_url = "https://www.toledodigital.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"  
    ]


class ElNeneAdapter(VtexMasterAdapter):
    cadena_id = "ELNENE"
    base_url = "https://www.supermercadoselnene.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"  
    ]


class CordiezAdapter(VtexMasterAdapter):
    cadena_id = "CORDIEZ"
    base_url = "https://www.cordiez.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"  
    ]