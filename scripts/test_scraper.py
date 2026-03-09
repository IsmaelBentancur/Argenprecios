"""
Script de prueba para validación del scraper de Coto.
Verifica:
  1. Extracción de EAN/SKU.
  2. Parseo de precios (Lista vs Oferta).
  3. Formato de moneda argentina.
"""

import asyncio
import sys
import os

# Agregar el directorio raíz al path para poder importar los módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from loguru import logger
from modules.harvester.adapters.coto_adapter import CotoAdapter

async def test_adapter(adapter_class, limit=5):
    logger.info(f"--- Probando {adapter_class.cadena_id} ---")
    sem = asyncio.Semaphore(1)
    adapter = adapter_class(sem)

    # Mock de save_batch para no ensuciar la DB
    async def mock_save(products):
        for p in products:
            logger.info(f"[{adapter.cadena_id}] {p['ean']} | {p['nombre'][:40]}... | Lista: ${p['precio_lista']} | Oferta: ${p['precio_oferta'] or '-'}")
        return len(products)

    adapter._save_batch = mock_save

    # Solo procesamos la primera categoría para la prueba
    urls = await adapter.get_category_urls()
    if not urls:
        logger.error("No se encontraron URLs de categorías")
        return

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await adapter._launch_browser(pw)
        ctx = await adapter._new_context(browser)
        page = await ctx.new_page()

        logger.info(f"Navegando a: {urls[0]}")
        await page.goto(urls[0], wait_until="domcontentloaded", timeout=60000)

        count = 0
        async for product in adapter.parse_product_list(page):
            logger.success(f"Capturado: {product.ean} | {product.nombre[:30]} | ${product.precio_lista}")
            count += 1
            if count >= limit:
                break

        await browser.close()

if __name__ == "__main__":
    # Configurar logger
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    async def main():
        try:
            await test_adapter(CotoAdapter)
        except Exception as e:
            logger.error(f"Error probando Coto: {e}")

    asyncio.run(main())
