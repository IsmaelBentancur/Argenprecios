# -*- coding: utf-8 -*-
"""
Modulo 2: The Harvester - punto de entrada.
The Clock llama a run_harvester() pasando la cadena y el semaforo.
"""

import asyncio
from typing import Any

from loguru import logger

from modules.harvester.adapters.coto_adapter import CotoAdapter
from modules.harvester.adapters.vtex_master_adapter import (
    JumboAdapter, DiscoAdapter, VeaAdapter, DiaAdapter,
    ChangomasAdapter, JosimarAdapter,
    LibertadAdapter, ToledoAdapter, CordiezAdapter,
    CooperativaObreraAdapter, LaAnonimaAdapter,
)

# Cadenas activas según lista aprobada por Isma (2026-03-09):
# Coto, Día, Jumbo, Disco, Vea, MásOnline, La Anónima, Cooperativa Obrera,
# Josimar, Toledo, Cordiez, Hipermercado Libertad
_ADAPTER_REGISTRY: dict[str, type] = {
    "COTO": CotoAdapter,
    "JUMBO": JumboAdapter,
    "DISCO": DiscoAdapter,
    "VEA": VeaAdapter,
    "DIA": DiaAdapter,
    "CHANGOMAS": ChangomasAdapter,
    "JOSIMAR": JosimarAdapter,
    "LIBERTAD": LibertadAdapter,
    "TOLEDO": ToledoAdapter,
    "CORDIEZ": CordiezAdapter,
    "LACOOPE": CooperativaObreraAdapter,
    "LAANONIMA": LaAnonimaAdapter,
}


async def run_harvester(cadena: dict[str, Any], semaphore: asyncio.Semaphore) -> int:     
    """
    Instancia el adaptador correspondiente a la cadena y ejecuta el scraping.
    Retorna la cantidad de productos guardados.
    """
    cadena_id: str = cadena["cadena_id"]
    adapter_cls = _ADAPTER_REGISTRY.get(cadena_id)

    if not adapter_cls:
        logger.warning(f"[Harvester] Sin adaptador para cadena: {cadena_id}. Ignorando.") 
        return 0

    logger.info(f"[Harvester] Iniciando adaptador: {cadena_id}")
    adapter = adapter_cls(semaphore=semaphore)
    return await adapter.run()

