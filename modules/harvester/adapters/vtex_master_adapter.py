# -*- coding: utf-8 -*-
"""
VtexMasterAdapter: Adaptador universal para cadenas basadas en VTEX IO.
Cubre ~90% del retail digital argentino con el mismo codigo base.
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
    # Patrones comunes de API de búsqueda VTEX (Legacy, IS GraphQL, IS REST, PickRuntime)
    search_api_pattern: str = r"/graphql|/products/search|/product_search|/search_suggestions|/api/io/|/s\?map="
    categories: list[str] = []

    async def get_category_urls(self) -> list[str]:
        if not self.base_url or not self.categories:
            logger.warning(f"[{self.cadena_id}] base_url o categories no configurados.")  
            return []
        return [f"{self.base_url.rstrip('/')}/{cat}" for cat in self.categories]

    async def parse_product_list(self, page: Page) -> AsyncIterator[ProductData]:
        """
        Intercepta las respuestas de la API de VTEX mientras se navega por la página.
        Usa un queue para entregar productos en tiempo real al BaseAdapter.
        La navegación la maneja BaseAdapter (page.goto + _human_behavior).
        """
        queue = asyncio.Queue()
        pattern = re.compile(self.search_api_pattern)
        processed_eans = set()

        async def _handle_response(response: Response):
            if pattern.search(response.url):
                try:
                    data = await response.json()
                    products = self._detect_products(data)
                    if not products and any(k in response.url for k in ("product", "search")):
                        logger.trace(f"[{self.cadena_id}] No se detectaron productos en API match: {response.url[:100]}")
                    
                    for p in products:
                        ean = self._extract_vtex_ean(p)
                        if ean and ean not in processed_eans:
                            processed_eans.add(ean)
                            product = self._map_product(p, page.url)
                            if product:
                                await queue.put(product)
                except Exception:
                    pass
            elif any(k in response.url for k in ("product", "search", "catalog", "graphql")):
                # Logueamos solo si no es un asset (JS/CSS/PNG)
                if not any(ext in response.url for ext in (".js", ".css", ".png", ".jpg", ".webp", ".svg")):
                    logger.debug(f"[{self.cadena_id}] API no mapeada: {response.url[:120]}")

        # Registrar listener ANTES del goto (manejado por el flujo de BaseAdapter)
        page.on("response", _handle_response)

        # Inyectar vtex_segment para forzar precios de Buenos Aires en todas las cadenas VTEX
        from urllib.parse import urlparse
        domain = urlparse(self.base_url).hostname or ""
        if domain:
            await self._set_vtex_region(page, domain)

        # JS para extraer productos del Apollo cache (window.__STATE__) de VTEX IO SSR.
        # Soporta claves Product: y StoreProduct: según versión del store.
        _JS_STATE = """
        () => {
            const state = window.__STATE__;
            if (!state) return [];
            function resolve(node, visited) {
                if (!visited) visited = new Set();
                if (node === null || typeof node !== 'object') return node;
                // Apollo cache usa { __ref: "Key:id" } para referencias — nunca "id"
                if (node.__ref && state[node.__ref]) {
                    if (visited.has(node.__ref)) return { __circular: true };
                    visited.add(node.__ref);
                    return resolve(state[node.__ref], new Set(visited));
                }
                if (Array.isArray(node)) return node.map(function(i) { return resolve(i, new Set(visited)); });
                const out = {};
                for (const k in node) { if (k !== '__typename') out[k] = resolve(node[k], new Set(visited)); }
                return out;
            }
            const products = [];
            const seen = new Set();
            for (const key in state) {
                if (/^(Store)?Product:/i.test(key)) {
                    const p = resolve(state[key]);
                    const name = p && (p.productName || p.name);
                    if (name && !seen.has(key)) { seen.add(key); products.push(p); }
                }
            }
            return products;
        }
        """

        async def _run_state_extraction():
            """Extrae productos de window.__STATE__ (SSR). Llamar solo con página abierta."""
            try:
                result = await page.evaluate(_JS_STATE)
                if result:
                    logger.info(f"[{self.cadena_id}] __STATE__ fallback: {len(result)} productos")
                for p in result or []:
                    ean = self._extract_vtex_ean(p)
                    if ean and ean not in processed_eans:
                        processed_eans.add(ean)
                        mapped = self._map_product(p, page.url)
                        if mapped:
                            await queue.put(mapped)
            except Exception as e:
                logger.debug(f"[{self.cadena_id}] Error en __STATE__ fallback: {e}")

        # Consumir cola hasta que la página se cierre.
        # Fallback SSR: si después de 5 timeouts (5s) sin productos de API y la página
        # sigue abierta, extraer inline de window.__STATE__.
        # Evita la race condition de background task vs page.close().
        idle_ticks = 0
        state_extracted = False
        while True:
            try:
                product = await asyncio.wait_for(queue.get(), timeout=1.0)
                idle_ticks = 0
                yield product
            except asyncio.TimeoutError:
                if page.is_closed():
                    break
                idle_ticks += 1
                # 5s idle sin API → modo SSR → extracción inline (página garantizadamente abierta)
                if not state_extracted and idle_ticks >= 5:
                    state_extracted = True
                    await _run_state_extraction()

    def _map_product(self, p: dict, source_url: str) -> ProductData | None:
        try:
            nombre = p.get("productName") or p.get("name")
            items = p.get("items") or []
            if not items: return None

            item = items[0]
            ean = self._extract_vtex_ean(p)
            sellers = item.get("sellers") or []
            if not sellers: return None

            comm = sellers[0].get("commertialOffer") or {}
            precio_lista = float(comm.get("ListPrice") or 0)
            precio_venta = float(comm.get("Price") or 0)

            if precio_lista <= 0 or precio_lista == precio_venta:
                precio_lista = precio_venta
                precio_oferta = None
            else:
                precio_oferta = precio_venta

            if precio_lista <= 0: return None

            unit = item.get("measurementUnit")
            multiplier = float(item.get("unitMultiplier") or 1)
            p_unit = None
            if multiplier > 0 and multiplier != 1:
                p_unit = round(precio_venta / multiplier, 2)
            elif unit and unit.lower() in ("kg", "l", "kg.", "l."):
                p_unit = precio_venta

            return ProductData(
                ean=ean,
                nombre=nombre,
                cadena_id=self.cadena_id,
                precio_lista=precio_lista,
                precio_oferta=precio_oferta,
                stock_disponible=comm.get("AvailableQuantity", 0) > 0,
                url_origen=source_url,
                precio_por_unidad=p_unit,
                unidad_medida=unit
            )
        except Exception:
            return None

    def _detect_products(self, data: dict) -> list:
        if not isinstance(data, dict): return []
        # 1. Apollo GraphQL standard (productSearch)
        if "data" in data and "productSearch" in data.get("data", {}):
            return data["data"]["productSearch"].get("products", [])
        # 2. Apollo GraphQL variant (products)
        if "data" in data and "products" in data.get("data", {}):
            return data["data"]["products"]
        # 3. Custom products key
        if "products" in data and isinstance(data["products"], list):
            return data["products"]
        # 4. Search API direct response (Array of products)
        if isinstance(data, list):
            return data
        # 5. PickRuntime / __pickRuntime
        if "blocks" in data:
            # Recursividad simple para buscar listas de productos en bloques de VTEX
            def find_products(obj):
                if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict) and "productId" in obj[0]:
                    return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        res = find_products(v)
                        if res: return res
                return None
            return find_products(data) or []
        return []

    def _extract_vtex_ean(self, product: dict) -> str | None:
        items = product.get("items", [])
        if items:
            item = items[0]
            ean = item.get("ean")
            if ean and len(ean) in (8, 13) and ean.isdigit(): return ean
            ref_ids = item.get("referenceId") or []
            if isinstance(ref_ids, list) and ref_ids:
                val = str(ref_ids[0].get("Value", ""))
                if val.isdigit() and len(val) in (8, 13): return val
        ref = product.get("productReference") or product.get("productId")
        if ref and str(ref).isdigit() and len(str(ref)) in (8, 13): return str(ref)
        return None

    @staticmethod
    async def _human_behavior(page: Page) -> None:
        for _ in range(12):
            try:
                await page.evaluate("window.scrollBy(0, 1200)")
            except Exception:
                break
            await asyncio.sleep(random.uniform(0.8, 1.5))
        await asyncio.sleep(2.0)


# Adaptadores concretos
class JumboAdapter(VtexMasterAdapter):
    cadena_id = "JUMBO"
    base_url = "https://www.jumbo.com.ar"
    categories = [
        "almacen", "bebidas", "limpieza", "perfumeria", "lacteos", "quesos-y-fiambres",
        "carnes", "frutas-y-verduras", "congelados", "panaderia-y-reposteria",
        "47824?map=productClusterIds", "156?map=productClusterIds", "218?map=productClusterIds",
        "219?map=productClusterIds", "46428?map=productClusterIds", "20347?map=productClusterIds",
        "19697?map=productClusterIds", "19694?map=productClusterIds", "19698?map=productClusterIds",
        "19695?map=productClusterIds", "19699?map=productClusterIds", "19696?map=productClusterIds",
        "Almacen/Desayuno-y-Merienda", "Almacen/Golosinas-y-Chocolates", "Almacen/Snacks",
        "carnes/embutidos", "Lacteos/Leches", "Frutas-y-Verduras/Verduras",
        "Frutas-y-Verduras/Frutas", "carnes/embutidos/chorizos"
    ]

class DiscoAdapter(VtexMasterAdapter):
    cadena_id = "DISCO"
    base_url = "https://www.disco.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "lacteos", "carniceria", "frutas-y-verduras", "congelados", "panaderia"]

class VeaAdapter(VtexMasterAdapter):
    cadena_id = "VEA"
    base_url = "https://www.vea.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "lacteos", "carnes", "frutas-y-verduras", "congelados", "panaderia-y-reposteria"]

class DiaAdapter(VtexMasterAdapter):
    cadena_id = "DIA"
    base_url = "https://diaonline.supermercadosdia.com.ar"
    categories = ["almacen", "bebidas", "frescos", "limpieza", "perfumeria", "congelados", "bebes"]

class ChangomasAdapter(VtexMasterAdapter):
    cadena_id = "CHANGOMAS"
    base_url = "https://www.masonline.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "lacteos", "carnes", "frutas-y-verduras", "congelados"]

class JosimarAdapter(VtexMasterAdapter):
    cadena_id = "JOSIMAR"
    base_url = "https://www.josimar.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"]

class LibertadAdapter(VtexMasterAdapter):
    cadena_id = "LIBERTAD"
    base_url = "https://www.hiperlibertad.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"]

class ToledoAdapter(VtexMasterAdapter):
    cadena_id = "TOLEDO"
    base_url = "https://www.toledodigital.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"]

class CordiezAdapter(VtexMasterAdapter):
    cadena_id = "CORDIEZ"
    base_url = "https://www.cordiez.com.ar"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "frescos", "bebes", "congelados"]

class CooperativaObreraAdapter(VtexMasterAdapter):
    cadena_id = "LACOOPE"
    base_url = "https://www.lacoopeencasa.coop"
    categories = ["productos/almacen", "productos/bebidas", "productos/frescos", "productos/limpieza", "productos/perfumeria", "productos/congelados"]

class LaAnonimaAdapter(VtexMasterAdapter):
    cadena_id = "LAANONIMA"
    base_url = "https://www.laanonimaonline.com"
    categories = ["almacen", "bebidas", "limpieza", "perfumeria", "frescos", "congelados"]