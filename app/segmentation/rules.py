"""Reglas de segmentación (ver Clasificacion.txt).

Cada segmento se evalúa como un conjunto de criterios ponderados. El procesador pesa más que cualquier otra
característica, de modo que una especificación superior aislada (p. ej. 256 GB) no basta para subir de gama,
pero tampoco se descarta un equipo por no cumplir un criterio marcado como "generalmente".
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from app.segmentation.processors import Tier
from app.segmentation.profile import DeviceProfile

Check = Callable[[DeviceProfile], Optional[bool]]


class Segment(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    GAMER = "gamer"


@dataclass(frozen=True)
class Criterion:
    name: str
    weight: float
    check: Check
    required: bool = False


@dataclass(frozen=True)
class SegmentRule:
    segment: Segment
    title: str
    criteria: Tuple[Criterion, ...]
    threshold: float
    min_coverage: float
    is_tier: bool


@dataclass
class SegmentScore:
    score: float
    coverage: float
    eligible: bool
    met: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)


@dataclass
class Classification:
    segments: List[Segment]
    scores: Dict[Segment, SegmentScore]

    def to_dict(self) -> dict:
        return {
            "segments": [segment.value for segment in self.segments],
            "scores": {
                segment.value: {
                    "score": round(result.score, 3),
                    "coverage": round(result.coverage, 3),
                    "eligible": result.eligible,
                    "met": result.met,
                    "failed": result.failed,
                    "unknown": result.unknown,
                }
                for segment, result in self.scores.items()
            },
        }


def _when(value, predicate) -> Optional[bool]:
    return None if value is None else bool(predicate(value))


def processor_tier(tier: Tier) -> Check:
    return lambda p: _when(p.processor.tier, lambda value: value == tier)


def ram_at_most(gb: float) -> Check:
    return lambda p: _when(p.ram_gb, lambda value: value <= gb)


def ram_at_least(gb: float) -> Check:
    return lambda p: _when(p.ram_gb, lambda value: value >= gb)


def storage_between(low: int, high: int) -> Check:
    return lambda p: _when(p.storage_gb, lambda value: low <= value <= high)


def storage_at_least(gb: int) -> Check:
    return lambda p: _when(p.storage_gb, lambda value: value >= gb)


def display_is(tech: str) -> Check:
    return lambda p: _when(p.display_tech, lambda value: value == tech)


def refresh_at_most(hz: int) -> Check:
    return lambda p: _when(p.refresh_rate_hz, lambda value: value <= hz)


def refresh_at_least(hz: int) -> Check:
    return lambda p: _when(p.refresh_rate_hz, lambda value: value >= hz)


def advanced_display(p: DeviceProfile) -> Optional[bool]:
    """OLED/AMOLED, o LCD "avanzada" (alta frecuencia de actualización)."""
    if p.display_tech == "OLED":
        return True
    if p.display_tech == "LCD" and p.refresh_rate_hz is not None:
        return p.refresh_rate_hz >= 90
    return None if p.display_tech is None else False


def has_5g(p: DeviceProfile) -> Optional[bool]:
    return p.has_5g


def gaming_processor(p: DeviceProfile) -> Optional[bool]:
    return None if p.processor.tier is None else p.processor.gaming


def battery_at_least(mah: int) -> Check:
    return lambda p: _when(p.battery_mah, lambda value: value >= mah)


def gaming_features(p: DeviceProfile) -> Optional[bool]:
    return bool(p.gaming_features)


RULES: Dict[Segment, SegmentRule] = {
    Segment.BAJA: SegmentRule(
        segment=Segment.BAJA,
        title="Gama Baja",
        criteria=(
            Criterion("procesador de entrada", 3, processor_tier(Tier.ENTRY)),
            Criterion("RAM hasta 4 GB", 1, ram_at_most(4)),
            Criterion("almacenamiento 32-128 GB", 0.5, storage_between(32, 128)),
            Criterion("pantalla LCD", 1, display_is("LCD")),
            Criterion("60-90 Hz", 0.5, refresh_at_most(90)),
        ),
        threshold=0.65,
        min_coverage=0.5,
        is_tier=True,
    ),
    Segment.MEDIA: SegmentRule(
        segment=Segment.MEDIA,
        title="Gama Media",
        criteria=(
            Criterion("procesador de gama media", 3, processor_tier(Tier.MID)),
            Criterion("RAM de 6 GB o más", 1, ram_at_least(6)),
            Criterion("almacenamiento de 128 GB o más", 1, storage_at_least(128)),
            Criterion("LCD avanzada u OLED", 1, advanced_display),
            Criterion("90 Hz o más", 1, refresh_at_least(90)),
            Criterion("5G", 0.5, has_5g),
        ),
        threshold=0.65,
        min_coverage=0.5,
        is_tier=True,
    ),
    Segment.ALTA: SegmentRule(
        segment=Segment.ALTA,
        title="Gama Alta",
        criteria=(
            Criterion("procesador de gama alta", 3, processor_tier(Tier.HIGH)),
            Criterion("RAM de 8 GB o más", 1, ram_at_least(8)),
            Criterion("almacenamiento de 256 GB o más", 0.5, storage_at_least(256)),
            Criterion("pantalla OLED", 1, display_is("OLED")),
            Criterion("120 Hz o más", 0.5, refresh_at_least(120)),
            Criterion("5G", 1, has_5g),
        ),
        threshold=0.65,
        min_coverage=0.5,
        is_tier=True,
    ),
    Segment.GAMER: SegmentRule(
        segment=Segment.GAMER,
        title="Gamer",
        criteria=(
            Criterion("procesador apto para gaming", 3, gaming_processor, required=True),
            Criterion("RAM de 8 GB o más", 1, ram_at_least(8), required=True),
            Criterion("120 Hz o más", 1, refresh_at_least(120), required=True),
            Criterion("batería de 5,000 mAh o más", 0.5, battery_at_least(5000)),
            Criterion("características gaming dedicadas", 0.5, gaming_features),
        ),
        threshold=0.7,
        min_coverage=0.7,
        is_tier=False,
    ),
}


def evaluate(rule: SegmentRule, profile: DeviceProfile) -> SegmentScore:
    total = sum(criterion.weight for criterion in rule.criteria)
    known_weight = met_weight = 0.0
    result = SegmentScore(score=0.0, coverage=0.0, eligible=False)
    required_ok = True

    for criterion in rule.criteria:
        outcome = criterion.check(profile)
        if outcome is None:
            result.unknown.append(criterion.name)
            required_ok = required_ok and not criterion.required
            continue
        known_weight += criterion.weight
        if outcome:
            met_weight += criterion.weight
            result.met.append(criterion.name)
        else:
            result.failed.append(criterion.name)
            required_ok = required_ok and not criterion.required

    result.coverage = known_weight / total if total else 0.0
    result.score = met_weight / known_weight if known_weight else 0.0
    result.eligible = required_ok and result.coverage >= rule.min_coverage and result.score >= rule.threshold
    return result


def classify(profile: DeviceProfile) -> Classification:
    scores = {segment: evaluate(rule, profile) for segment, rule in RULES.items()}
    segments = [segment for segment, result in scores.items() if result.eligible]

    tier_segments = [segment for segment, rule in RULES.items() if rule.is_tier]
    if not any(segment in segments for segment in tier_segments):
        # Todo equipo con información suficiente pertenece al menos a una gama: la que mejor encaje.
        candidates = [
            segment for segment in tier_segments
            if scores[segment].coverage >= RULES[segment].min_coverage and scores[segment].score > 0
        ]
        if candidates:
            best = max(candidates, key=lambda segment: scores[segment].score)
            segments.insert(0, best)

    return Classification(segments=segments, scores=scores)
