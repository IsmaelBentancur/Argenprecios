"""
Módulo 3: The Promo Engine — punto de entrada.
Captura, parsea y persiste reglas de descuento bancarias y de fidelidad.
"""

import asyncio
from typing import Any

from loguru import logger
from playwright.async_api import async_playwright

from db.client import get_db
from modules.promo_engine.models import ReglaDescuento
from modules.promo_engine.parser import parse_promo_text
from modules.harvester.user_agents import get_random_user_agent, get_random_viewport

# Selectores de secciones de promociones por cadena
_PROMO_SELECTORS: dict[str, list[str]] = {
    "COTO": [
        ".banners-promo",
        "[class*='promotional']",
        ".beneficios-container",
        ".promo-texto",
    ],
    "CARREFOUR": [
        "[class*='promotions']",
        "[class*='banner']",
        "[data-testid*='promo']",
        ".shelf-title",
    ],
}

# URLs de páginas de promociones por cadena
_PROMO_URLS: dict[str, list[str]] = {
    "COTO": [
        "https://www.cotodigital.com.ar/sitios/cdigi/beneficios",
        "https://www.cotodigital.com.ar/sitios/cdigi/promociones",
    ],
    "CARREFOUR": [
        "https://www.carrefour.com.ar/promociones",
        "https://www.carrefour.com.ar/descuentos-bancarios",
    ],
}


async def run_promo_engine(cadena: dict[str, Any]) -> int:
    """
    Extrae y persiste reglas de descuento de un supermercado.
    Retorna la cantidad de reglas guardadas.
    """
    cadena_id = cadena["cadena_id"]
    urls = _PROMO_URLS.get(cadena_id, [])
    selectors = _PROMO_SELECTORS.get(cadena_id, [])

    if not urls:
        logger.warning(f"[PromoEngine] Sin URLs de promociones para {cadena_id}")
        return 0

    reglas: list[ReglaDescuento] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        ctx = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport=get_random_viewport(),
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        page = await ctx.new_page()

        # Bloquear recursos pesados
        await page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_()
            ),
        )

        for url in urls:
            try:
                logger.debug(f"[PromoEngine] Extrayendo promos de: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                await asyncio.sleep(1.5)

                for selector in selectors:
                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        texto = (await el.inner_text()).strip()
                        if len(texto) < 10:  # descartamos textos triviales
                            continue
                        # Parsear cada línea del bloque de texto
                        for linea in texto.splitlines():
                            linea = linea.strip()
                            if len(linea) < 10:
                                continue
                            regla = parse_promo_text(linea, cadena_id)
                            if regla:
                                reglas.append(regla)
                                logger.debug(
                                    f"[PromoEngine] Regla capturada: "
                                    f"{regla.tipo.value} | {linea[:60]}"
                                )

            except Exception as exc:
                logger.error(f"[PromoEngine] Error en {url}: {exc}")

        await browser.close()

    saved = await _save_reglas(cadena_id, reglas)
    logger.info(f"[PromoEngine] {cadena_id}: {saved} reglas guardadas")
    return saved


async def _save_reglas(cadena_id: str, reglas: list[ReglaDescuento]) -> int:
    if not reglas:
        return 0

    from pymongo import UpdateOne

    ops = []
    for r in reglas:
        # Clave única: cadena + tipo + banco/programa + día
        key = {
            "cadena_id": r.cadena_id,
            "tipo": r.tipo.value,
            "banco": r.banco,
            "tarjeta": r.tarjeta,
            "programa_fidelidad": r.programa_fidelidad,
            "dia_semana": r.dia_semana.value if r.dia_semana else None,
            "ean": r.ean,
        }
        ops.append(
            UpdateOne(
                key,
                {"$set": r.to_dict()},
                upsert=True,
            )
        )

    result = await get_db().reglas_descuento.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count
