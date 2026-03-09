# -*- coding: utf-8 -*-
"""
Adaptador para Coto Digital (www.cotodigital.com.ar)

Estrategia de extraccion:
  1. Navegar por categorias del menu principal (Nueva plataforma Angular)
  2. Extraer EAN desde: data-cnstrc-item-id ("prod00566098" -> "00566098")
  3. Extraer precios desde elementos .card-title y selectores especificos
  4. Manejar paginacion via URL ?page=N
"""

import asyncio
import re
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import Page

from modules.harvester.adapters.base_adapter import BaseAdapter
from modules.harvester.models import ProductData

# URLs de categorias de Coto Digital
_COTO_BASE = "https://www.cotodigital.com.ar"
_CATEGORY_URLS = [
    # Congelados (subcategorias)
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-pescaderia/catv00003240",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-nuggets-patitas-y-bocaditos/catv00003239",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-hamburguesas-y-milanesas/catv00003237",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-papas-congeladas-fritas/catv00003201",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-helados-y-postres/catv00003146",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-comidas-congeladas/catv00003238",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-vegetales-congelados/catv00003234",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-congelados-frutas-congeladas/catv00003204",
    # Limpieza (subcategorias)
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-lavado/catv00002752",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-papeles/catv00003017",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-insecticidas/catv00003025",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-calzado/catv00003034",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-accesorios-de-limpieza/catv00003035",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-desodorantes-de-ambiente/catv00003036",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-limpieza-de-bano/catv00003037",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-limpieza-de-cocina/catv00003038",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-limpieza-de-pisos-y-superficies/catv00003039",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-limpieza-lavandinas/catv00004744",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-perfumer%C3%ADa/catv00001257",
    # Almacen
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-golosinas/catv00003539",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-panaderia/catv00003530",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-snacks/catv00003541",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-cereales/catv00003533",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-endulzantes/catv00001270",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-aderezos-y-salsas/catv00002211",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-infusiones/catv00001275",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-conservas/catv00001266",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-harinas/catv00001274",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-encurtidos/catv00001267",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-mermeladas-y-dulces/catv00001273",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-salsas-y-pur%C3%A9-de-tomate/catv00002808",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-aceites-y-condimentos/catv00002975",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-alimento-de-beb%C3%A9s-y-ni%C3%B1os/catv00002976",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-arroz-y-legumbres/catv00002977",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-especias/catv00002978",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-pasta-seca-lista-y-rellenas/catv00002979",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-polvo-para-postres-y-reposteria/catv00002980",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-sopas-caldos-pur%C3%A9-y-saborizantes/catv00002981",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-almac%C3%A9n-rebozador-y-pan-rallado/catv00003542",
    # Bebidas (subcategorias)
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-bebidas-bebidas-sin-alcohol/catv00001301",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-bebidas-bebidas-con-alcohol/catv00001300",
    # Frescos (subcategorias)
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-fiambres/catv00001299",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-quesos/catv00003769",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-carniceria/catv00001292",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-aves/catv00001462", 
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-pastas-frescas-y-tapas/catv00001297",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-frutas-y-verduras/catv00003285",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-pescaderia/catv00001293",
    f"{_COTO_BASE}/sitios/cdigi/productos/categorias/catalogo-frescos-huevos/catv00001464",
]

# Selectores DOM de Coto Digital (Nueva plataforma Angular)
_SEL_PRODUCT_CARD = ".producto-card"
_SEL_PRODUCT_NAME = ".nombre-producto"
_SEL_PRICE_MAIN   = ".card-title"  # Precio destacado (puede ser oferta o regular)
_SEL_PRICE_SMALL  = "small.text-center.ng-star-inserted"
_SEL_PRICE_UNIT   = ".centro-precios small.card-text" # Precio tachado o regular


