"""
Adaptador para Carrefour (www.carrefour.com.ar)
Usa la API de VTEX Intelligent Search interceptando respuestas GraphQL.
Paginación via URL ?page=N — igual que Coto.
"""

import asyncio
import random
import re
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import Page, Response

from modules.harvester.adapters.base_adapter import BaseAdapter
from modules.harvester.models import ProductData

_SEARCH_API_PATTERN = re.compile(r"carrefour\.com\.ar/_v/segment/graphql/v1")

_CATEGORIES = [
    "almacen", "bebidas", "limpieza", "perfumeria", "lacteos-y-productos-frescos",
    "carniceria", "frutas-y-verduras", "congelados", "panaderia", "bebes", "mascotas",
]

_MIN_PRODUCTS_PER_PAGE = 12  # si llegan menos, es la última página


class CarrefourAdapter(BaseAdapter):
    cadena_id = "CARREFOUR"

    async def get_category_urls(self) -> list[str]:
        return [f"https://www.carrefour.com.ar/{cat}" for cat in _CATEGORIES]

    async def parse_product_list(self, page: Page) -> AsyncIterator[ProductData]:
        base_url = page.url.split("?")[0]
        page_num = 1
        processed_eans: set[str] = set()

        while True:
            # Navegar a la página correspondiente (página 1 ya está cargada)
            if page_num > 1:
                try:
                    await page.goto(
                        f"{base_url}?page={page_num}",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    await asyncio.sleep(2.0)
                except Exception:
                    break

            logger.debug(f"[CARREFOUR] Página {page_num} | {base_url}")

            # Capturar respuestas de la API VTEX durante el scroll
            page_products: list[dict] = []

            async def _handle_response(response: Response):
                if _SEARCH_API_PATTERN.search(response.url):
                    try:
                        data = await response.json()
                        if isinstance(data, dict) and "data" in data:
                            ps = data["data"].get("productSearch", {}).get("products") or []
                            page_products.extend(ps)
                    except Exception:
                        pass

            page.on("response", _handle_response)
            await self._scroll_page(page)
            page.remove_listener("response", _handle_response)

            if not page_products:
                logger.debug(f"[CARREFOUR] Sin productos en página {page_num}, deteniendo.")
                break

            count = 0
            for p in page_products:
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

                # Unidades y Pesos Variables
                unit = item.get("measurementUnit")
                multiplier = float(item.get("unitMultiplier") or 1)
                p_unit = None
                if multiplier > 0 and multiplier != 1:
                    p_unit = round(precio_venta / multiplier, 2)
                elif unit and unit.lower() in ("kg", "l", "kg.", "l."):
                    p_unit = precio_venta

                stock = comm.get("AvailableQuantity", 0) > 0
                processed_eans.add(ean)
                count += 1

                yield ProductData(
                    ean=ean,
                    nombre=nombre,
                    cadena_id=self.cadena_id,
                    precio_lista=precio_lista,
                    precio_oferta=precio_oferta,
                    stock_disponible=stock,
                    url_origen=page.url,
                    precio_por_unidad=p_unit,
                    unidad_medida=unit,
                )

            logger.debug(f"[CARREFOUR] {count} productos nuevos en página {page_num}")

            # Condición de corte: página con pocos productos = última página
            if len(page_products) < _MIN_PRODUCTS_PER_PAGE:
                break

            page_num += 1

    def _extract_vtex_ean(self, p: dict) -> str | None:
        """Extrae EAN real de VTEX con fallbacks."""
        items = p.get("items") or []
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
        return p.get("productReference") or p.get("productId")

    @staticmethod
    async def _scroll_page(page: Page) -> None:
        """Scroll progresivo para disparar lazy loading y respuestas de API VTEX."""
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 900)")
            await asyncio.sleep(random.uniform(1.0, 2.0))

