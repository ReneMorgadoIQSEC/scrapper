from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SPEC_FIELDS = ("chipset", "ram_options", "display_type", "refresh_rate_hz", "has_5g", "battery_mah", "gaming_features")
# Campos sin los que la segmentación queda incompleta; gaming_features vacío es un resultado válido.
REQUIRED_FIELDS = SPEC_FIELDS[:-1]


def is_empty(value: Any) -> bool:
    return value is None or value == {} or value == []


@dataclass
class DeviceSpecs:
    """Características técnicas de un dispositivo, independientes de la variante de almacenamiento."""

    # "telcel", "gsmarena", "nanoreview", combinaciones como "telcel+gsmarena", o "none".
    source: str
    matched_name: Optional[str] = None
    # Ficha técnica externa usada como respaldo; None si todo vino de Telcel.
    source_url: Optional[str] = None
    chipset: Optional[str] = None
    # Almacenamiento en GB (como texto para poder serializar a JSON) -> opciones de RAM física en GB.
    ram_options: Dict[str, List[float]] = field(default_factory=dict)
    display_type: Optional[str] = None
    refresh_rate_hz: Optional[int] = None
    has_5g: Optional[bool] = None
    battery_mah: Optional[int] = None
    gaming_features: List[str] = field(default_factory=list)

    @property
    def missing_fields(self) -> List[str]:
        return [name for name in REQUIRED_FIELDS if is_empty(getattr(self, name))]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceSpecs":
        known = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        return cls(**known)
