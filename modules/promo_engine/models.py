"""
Módulo 3 — The Promo Engine
Modelos de Reglas de Descuento.

Una ReglasDescuento es la representación estructurada de una promoción
capturada del sitio del supermercado (banner, sección promociones, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TipoPromo(str, Enum):
    DIRECTA    = "directa"      # 20% OFF en toda la compra
    MULTI_UNIT = "multi_unit"   # 2da unidad al 70%, 3x2
    BANCARIA   = "bancaria"     # % descuento con tarjeta/banco específico
    FIDELIDAD  = "fidelidad"    # Precio exclusivo para socios del programa


class DiaSemana(str, Enum):
    LUNES     = "lunes"
    MARTES    = "martes"
    MIERCOLES = "miercoles"
    JUEVES    = "jueves"
    VIERNES   = "viernes"
    SABADO    = "sabado"
    DOMINGO   = "domingo"
    TODOS     = "todos"


@dataclass
class ReglaDescuento:
    cadena_id: str                           # "COTO", "JUMBO", etc.
    tipo: TipoPromo
    texto_original: str                      # Texto tal como aparece en el sitio

    # Alcance (si aplica a EAN específico o categoría)
    ean: str | None = None                   # None = aplica a toda la cadena
    categoria: str | None = None

    # Valores del descuento
    descuento_pct: float | None = None       # 20.0 → 20%
    factor_multiplicador: float | None = None # ej: 3x2 → 0.6667

    # Condiciones bancarias
    banco: str | None = None
    tarjeta: str | None = None
    medio_pago: str | None = None            # "credito", "debito", "qr"
    dia_semana: DiaSemana | None = None
    tope_reintegro: float | None = None      # ARS máximo de reintegro

    # Condiciones de fidelidad
    programa_fidelidad: str | None = None    # "Comunidad Coto", "Jumbo+", etc.

    # Vigencia
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None

    # Metadata
    capturado_en: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def calcular_precio_final(self, precio_lista: float) -> float:
        """Aplica la regla al precio de lista y devuelve el precio neto."""
        if self.factor_multiplicador is not None:
            precio_final = precio_lista * self.factor_multiplicador
        elif self.descuento_pct is not None:
            ahorro = precio_lista * (self.descuento_pct / 100)
            if self.tope_reintegro:
                ahorro = min(ahorro, self.tope_reintegro)
            precio_final = precio_lista - ahorro
        else:
            precio_final = precio_lista

        return round(precio_final, 2)

    def esta_vigente(self) -> bool:
        now = datetime.now(tz=timezone.utc)
        if self.fecha_inicio and now < self.fecha_inicio:
            return False
        if self.fecha_fin and now > self.fecha_fin:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "cadena_id": self.cadena_id,
            "tipo": self.tipo.value,
            "texto_original": self.texto_original,
            "ean": self.ean,
            "categoria": self.categoria,
            "descuento_pct": self.descuento_pct,
            "factor_multiplicador": self.factor_multiplicador,
            "banco": self.banco,
            "tarjeta": self.tarjeta,
            "medio_pago": self.medio_pago,
            "dia_semana": self.dia_semana.value if self.dia_semana else None,
            "tope_reintegro": self.tope_reintegro,
            "programa_fidelidad": self.programa_fidelidad,
            "fecha_inicio": self.fecha_inicio,
            "fecha_fin": self.fecha_fin,
            "capturado_en": self.capturado_en,
        }

