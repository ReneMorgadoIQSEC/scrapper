from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeviceSpecs:
    """Características técnicas de un dispositivo, independientes de la variante de almacenamiento."""

    source: str
    matched_name: Optional[str] = None
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
    def is_scraped(self) -> bool:
        """True si viene de una ficha técnica completa y no del respaldo parcial de Telcel."""
        return self.source not in ("telcel", "none")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceSpecs":
        known = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        return cls(**known)
