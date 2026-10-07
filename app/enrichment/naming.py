import re
from typing import Any, Dict, List, Optional

BRAND_ALIASES = {
    "TECNOMOBILE": "tecno",
    "TECNO MOBILE": "tecno",
}

_BUNDLE_SEPARATOR = re.compile(r"\s\+\s")
_STORAGE_RAM_PATTERN = re.compile(r"\b(\d+)\s*/\s*(\d+)\s*GB\b", re.IGNORECASE)
_STORAGE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(GB|TB)\b", re.IGNORECASE)
_NETWORK_TOKENS = {"4g", "5g", "lte"}


def product_display_name(product: Dict[str, Any]) -> str:
    return (product.get("nombreComercial") or product.get("name") or "").strip()


def brand_for_search(brand: str) -> str:
    brand = (brand or "").strip()
    return BRAND_ALIASES.get(brand.upper(), brand.lower())


def is_bundle(name: str) -> bool:
    return bool(_BUNDLE_SEPARATOR.search(name or ""))


def clean_model_name(name: str) -> str:
    """Quita almacenamiento, RAM y accesorios de regalo del nombre comercial de Telcel."""
    name = _BUNDLE_SEPARATOR.split(name, maxsplit=1)[0]
    name = _STORAGE_RAM_PATTERN.sub(" ", name)
    name = _STORAGE_PATTERN.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


def search_query(brand: str, name: str) -> str:
    """Consulta para el buscador: marca + modelo, sin tokens de red (GSMArena no los incluye en el nombre)."""
    brand = brand_for_search(brand)
    tokens = [token for token in clean_model_name(name).split() if token.lower() not in _NETWORK_TOKENS]
    model = " ".join(tokens)
    if brand and not model.lower().startswith(brand):
        model = f"{brand} {model}"
    return model.strip()


def device_key(product: Dict[str, Any]) -> str:
    """Identifica al dispositivo sin importar color ni almacenamiento, para compartir el scraping entre variantes."""
    brand = brand_for_search(product.get("marca") or "")
    return f"{brand}|{clean_model_name(product_display_name(product)).lower()}"


def listing_key(product: Dict[str, Any]) -> str:
    """Identifica una publicación visible (misma marca y nombre comercial = mismo equipo en otro color)."""
    return f"{(product.get('marca') or '').lower()}|{product_display_name(product).lower()}"


def storage_gb(product: Dict[str, Any]) -> Optional[int]:
    capacity = product.get("capacidad")
    candidates: List[str] = []
    if isinstance(capacity, dict) and capacity.get("value"):
        unit = capacity.get("unit") or ""
        candidates.append(f"{capacity['value']} {unit}".strip())
    candidates.append(product_display_name(product))

    for text in candidates:
        match = _STORAGE_RAM_PATTERN.search(text)
        if match:
            return int(match.group(1))
        match = _STORAGE_PATTERN.search(text)
        if match:
            value = float(match.group(1))
            return int(value * 1024) if match.group(2).upper() == "TB" else int(value)
        if text.strip().isdigit():
            return int(text.strip())
    return None


def ram_from_name(product: Dict[str, Any]) -> Optional[float]:
    """Algunos nombres de Telcel incluyen la RAM, p. ej. 'Redmi 15C 256/4GB'."""
    match = _STORAGE_RAM_PATTERN.search(product_display_name(product))
    return float(match.group(2)) if match else None


def mentions_network(name: str, network: str) -> bool:
    return network.lower() in {token.lower() for token in re.split(r"[^\w]+", name)}


def normalize_model_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())
