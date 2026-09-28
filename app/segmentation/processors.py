"""Clasificación de chipsets en familias de entrada, media y alta, más su aptitud para gaming."""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Sequence


class Tier(str, Enum):
    ENTRY = "entrada"
    MID = "media"
    HIGH = "alta"


@dataclass(frozen=True)
class ProcessorInfo:
    family: str
    tier: Optional[Tier]
    gaming: bool = False


UNKNOWN_PROCESSOR = ProcessorInfo(family="desconocido", tier=None)

_SNAPDRAGON_MODERN = re.compile(r"snapdragon\s*(\d)\s*(s|\+)?\s*(?:gen\s*\d+|elite)")
_SNAPDRAGON_LEGACY = re.compile(r"(?:snapdragon|sdm)\s*(\d{3})")
_QUALCOMM_PART = re.compile(r"\bsm(\d)(\d{3})")
_DIMENSITY = re.compile(r"dimensity\s*(\d{3,4})")
_EXYNOS = re.compile(r"exynos\s*(\d{3,4})")
_KIRIN = re.compile(r"kirin\s*(\d{3,4})")
_APPLE = re.compile(r"(?:apple|chip)\s+a(\d{1,2})\b|\ba(\d{2})\s+(?:bionic|pro|fusion)\b")
_UNISOC = re.compile(r"unisoc|spreadtrum|\btiger\s*t\d|\bt6\d\d\b")

# Números de parte Qualcomm SM6xxx que en realidad son chips de entrada (Snapdragon 662/665/680/685).
_QUALCOMM_ENTRY_PARTS = {"6115", "6125", "6225"}
# Números de parte de las variantes Snapdragon 7+ (7+ Gen 2 y 7+ Gen 3).
_QUALCOMM_GAMING_7_PARTS = {"7475", "7675"}


def _snapdragon_modern(text: str) -> Optional[ProcessorInfo]:
    match = _SNAPDRAGON_MODERN.search(text)
    if not match:
        return None
    series, variant = int(match.group(1)), match.group(2) or ""
    family = f"Snapdragon {series}{variant} Series"
    if series >= 8:
        return ProcessorInfo(family, Tier.HIGH, gaming=True)
    if series == 7:
        return ProcessorInfo(family, Tier.MID, gaming=variant == "+")
    if series == 6:
        return ProcessorInfo(family, Tier.MID)
    return ProcessorInfo(family, Tier.ENTRY)


def _snapdragon_legacy(text: str) -> Optional[ProcessorInfo]:
    match = _SNAPDRAGON_LEGACY.search(text)
    if not match:
        return None
    number = int(match.group(1))
    family = f"Snapdragon {number}"
    if number >= 800:
        return ProcessorInfo(family, Tier.HIGH if number >= 855 else Tier.MID, gaming=number >= 865)
    if number >= 690:
        return ProcessorInfo(family, Tier.MID)
    return ProcessorInfo(family, Tier.ENTRY)


def _qualcomm_part(text: str) -> Optional[ProcessorInfo]:
    match = _QUALCOMM_PART.search(text)
    if not match:
        return None
    series, part = int(match.group(1)), match.group(1) + match.group(2)
    family = f"Qualcomm SM{part}"
    if series >= 8:
        return ProcessorInfo(family, Tier.HIGH, gaming=True)
    if series == 7:
        return ProcessorInfo(family, Tier.MID, gaming=part in _QUALCOMM_GAMING_7_PARTS)
    if series == 6 and part not in _QUALCOMM_ENTRY_PARTS:
        return ProcessorInfo(family, Tier.MID)
    return ProcessorInfo(family, Tier.ENTRY)


def _dimensity(text: str) -> Optional[ProcessorInfo]:
    match = _DIMENSITY.search(text)
    if not match:
        return None
    number = int(match.group(1))
    family = f"Dimensity {number}"
    if number >= 9000:
        return ProcessorInfo(family, Tier.HIGH, gaming=True)
    if number >= 8000:
        return ProcessorInfo(family, Tier.MID, gaming=True)
    if number >= 7000:
        return ProcessorInfo(family, Tier.MID)
    if number >= 6000:
        return ProcessorInfo(family, Tier.ENTRY)
    # Nomenclatura anterior: Dimensity 700/800/810 (entrada), 900/920/1080/1200/1300 (media).
    return ProcessorInfo(family, Tier.MID if number >= 900 else Tier.ENTRY)


def _exynos(text: str) -> Optional[ProcessorInfo]:
    match = _EXYNOS.search(text)
    if not match:
        return None
    number = match.group(1)
    family = f"Exynos {number}"
    if (len(number) == 4 and number[0] in "29") or (len(number) == 3 and number[0] == "9"):
        return ProcessorInfo(family, Tier.HIGH)
    # Exynos 1330 rinde al nivel de Dimensity 6100 / Snapdragon 4 Gen 2; el resto de la serie 1000 es media.
    if len(number) == 4 and number[0] == "1" and number != "1330":
        return ProcessorInfo(family, Tier.MID)
    return ProcessorInfo(family, Tier.ENTRY)


def _kirin(text: str) -> Optional[ProcessorInfo]:
    match = _KIRIN.search(text)
    if not match:
        return None
    number = int(match.group(1))
    family = f"Kirin {number}"
    if number >= 9000 or 900 <= number < 1000:
        return ProcessorInfo(family, Tier.HIGH)
    if number >= 8000 or 800 <= number < 900:
        return ProcessorInfo(family, Tier.MID)
    return ProcessorInfo(family, Tier.ENTRY)


def _apple(text: str) -> Optional[ProcessorInfo]:
    match = _APPLE.search(text)
    if not match:
        return None
    generation = int(match.group(1) or match.group(2))
    # "Generaciones recientes" de iPhone: A15 Bionic (2021) en adelante.
    return ProcessorInfo(f"Apple A{generation}", Tier.HIGH if generation >= 15 else Tier.MID)


def _tensor(text: str) -> Optional[ProcessorInfo]:
    return ProcessorInfo("Google Tensor", Tier.HIGH) if "tensor" in text else None


def _helio(text: str) -> Optional[ProcessorInfo]:
    return ProcessorInfo("MediaTek Helio", Tier.ENTRY) if "helio" in text or re.search(r"\bmt6\d{3}", text) else None


def _unisoc(text: str) -> Optional[ProcessorInfo]:
    return ProcessorInfo("UNISOC", Tier.ENTRY) if _UNISOC.search(text) else None


# El orden importa: p. ej. "Mediatek MT6835 Dimensity 6100+" debe resolverse como Dimensity antes que como MT6xxx.
_PARSERS: Sequence[Callable[[str], Optional[ProcessorInfo]]] = (
    _apple,
    _snapdragon_modern,
    _snapdragon_legacy,
    _qualcomm_part,
    _dimensity,
    _exynos,
    _kirin,
    _tensor,
    _helio,
    _unisoc,
)


def classify_processor(chipset: Optional[str]) -> ProcessorInfo:
    if not chipset:
        return UNKNOWN_PROCESSOR
    text = chipset.lower().replace(" plus", "+")
    for parser in _PARSERS:
        info = parser(text)
        if info:
            return info
    return ProcessorInfo(family=chipset, tier=None)
