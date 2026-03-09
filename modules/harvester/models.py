# -*- coding: utf-8 -*-
"""
Modelos de datos del Harvester.
ProductData es el contrato de salida que todos los adaptadores deben cumplir.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _isoweek() -> str:
    """Devuelve la clave de semana actual para el Bucketing Pattern. Ej: '2025-W22'"""
    today = datetime.now(tz=timezone.utc)
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class ProductData:
    ean: str                          # GTIN-13 u 8 - clave primaria obligatoria
    nombre: str
    cadena_id: str                    # Ej: "COTO", "JUMBO"
    precio_lista: float
    precio_oferta: float | None
    stock_disponible: bool
    url_origen: str
    url_detalle: str | None = None    # URL a la ficha del producto (para enriquecimiento)
    captured_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    semana: str = field(default_factory=_isoweek)
    precio_por_unidad: float | None = None
    unidad_medida: str | None = None

    def to_dict(self) -> dict:
        return {
            "ean": self.ean,
            "nombre": self.nombre,
            "cadena_id": self.cadena_id,
            "precio_lista": self.precio_lista,
            "precio_oferta": self.precio_oferta,
            "stock_disponible": self.stock_disponible,
            "url_origen": self.url_origen,
            "url_detalle": self.url_detalle,
            "captured_at": self.captured_at,
            "semana": self.semana,
            "precio_por_unidad": self.precio_por_unidad,
            "unidad_medida": self.unidad_medida,
        }

    def is_valid(self) -> bool:
        """Valida que el EAN tenga longitud correcta y el precio sea positivo."""
        ean_ok = len(self.ean) in (8, 13) and self.ean.isdigit()
        precio_ok = self.precio_lista > 0
        return ean_ok and precio_ok

