from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.enrichment.naming import ram_from_name, storage_gb
from app.enrichment.specs import DeviceSpecs
from app.segmentation.processors import ProcessorInfo, classify_processor


@dataclass(frozen=True)
class DeviceProfile:
    """Vista normalizada de un equipo concreto (con su almacenamiento) lista para evaluar reglas."""

    processor: ProcessorInfo
    chipset: Optional[str]
    ram_gb: Optional[float]
    storage_gb: Optional[int]
    display_tech: Optional[str]
    refresh_rate_hz: Optional[int]
    has_5g: Optional[bool]
    battery_mah: Optional[int]
    gaming_features: List[str] = field(default_factory=list)
    specs_source: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chipset": self.chipset,
            "processorFamily": self.processor.family,
            "processorTier": self.processor.tier.value if self.processor.tier else None,
            "processorGaming": self.processor.gaming,
            "ramGb": self.ram_gb,
            "storageGb": self.storage_gb,
            "displayTech": self.display_tech,
            "refreshRateHz": self.refresh_rate_hz,
            "has5g": self.has_5g,
            "batteryMah": self.battery_mah,
            "gamingFeatures": self.gaming_features,
            "specsSource": self.specs_source,
        }


def display_technology(display_type: Optional[str]) -> Optional[str]:
    if not display_type:
        return None
    text = display_type.upper()
    if "OLED" in text:
        return "OLED"
    if any(token in text for token in ("LCD", "IPS", "TFT", "PLS")):
        return "LCD"
    return None


def resolve_ram(product: Dict[str, Any], specs: DeviceSpecs, storage: Optional[int]) -> Optional[float]:
    from_name = ram_from_name(product)
    if from_name:
        return from_name
    options = specs.ram_options or {}
    if storage is not None and str(storage) in options:
        # Si una capacidad se vende con varias RAM, se toma la menor: es la configuración base y la más conservadora.
        return min(options[str(storage)])
    all_values = [ram for values in options.values() for ram in values]
    return min(all_values) if all_values else None


def build_profile(product: Dict[str, Any], specs: DeviceSpecs) -> DeviceProfile:
    storage = storage_gb(product)
    return DeviceProfile(
        processor=classify_processor(specs.chipset),
        chipset=specs.chipset,
        ram_gb=resolve_ram(product, specs, storage),
        storage_gb=storage,
        display_tech=display_technology(specs.display_type),
        refresh_rate_hz=specs.refresh_rate_hz,
        has_5g=specs.has_5g,
        battery_mah=specs.battery_mah,
        gaming_features=list(specs.gaming_features or []),
        specs_source=specs.source,
    )
