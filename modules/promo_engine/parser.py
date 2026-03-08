"""
Módulo 3 — The Promo Engine
Parser NLP/Regex: transforma texto libre de promociones en ReglaDescuento estructurada.

Ejemplos de texto que parsea:
  "20% de descuento con Banco Nación los lunes y martes"
  "2da unidad al 70%"
  "3x2 en toda la línea"
  "Precio exclusivo Comunidad Coto"
  "25% de ahorro con Visa Débito, tope $5.000"
  "Hasta 30% OFF pagando con QR Mercado Pago"
"""

import re
from datetime import datetime, timezone

from modules.promo_engine.models import DiaSemana, ReglaDescuento, TipoPromo

# ---------------------------------------------------------------------------
# Patrones de extracción
# ---------------------------------------------------------------------------

_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_TOPE_RE = re.compile(r"tope\s*\$?\s*([\d.,]+)", re.IGNORECASE)

_MULTI_3X2 = re.compile(r"3\s*[xX×]\s*2", re.IGNORECASE)
_MULTI_2ND = re.compile(
    r"(?:2da?|segunda)\s+unidad\s+al\s+(\d+(?:[.,]\d+)?)\s*%", re.IGNORECASE
)
_MULTI_NXM = re.compile(r"(\d+)\s*[xX×]\s*(\d+)", re.IGNORECASE)

_DIAS: dict[str, DiaSemana] = {
    "lunes": DiaSemana.LUNES,
    "martes": DiaSemana.MARTES,
    "miércoles": DiaSemana.MIERCOLES,
    "miercoles": DiaSemana.MIERCOLES,
    "jueves": DiaSemana.JUEVES,
    "viernes": DiaSemana.VIERNES,
    "sábado": DiaSemana.SABADO,
    "sabado": DiaSemana.SABADO,
    "domingo": DiaSemana.DOMINGO,
}

_BANCOS: list[str] = [
    "Banco Nación", "Banco Provincia", "Banco Ciudad", "Banco Galicia",
    "Banco Santander", "Banco BBVA", "Banco HSBC", "Banco Macro",
    "Banco Supervielle", "Banco Patagonia", "Banco Hipotecario",
    "Banco Comafi", "ICBC", "Brubank", "Mercado Pago", "Naranja X",
    "Ualá", "Personal Pay", "Cuenta DNI", "MODO", "BUEPP",
]

_TARJETAS: list[str] = [
    "Visa", "Mastercard", "American Express", "Amex", "Cabal",
    "Naranja", "Tarjeta Shopping", "Tarjeta Nevada",
]

_MEDIOS: dict[str, str] = {
    "débito": "debito", "debito": "debito",
    "crédito": "credito", "credito": "credito",
    "qr": "qr",
}

