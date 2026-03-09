# -*- coding: utf-8 -*-
"""
Modulo 2 - The Harvester
BaseAdapter: Clase abstracta que define el contrato para todos los adaptadores.
"""

import asyncio
import json
import random
import re
from abc import ABC, abstractmethod
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    async_playwright,
)

from db.client import get_db
from modules.harvester.models import ProductData
from modules.harvester.user_agents import get_random_user_agent, get_random_viewport      

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet", "other"}
_EAN_RE = re.compile(r"\b(\d{8}|\d{13})\b")


class BaseAdapter(ABC):
    cadena_id: str = ""

    def __init__(self, semaphore: asyncio.Semaphore):
        self._semaphore = semaphore
        self._db = get_db()

    async def run(self) -> int:
        total_saved = 0
        async with async_playwright() as pw:
            category_urls = await self.get_category_urls()
            logger.info(f"[{self.cadena_id}] {len(category_urls)} categorias a procesar")

            # Un solo browser para todas las categorias - mas eficiente en CPU/RAM
            browser = await self._launch_browser(pw)
            try:
                # Procesamiento paralelo de categorias limitado por semaforo
                tasks = [self._process_category_with_semaphore(browser, url) for url in category_urls]
                results = await asyncio.gather(*tasks)
                total_saved = sum(results)
            finally:
                try: await browser.close()
                except Exception as exc: logger.debug(f"[{self.cadena_id}] browser.close(): {exc}")

        if total_saved == 0:
            logger.error(f"[{self.cadena_id}] CRíTICO: 0 productos capturados. Verificar selectores o disponibilidad del sitio.")
        else:
            logger.info(f"[{self.cadena_id}] Total guardados/actualizados: {total_saved}")
        return total_saved

    async def _process_category_with_semaphore(self, browser: Browser, url: str) -> int:
        async with self._semaphore:
            return await self._process_category(browser, url)

    @abstractmethod
    async def get_category_urls(self) -> list[str]: ...

    @abstractmethod
    async def parse_product_list(self, page: Page) -> AsyncIterator[ProductData]: ...

    async def _launch_browser(self, pw: Playwright) -> Browser:
        return await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-gpu"]
        )

    # Cookie vtex_segment para forzar precios de Buenos Aires (sc=1, ARG, es-AR, ARS)
    # JSON: {"ecommerce_rules_cache_render":true,"sc":"1","cultureInfo":"es-AR",
    #        "currencyCode":"ARS","currencySymbol":"$","country":"ARG"}
    _VTEX_SEGMENT_COOKIE = (
        "eyJlY29tbWVyY2VfcnVsZXNfY2FjaGVfcmVuZGVyIjp0cnVlLCJzYyI6IjEiLCJjdWx0dXJlSW5mbyI6ImVz"
        "LUFSIiwiY3VycmVuY3lDb2RlIjoiQVJTIiwiY3VycmVuY3lTeW1ib2wiOiIkIiwiY291bnRyeSI6IkFSRyJ9"
    )

    async def _new_context(self, browser: Browser) -> BrowserContext:
        ua = get_random_user_agent()
        vp = get_random_viewport()
        ctx = await browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            ignore_https_errors=True,
        )
        # playwright-stealth: oculta indicadores de automatizacion del navegador.
        # Se aplica al contexto para que todas las paginas hereden el stealth.
        try:
            from playwright_stealth import stealth_async
            await stealth_async(ctx)
        except Exception:
            # Fallback manual si la libreria no esta disponible
            await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return ctx

    async def _set_vtex_region(self, page: "Page", domain: str) -> None:
        """Inyecta la cookie vtex_segment para forzar precios de Buenos Aires."""
        try:
            await page.context.add_cookies([{
                "name": "vtex_segment",
                "value": self._VTEX_SEGMENT_COOKIE,
                "domain": domain,
                "path": "/",
            }])
        except Exception:
            pass

    async def _block_resources(self, page: Page) -> None:
        async def _handler(route: Route) -> None:
            if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", _handler)

    async def _process_category(self, browser: Browser, url: str) -> int:
        ctx = None
        saved = 0
        try:
            ctx = await self._new_context(browser)
            page = await ctx.new_page()
            await self._block_resources(page)
            
            # Inyectar regionalización si es VTEX (basado en dominio)
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if "jumbo" in domain or "disco" in domain or "vea" in domain or "diaonline" in domain:
                await self._set_vtex_region(page, domain)

            logger.debug(f"[{self.cadena_id}] Abriendo: {url}")

            batch: list[dict] = []

            async def _navigate():
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await self._human_behavior(page)
                finally:
                    # SIEMPRE cerrar la pagina, incluso si goto() o human_behavior() fallan.
                    # Sin esto, page.is_closed() nunca es True y el generador VTEX
                    # queda en loop infinito esperando la cola (bug en ChangoMas).
                    try:
                        await page.close()
                    except Exception:
                        pass

            # Lanzar navegacion como task concurrente para que el generador pueda
            # registrar su listener (page.on) ANTES de que los requests de red ocurran.
            nav_task = asyncio.ensure_future(_navigate())
            try:
                async for product in self.parse_product_list(page):
                    if not product.is_valid():
                        continue
                    batch.append(product.to_dict())
            finally:
                await nav_task

            if batch:
                saved = await self._save_batch(batch)
                logger.info(f"[{self.cadena_id}] {len(batch)} productos capturados en {url} ({saved} con cambios)")
        except Exception as exc:
            logger.error(f"[{self.cadena_id}] Error en {url}: {exc}")
        finally:
            if ctx:
                try: await ctx.close()
                except Exception as exc: logger.debug(f"[{self.cadena_id}] ctx.close(): {exc}")
        return saved

    async def _save_batch(self, products: list[dict]) -> int:
        """
        Guarda un lote de productos.
        Solo actualiza si hay cambios reales en precio o stock.
        La resolucion de EANs internos -> GTINs reales ocurre en read-time (calculator.py).
        """
        if not products:
            return 0
        from pymongo import UpdateOne

        ops = []
        for p in products:
            bucket_id = f"{p['ean']}_{p['cadena_id']}_{p['semana']}"

            # Buscamos por bucket_id Y (precio distinto O stock distinto)
            ops.append(UpdateOne(
                {
                    "bucket_id": bucket_id,
                    "$or": [
                        {"ultimo_precio_lista": {"$ne": p["precio_lista"]}},
                        {"ultimo_precio_oferta": {"$ne": p["precio_oferta"]}},
                        {"stock_disponible": {"$ne": p["stock_disponible"]}}
                    ]
                },
                {
                    "$set": {
                        "ean": p["ean"], "cadena_id": p["cadena_id"], "nombre": p["nombre"],
                        "semana": p["semana"], "ultimo_precio_lista": p["precio_lista"],  
                        "ultimo_precio_oferta": p["precio_oferta"], "stock_disponible": p["stock_disponible"],
                        "url_origen": p["url_origen"], "url_detalle": p.get("url_detalle"), "updated_at": p["captured_at"],
                        "precio_por_unidad": p.get("precio_por_unidad"),
                        "unidad_medida": p.get("unidad_medida"),
                    },
                    "$push": {
                        "capturas": {
                            "$each": [{"precio_lista": p["precio_lista"], "precio_oferta": p["precio_oferta"], "ts": p["captured_at"]}],
                            "$slice": -20,  # conservar solo las ultimas 20 capturas
                        }
                    },
                    "$setOnInsert": {"bucket_id": bucket_id, "captured_at": p["captured_at"]},
                },
                upsert=True
            ))

        try:
            result = await self._db.historial_precios.bulk_write(ops, ordered=False)      
            return (result.upserted_count or 0) + (result.modified_count or 0)
        except Exception as e:
            from pymongo.errors import BulkWriteError
            if isinstance(e, BulkWriteError):
                details = e.details
                saved = (details.get("nUpserted") or 0) + (details.get("nModified") or 0) 
                logger.warning(f"[{self.cadena_id}] BulkWrite parcial: {saved} guardados, {len(details.get('writeErrors', []))} errores")
                return saved
            logger.error(f"[{self.cadena_id}] Error en _save_batch: {e}")
            return 0

    @staticmethod
    def clean_price(raw: str) -> float | None:
        """
        Parsea precios en formato argentino.
        Separador de miles: punto  ->  $12.900  o  $2.900
        Separador decimal: coma   ->  $12.900,00  o  $2.900,00
        """
        cleaned = "".join(c for c in raw if c.isdigit() or c in ",.")
        if not cleaned:
            return None

        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            if cleaned.count(".") == 1 and re.search(r"\.\d{3}$", cleaned):
                cleaned = cleaned.replace(".", "")
            elif cleaned.count(".") > 1:
                cleaned = cleaned.replace(".", "")

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def extract_ean_from_text(text: str) -> str | None:
        match = _EAN_RE.search(text)
        return match.group(1) if match else None

    @staticmethod
    def extract_ean_from_json_ld(html: str) -> str | None:
        pattern = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
        for match in pattern.finditer(html):
            try:
                data = json.loads(match.group(1))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Product", "product"):
                        for key in ("gtin13", "gtin8", "gtin", "sku"):
                            val = str(item.get(key, ""))
                            if len(val) in (8, 13) and val.isdigit(): return val
            except Exception: continue
        return None

    @staticmethod
    async def _human_behavior(page: Page) -> None:
        await asyncio.sleep(random.uniform(1.0, 3.0))
        try:
            await page.evaluate("""async () => {
                await new Promise(resolve => {
                    let total = 0; const dist = 400;
                    const timer = setInterval(() => {
                        window.scrollBy(0, dist); total += dist;
                        if (total >= document.body.scrollHeight) { clearInterval(timer); resolve(); }
                    }, 200);
                });
            }""")
        except Exception:
            pass
        await asyncio.sleep(random.uniform(1.0, 2.0))





