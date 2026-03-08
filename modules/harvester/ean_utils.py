"""
Utilidades para validación y normalización de EANs/GTINs.
"""

import re
import unicodedata


def validate_gtin(code: str) -> bool:
    """
    Valida si un código es un GTIN real (GTIN-8 o GTIN-13) usando el check digit GS1.

    El último dígito es el check digit. Si la validación falla, el código es un ID
    interno del retailer (e.g. SKU interno de Coto) y no un código de barras universal.
    """
    if not code or not code.isdigit() or len(code) not in (8, 13):
        return False

    digits = [int(d) for d in code]
    check = digits[-1]
    body = digits[:-1]

    # Desde el extremo derecho del body, alternar x3 y x1
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    expected = (10 - (total % 10)) % 10
    return check == expected


def is_internal_coto_id(ean: str) -> bool:
    """
    Returns True si el EAN parece ser un SKU interno de Coto (no un GTIN real).
    Un ID es interno si falla la validación GTIN o si empieza con '00' (prefijo interno).
    """
    if not validate_gtin(ean):
        return True
    # IDs Coto internos suelen empezar con "00" para GTIN-8
    if len(ean) == 8 and ean.startswith("00"):
        return True
    return False


def slugify(text: str, max_len: int = 60) -> str:
    """Convierte un nombre de producto en un slug para URL."""
    # Normalizar unicode (quitar acentos)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    # Lowercase, reemplazar no-alfanuméricos con guion
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len]
