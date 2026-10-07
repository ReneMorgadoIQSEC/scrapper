"""Especificaciones a partir del detalle de producto de Telcel: campos estructurados más el texto comercial."""
import html
import re
from typing import Any, Dict, List, Optional

from app.enrichment.naming import is_bundle, product_display_name, storage_gb
from app.enrichment.specs import SPEC_FIELDS, DeviceSpecs, is_empty

_TEXT_FIELDS = ("description", "slogan", "descripcionSeo")
_TAGS = re.compile(r"<[^>]+>")
# "4.5G" es LTE avanzado, no 5G.
_FIVE_G = re.compile(r"(?<![\d.])5G\b", re.IGNORECASE)
_HZ = re.compile(r"\b(\d{2,3})\s*Hz\b(?!\s*(?:PWM|de muestreo|táctil))", re.IGNORECASE)
_MAH = re.compile(r"\b(\d{1,2}(?:[ ,.]\d{3}|\d{3}))\s*mAh\b", re.IGNORECASE)
# La RAM "dinámica"/"virtual" es almacenamiento prestado, y "hasta X GB" suele mezclar variantes o RAM virtual.
_RAM = re.compile(
    r"(?<!hasta )\b(?:(\d{1,2})\s*GB\s+(?:de\s+)?RAM|RAM\s+de\s+(\d{1,2})\s*GB)\b"
    r"(?!\s+(?:dinámica|virtual|extendida|boost))",
    re.IGNORECASE,
)
_DISPLAY = re.compile(r"\b(?:LTPO\s+)?(?:Super\s+)?(?:AMOLED|P?OLED|LCD|IPS)\b", re.IGNORECASE)
_GAMING_KEYWORDS = ("cámara de vapor", "enfriamiento líquido", "refrigeración líquida", "gatillos")
_REFRESH_RANGE = range(60, 166)
_BATTERY_RANGE = range(1000, 15001)


def parse_telcel_detail(detail: Dict[str, Any], product: Dict[str, Any]) -> DeviceSpecs:
    technology = (detail.get("tecnologia") or "").strip()
    specs = DeviceSpecs(
        source="telcel",
        matched_name=product_display_name(product),
        chipset=_chipset(detail),
        has_5g=bool(_FIVE_G.search(technology)) if technology else None,
    )
    # En paquetes (equipo + TV, tablet...) el texto describe también el regalo y sus cifras no son confiables.
    if not is_bundle(product_display_name(detail) or product_display_name(product)):
        _apply_marketing_text(specs, _plain_text(detail), storage_gb(detail) or storage_gb(product))
    if all(is_empty(getattr(specs, name)) for name in SPEC_FIELDS):
        specs.source = "none"
    return specs


def _chipset(detail: Dict[str, Any]) -> Optional[str]:
    brand = (detail.get("procesadorMarca") or "").strip()
    model = (detail.get("procesadorModelo") or "").strip()
    if brand and brand.lower() in model.lower():
        brand = ""
    return " ".join(part for part in (brand, model) if part) or None


def _plain_text(detail: Dict[str, Any]) -> str:
    raw = " ".join(str(detail.get(name) or "") for name in _TEXT_FIELDS)
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", raw)))


def _single(values: List[int]) -> Optional[int]:
    """Solo se acepta un dato si el texto no se contradice (p. ej. '7700mAh' y '8,000 mAh' en la misma ficha)."""
    distinct = set(values)
    return distinct.pop() if len(distinct) == 1 else None


def _apply_marketing_text(specs: DeviceSpecs, text: str, storage: Optional[int]) -> None:
    refresh_rates = [int(value) for value in _HZ.findall(text) if int(value) in _REFRESH_RANGE]
    batteries = [int(re.sub(r"\D", "", value)) for value in _MAH.findall(text)]
    rams = [int(first or second) for first, second in _RAM.findall(text)]
    display = _DISPLAY.search(text)
    lowered = text.lower()

    specs.refresh_rate_hz = max(refresh_rates) if refresh_rates else None
    specs.battery_mah = _single([value for value in batteries if value in _BATTERY_RANGE])
    ram = _single(rams)
    specs.ram_options = {str(storage or 0): [float(ram)]} if ram else {}
    specs.display_type = re.sub(r"\s+", " ", display.group(0)) if display else None
    specs.gaming_features = [keyword for keyword in _GAMING_KEYWORDS if keyword in lowered]