class CotoAdapter(BaseAdapter):
    cadena_id = "COTO"

    async def get_category_urls(self) -> list[str]:
        return _CATEGORY_URLS

    # Coto gestiona su propia navegación paginada — no usa el nav_task de BaseAdapter.
    # Overrideamos _process_category para evitar la race condition entre el nav_task
    # (que cierra la página) y la paginación interna del adaptador.
    async def _process_category(self, browser, url: str) -> int:
        from playwright.async_api import Browser
        ctx = None
        saved = 0
        try:
            ctx = await self._new_context(browser)
            page = await ctx.new_page()
            await self._block_resources(page)

            batch: list[dict] = []
            async for product in self._paginate(page, url):
                if product.is_valid():
                    batch.append(product.to_dict())

            if batch:
                saved = await self._save_batch(batch)
                logger.info(f"[COTO] {len(batch)} productos en {url} ({saved} con cambios)")
        except Exception as exc:
            logger.error(f"[COTO] Error en {url}: {exc}")
        finally:
            if ctx:
                try:
                    await ctx.close()
                except Exception as e:
                    logger.debug(f"[COTO] ctx.close(): {e}")
        return saved

    # Satisface la interfaz abstracta — no se usa porque _process_category está overrideado.
    async def parse_product_list(self, page: Page) -> AsyncIterator[ProductData]:
        return
        yield  # hace que sea un generador válido

    async def _paginate(self, page: Page, url: str) -> AsyncIterator[ProductData]:
        base_url = url.split("?")[0]
        page_num = 1
        seen_eans: set[str] = set()
        _MAX_PAGES = 60  # safety cap (~1440 productos max por categoria)

        while page_num <= _MAX_PAGES:
            current_url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=45000)
                if page_num > 1:
                    await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"[COTO] Error navegando a p{page_num}: {e}")
                break

            logger.debug(f"[COTO] Pagina {page_num} | {base_url}")

            try:
                await page.wait_for_selector(_SEL_PRODUCT_CARD, timeout=10_000)
            except Exception:
                break

            cards = await page.query_selector_all(_SEL_PRODUCT_CARD)
            if not cards:
                break

            new_in_page = 0
            for card in cards:
                product = await self._extract_from_card(card, page)
                if product and product.ean not in seen_eans:
                    seen_eans.add(product.ean)
                    new_in_page += 1
                    yield product

            logger.debug(f"[COTO] Pagina {page_num}: {new_in_page} productos nuevos")
            if new_in_page == 0:
                break
            if len(cards) < 20:  # Coto muestra 24-48; menos = ultima pagina
                break

            page_num += 1

    async def _extract_from_card(self, card, page: Page) -> ProductData | None:
        try:
            container = await card.query_selector(".card-container")
            item_id = await container.get_attribute("data-cnstrc-item-id") if container else None

            # Coto usa SKUs internos, no siempre EANs globales.
            # Intentamos extraer del JSON-LD primero para ver si hay GTIN.
            card_html = await card.inner_html()
            ean = self.extract_ean_from_json_ld(card_html)

            if not ean and item_id and item_id.startswith("prod"):
                # Fallback al ID interno (prefijo 'prod' eliminado)
                ean = item_id[4:]

            if not ean:
                return None

            nombre = await self._text(card, _SEL_PRODUCT_NAME)
            if not nombre:
                return None

            # Logica de Precios en Coto:
            # .card-title siempre tiene el precio de venta actual.
            # small.text-center tiene el precio regular si hay oferta.
            raw_main = await self._text(card, _SEL_PRICE_MAIN)
            price_main = self.clean_price(raw_main) if raw_main else None

            raw_small = await self._text(card, _SEL_PRICE_SMALL)
            price_small = self.clean_price(raw_small) if raw_small else None

            if price_small and price_main and price_main < price_small:
                # Caso Oferta: Main es el precio rebajado, Small es el lista
                precio_lista = price_small
                precio_oferta = price_main
            else:
                # Caso Regular: Main es el precio de lista
                precio_lista = price_main
                precio_oferta = None

            if not precio_lista:
                return None

            agregar_btn = await card.query_selector("button.btn-primary")
            stock_disponible = agregar_btn is not None

            # URL de detalle del producto (para EAN enricher)
            url_detalle = None
            link_el = await card.query_selector("a[href*='/producto/']")
            if not link_el:
                link_el = await card.query_selector("a")
            if link_el:
                href = await link_el.get_attribute("href")
                if href:
                    url_detalle = href if href.startswith("http") else f"https://www.cotodigital.com.ar{href}"

            # Precio por unidad (Coto)
            # Formato: "Precio por 1 Litro: $1.110,66"
            p_unit = None
            u_med = None
            raw_unit = await self._text(card, _SEL_PRICE_UNIT)
            if raw_unit and "Precio por" in raw_unit:
                m_unit = re.search(r"Precio por ([\d.,]+)\s+([a-zA-Z]+):\s+\$([\d.,]+)", raw_unit, re.I)
                if m_unit:
                    u_med = m_unit.group(2).strip()
                    p_unit = self.clean_price(m_unit.group(3))

            return ProductData(
                ean=ean,
                nombre=nombre.strip(),
                cadena_id=self.cadena_id,
                precio_lista=precio_lista,
                precio_oferta=precio_oferta,
                stock_disponible=stock_disponible,
                url_origen=page.url,
                url_detalle=url_detalle,
                precio_por_unidad=p_unit,
                unidad_medida=u_med,
            )

        except Exception:
            return None

    @staticmethod
    async def _text(element, selector: str) -> str | None:
        el = await element.query_selector(selector)
        if not el: return None
        return (await el.inner_text()).strip() or None



