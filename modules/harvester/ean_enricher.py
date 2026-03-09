"""
EAN Enricher para Coto Digital.

Problema: Coto usa SKUs internos (ej: "00566098") en lugar de GTINs reales.
Esto impide cruzar precios con otras cadenas por EAN.

Solución:
  1. Detectar EANs de Coto que no son GTINs válidos.
  2. Visitar la página de detalle del producto en cotodigital.com.ar.
  3. Extraer el GTIN-13 del JSON-LD (schema.org/Product) o meta tags.
  4. Guardar el mapeo en la colección `coto_mappings`.

Uso manual:
  python -m modules.harvester.ean_enricher

El scheduler puede invocar enrich_batch() periódicamente.
"""

import asyncio
import json
import re
from datetime import datetime, timezone

from loguru import logger
from playwright.async_api import async_playwright

from db.client import get_db
from modules.harvester.ean_utils import is_internal_id, slugify

_COTO_BASE = "https://www.cotodigital.com.ar"
_DETAIL_URL_PATTERN = "{base}/sitios/cdigi/producto/-/{slug}/{product_id}"
_BATCH_SIZE = 50
_DELAY_SECS = 3.0


def _build_detail_url(nombre: str, ean_interno: str) -> str:
    slug = slugify(nombre)
    return _DETAIL_URL_PATTERN.format(
        base=_COTO_BASE, slug=slug, product_id=ean_interno
    )


def _extract_gtin_from_jsonld(html: str) -> str | None:
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Product", "product"):
                    for key in ("gtin13", "gtin8", "gtin", "sku"):
                        val = str(item.get(key, "")).strip()
                        if val.isdigit() and len(val) in (8, 13):
                            return val
        except Exception:
            continue
    return None


async def _fetch_gtin_from_page(page, url: str) -> str | None:
    """Visita la URL de detalle y extrae el GTIN real."""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if resp and resp.status >= 400:
            return None
        await asyncio.sleep(1.5)

        # 1. JSON-LD
        html = await page.content()
        gtin = _extract_gtin_from_jsonld(html)
        if gtin:
            return gtin

        # 2. Meta tags
        meta_gtin = await page.evaluate("""() => {
            const sel = 'meta[property="product:gtin13"], meta[name="gtin"], meta[name="barcode"]';
            const el = document.querySelector(sel);
            return el ? el.getAttribute('content') : null;
        }""")
        if meta_gtin and meta_gtin.isdigit() and len(meta_gtin) in (8, 13):
            return meta_gtin

        # 3. data-ean / data-gtin en DOM
        dom_gtin = await page.evaluate("""() => {
            const el = document.querySelector('[data-ean],[data-gtin],[data-barcode]');
            if (!el) return null;
            return el.getAttribute('data-ean') || el.getAttribute('data-gtin') || el.getAttribute('data-barcode');
        }""")
        if dom_gtin and dom_gtin.isdigit() and len(dom_gtin) in (8, 13):
            return dom_gtin

    except Exception as exc:
        logger.debug(f"[EanEnricher] Error en {url}: {exc}")
    return None


async def _get_pending_eans(db, limit: int) -> list[dict]:
    """EANs de Coto internos sin mapeo en coto_mappings."""
    pipeline = [
        {"$match": {"cadena_id": "COTO"}},
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$ean", "ean": {"$first": "$ean"}, "nombre": {"$first": "$nombre"}, "url_detalle": {"$first": "$url_detalle"}}},
        {"$lookup": {"from": "coto_mappings", "localField": "ean", "foreignField": "ean_interno", "as": "mapping"}},
        {"$match": {"mapping": {"$size": 0}}},
        {"$limit": limit * 3},
    ]
    docs = await db.historial_precios.aggregate(pipeline).to_list(length=None)
    return [
        {"ean_interno": d["ean"], "nombre": d.get("nombre") or "", "url_detalle": d.get("url_detalle")}
        for d in docs
        if is_internal_id(d["ean"])
    ][:limit]


async def enrich_batch(batch_size: int = _BATCH_SIZE) -> dict:
    """
    Enriquece hasta batch_size EANs internos de Coto buscando el GTIN real.
    Retorna {processed, enriched, failed}.
    """
    db = get_db()
    pending = await _get_pending_eans(db, batch_size)

    if not pending:
        logger.info("[EanEnricher] No hay EANs internos de Coto pendientes.")
        return {"processed": 0, "enriched": 0, "failed": 0}

    logger.info(f"[EanEnricher] Procesando {len(pending)} EANs internos de Coto...")
    enriched = failed = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-gpu"],
        )
        ctx = await browser.new_context(
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            ignore_https_errors=True,
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await ctx.new_page()

        async def _block(route):
            if route.request.resource_type in {"image", "media", "font", "stylesheet", "other"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _block)

        for item in pending:
            ean_interno = item["ean_interno"]
            nombre = item["nombre"]
            # Preferir url_detalle si ya está almacenada; si no, construirla
            url = item.get("url_detalle") or _build_detail_url(nombre, ean_interno)

            gtin = await _fetch_gtin_from_page(page, url)
            now = datetime.now(tz=timezone.utc)

            if gtin and gtin != ean_interno:
                await db.coto_mappings.update_one(
                    {"ean_interno": ean_interno},
                    {
                        "$set": {"ean_interno": ean_interno, "gtin": gtin, "nombre": nombre, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
                logger.info(f"[EanEnricher] ✓ {ean_interno} â†’ {gtin}  {nombre[:40]}")
                enriched += 1
            else:
                # Marcar como procesado (sin GTIN) para no reintentar indefinidamente
                await db.coto_mappings.update_one(
                    {"ean_interno": ean_interno},
                    {
                        "$set": {"ean_interno": ean_interno, "gtin": None, "nombre": nombre, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                        "$inc": {"intentos": 1},
                    },
                    upsert=True,
                )
                logger.debug(f"[EanEnricher] ✖ {ean_interno} sin GTIN  {nombre[:40]}")
                failed += 1

            await asyncio.sleep(_DELAY_SECS)

        try:
            await ctx.close()
            await browser.close()
        except Exception:
            pass

    result = {"processed": len(pending), "enriched": enriched, "failed": failed}
    logger.info(f"[EanEnricher] {result}")
    return result


if __name__ == "__main__":
    asyncio.run(enrich_batch())

