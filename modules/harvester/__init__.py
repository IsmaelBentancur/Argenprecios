# -*- coding: utf-8 -*-
"""
Modulo 2: The Harvester - punto de entrada.
The Clock llama a run_harvester() pasando la cadena y el semaforo.
"""

import asyncio
from typing import Any

from loguru import logger

from modules.harvester.adapters.coto_adapter import CotoAdapter
from modules.harvester.adapters.carrefour_adapter import CarrefourAdapter
from modules.harvester.adapters.vtex_master_adapter import (
    JumboAdapter, DiscoAdapter, VeaAdapter, DiaAdapter,
    ChangomasAdapter, FarmacityAdapter, JosimarAdapter,
    LibertadAdapter, ToledoAdapter, ElNeneAdapter, CordiezAdapter,
)

# Registro de adaptadores disponibles.
# STAGING: Las cadenas nuevas estan inactivas en MongoDB (activo: False en comercios_config).
# Para activar una cadena sin deploy:
#   db.comercios_config.updateOne({cadena_id: "JUMBO"}, {$set: {activo: true}})
_ADAPTER_REGISTRY: dict[str, type] = {
    "COTO": CotoAdapter,
    "CARREFOUR": CarrefourAdapter,
    # Staging - VTEX (Sprint 1/2)
    "JUMBO": JumboAdapter,
    "DISCO": DiscoAdapter,
    "VEA": VeaAdapter,
    "DIA": DiaAdapter,
    "CHANGOMAS": ChangomasAdapter,
    "FARMACITY": FarmacityAdapter,
    "JOSIMAR": JosimarAdapter,
    "LIBERTAD": LibertadAdapter,
    "TOLEDO": ToledoAdapter,
    "ELNENE": ElNeneAdapter,
    "CORDIEZ": CordiezAdapter,
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