_FIDELIDAD: dict[str, str] = {
    "comunidad coto": "Comunidad Coto",
    "mi carrefour": "Mi Carrefour",
    "club la nación": "Club La Nación",
    "club la nacion": "Club La Nación",
    "jumbo+": "Jumbo+",
    "disco +": "Disco+",
    "vea más": "Vea Más",
    "clarin 365": "Clarín 365",
    "365": "Clarín 365",
    "mas online": "ChangoMas",
}


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def parse_promo_text(
    texto: str,
    cadena_id: str,
    ean: str | None = None,
    categoria: str | None = None,
) -> ReglaDescuento | None:
    """
    Intenta parsear un texto de promoción y devolver una ReglaDescuento.
    Retorna None si no se puede extraer información útil.
    """
    texto_lower = texto.lower()

    # --- Fidelidad (verificar primero para no confundir con bancaria) ---
    for key, nombre in _FIDELIDAD.items():
        if key in texto_lower:
            pct = _extract_pct(texto)
            return ReglaDescuento(
                cadena_id=cadena_id,
                tipo=TipoPromo.FIDELIDAD,
                texto_original=texto,
                ean=ean,
                categoria=categoria,
                programa_fidelidad=nombre,
                descuento_pct=pct,
                factor_multiplicador=_pct_to_factor(pct) if pct else None,
            )

    # --- Multi-unidad 3x2 ---
    if _MULTI_3X2.search(texto):
        return ReglaDescuento(
            cadena_id=cadena_id,
            tipo=TipoPromo.MULTI_UNIT,
            texto_original=texto,
            ean=ean,
            categoria=categoria,
            factor_multiplicador=round(2 / 3, 6),  # pagas 2 llevas 3
        )

    # --- Multi-unidad Nda unidad al X% ---
    m2nd = _MULTI_2ND.search(texto)
    if m2nd:
        pct_2da = float(m2nd.group(1).replace(",", "."))
        # Precio promedio de 2 unidades: (100% + pct_2da%) / 200
        factor = round((100 + pct_2da) / 200, 6)
        return ReglaDescuento(
            cadena_id=cadena_id,
            tipo=TipoPromo.MULTI_UNIT,
            texto_original=texto,
            ean=ean,
            categoria=categoria,
            factor_multiplicador=factor,
            descuento_pct=pct_2da,
        )

    # --- Multi-unidad NxM genérico ---
    mnm = _MULTI_NXM.search(texto)
    if mnm:
        n, m = int(mnm.group(1)), int(mnm.group(2))
        if n > 0 and m < n:
            factor = round(m / n, 6)
            return ReglaDescuento(
                cadena_id=cadena_id,
                tipo=TipoPromo.MULTI_UNIT,
                texto_original=texto,
                ean=ean,
                categoria=categoria,
                factor_multiplicador=factor,
            )

    # --- Bancaria ---
    banco = _find_banco(texto)
    tarjeta = _find_tarjeta(texto)
    medio = _find_medio(texto_lower)
    dia = _find_dia(texto_lower)
    tope = _extract_tope(texto)
    pct = _extract_pct(texto)

    if banco or tarjeta or medio:
        return ReglaDescuento(
            cadena_id=cadena_id,
            tipo=TipoPromo.BANCARIA,
            texto_original=texto,
            ean=ean,
            categoria=categoria,
            descuento_pct=pct,
            factor_multiplicador=_pct_to_factor(pct) if pct else None,
            banco=banco,
            tarjeta=tarjeta,
            medio_pago=medio,
            dia_semana=dia,
            tope_reintegro=tope,
        )

    # --- Directa ---
    if pct:
        return ReglaDescuento(
            cadena_id=cadena_id,
            tipo=TipoPromo.DIRECTA,
            texto_original=texto,
            ean=ean,
            categoria=categoria,
            descuento_pct=pct,
            factor_multiplicador=_pct_to_factor(pct),
        )

    return None


def calcular_precio_neto(
    precio_lista: float,
    reglas: list[ReglaDescuento],
    tarjetas_usuario: list[str] | None = None,
    programas_usuario: list[str] | None = None,
) -> float:
    """
    Aplica las reglas aplicables al usuario y devuelve el mejor precio neto.
    Solo aplica reglas vigentes y compatibles con las tarjetas/programas del usuario.
    """
    mejor_precio = precio_lista

    for regla in reglas:
        if not regla.esta_vigente():
            continue

        # Verificar compatibilidad con el perfil del usuario
        if regla.tipo == TipoPromo.BANCARIA:
            if tarjetas_usuario is not None:
                match = any(
                    t.lower() in (regla.banco or "").lower()
                    or t.lower() in (regla.tarjeta or "").lower()
                    for t in tarjetas_usuario
                )
                if not match:
                    continue

        if regla.tipo == TipoPromo.FIDELIDAD:
            if programas_usuario is not None:
                if regla.programa_fidelidad not in programas_usuario:
                    continue

        precio_aplicado = regla.calcular_precio_final(precio_lista)
        if precio_aplicado < mejor_precio:
            mejor_precio = precio_aplicado

    return mejor_precio


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _extract_pct(texto: str) -> float | None:
    m = _PCT_RE.search(texto)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _pct_to_factor(pct: float) -> float:
    return round(1 - pct / 100, 6)


def _extract_tope(texto: str) -> float | None:
    m = _TOPE_RE.search(texto)
    if m:
        raw = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _find_banco(texto: str) -> str | None:
    for banco in _BANCOS:
        if banco.lower() in texto.lower():
            return banco
    return None


def _find_tarjeta(texto: str) -> str | None:
    for tarjeta in _TARJETAS:
        if tarjeta.lower() in texto.lower():
            return tarjeta
    return None


def _find_medio(texto_lower: str) -> str | None:
    for key, val in _MEDIOS.items():
        if key in texto_lower:
            return val
    return None


def _find_dia(texto_lower: str) -> DiaSemana | None:
    for key, dia in _DIAS.items():
        if key in texto_lower:
            return dia
    return None
