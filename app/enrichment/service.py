import asyncio
import logging
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Set, Tuple

from app.config import Settings
from app.enrichment.cache import SpecsCache
from app.enrichment.naming import device_key, product_display_name
from app.enrichment.specs import DeviceSpecs, is_empty
from app.enrichment.telcel_specs import parse_telcel_detail
from app.enrichment.throttle import SourceRateLimitedError, Throttle
from app.segmentation.processors import classify_processor
from app.telcel import TelcelClient

logger = logging.getLogger(__name__)


class SpecsSource(Protocol):
    name: str
    throttle: Throttle

    async def lookup(self, brand: str, name: str, model_code: str) -> Optional[DeviceSpecs]:
        ...


def missing_for_segmentation(specs: DeviceSpecs) -> List[str]:
    missing = specs.missing_fields
    # Telcel a veces reporta solo un código interno (p. ej. "MTK-25M+") que no permite ubicar la gama.
    if specs.chipset and classify_processor(specs.chipset).tier is None:
        missing.insert(0, "chipset")
    return missing


def fill_gaps(primary: DeviceSpecs, fallback: DeviceSpecs) -> DeviceSpecs:
    gaps = missing_for_segmentation(primary)
    if not primary.gaming_features:
        gaps.append("gaming_features")
    values = {name: getattr(fallback, name) for name in gaps if not is_empty(getattr(fallback, name))}
    source = fallback.source if primary.source == "none" else f"{primary.source}+{fallback.source}"
    return replace(primary, source=source, matched_name=fallback.matched_name, source_url=fallback.source_url, **values)


class SpecsEnricher:
    """Toma las especificaciones del detalle de Telcel y completa los huecos con las fuentes externas, en orden."""

    def __init__(self, sources: Sequence[SpecsSource], telcel: TelcelClient, cache: SpecsCache, settings: Settings):
        self._sources = sources
        self._telcel = telcel
        self._cache = cache
        self._settings = settings
        self._inflight: Dict[str, "asyncio.Future[DeviceSpecs]"] = {}
        self._background: Set["asyncio.Task[DeviceSpecs]"] = set()

    async def enrich_many(self, products: Iterable[Dict[str, Any]]) -> Dict[str, DeviceSpecs]:
        unique: Dict[str, Dict[str, Any]] = {}
        for product in products:
            unique.setdefault(device_key(product), product)
        specs = await asyncio.gather(*(self.get_specs(product) for product in unique.values()))
        self._cache.save()
        return dict(zip(unique.keys(), specs))

    async def get_specs(self, product: Dict[str, Any]) -> DeviceSpecs:
        cached = self._cache.get(device_key(product))
        if cached is None:
            return await self._fetch(product)
        if cached.stale:
            self._refresh_in_background(product)
        return cached.specs

    def _refresh_in_background(self, product: Dict[str, Any]) -> None:
        if device_key(product) in self._inflight:
            return
        task = asyncio.ensure_future(self._fetch(product))
        self._background.add(task)
        task.add_done_callback(self._on_background_done)

    def _on_background_done(self, task: "asyncio.Task[DeviceSpecs]") -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception() is None:
            self._cache.save()

    async def _fetch(self, product: Dict[str, Any]) -> DeviceSpecs:
        key = device_key(product)
        # Varias variantes (colores) o peticiones simultáneas comparten un único scraping por equipo.
        inflight = self._inflight.get(key)
        if inflight:
            return await asyncio.shield(inflight)

        future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            specs, ttl = await self._resolve(product)
            previous = self._cache.get(key)
            if previous and len(previous.specs.missing_fields) < len(specs.missing_fields):
                specs = previous.specs
            self._cache.set(key, specs, ttl)
            future.set_result(specs)
            return specs
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            # Evita el aviso de "excepción nunca recuperada" cuando nadie más esperaba este future.
            future.exception()
            raise
        finally:
            self._inflight.pop(key, None)

    async def _resolve(self, product: Dict[str, Any]) -> Tuple[DeviceSpecs, int]:
        primary, telcel_answered = await self._telcel_specs(product)
        if telcel_answered and not missing_for_segmentation(primary):
            return primary, self._settings.specs_ttl_found_seconds

        fallback, interrupted = await self._lookup_fallback(product)
        if fallback:
            return fill_gaps(primary, fallback), self._settings.specs_ttl_found_seconds

        # Si alguna fuente no pudo responder, el resultado parcial se guarda poco tiempo para reintentar pronto.
        interrupted = interrupted or not telcel_answered
        ttl = self._settings.specs_ttl_rate_limited_seconds if interrupted else self._settings.specs_ttl_fallback_seconds
        return primary, ttl

    async def _telcel_specs(self, product: Dict[str, Any]) -> Tuple[DeviceSpecs, bool]:
        detail: Optional[Dict[str, Any]] = None
        if product.get("code"):
            detail = await self._telcel.get_product_detail(product["code"])
        if not detail:
            return DeviceSpecs(source="none"), False
        return parse_telcel_detail(detail, product), True

    async def _lookup_fallback(self, product: Dict[str, Any]) -> Tuple[Optional[DeviceSpecs], bool]:
        name = product_display_name(product)
        brand, model_code = product.get("marca") or "", product.get("modelo") or ""
        interrupted = False

        for source in self._ordered_sources():
            try:
                specs = await source.lookup(brand, name, model_code)
            except SourceRateLimitedError:
                logger.info("%s en pausa por límite de peticiones; se omite para '%s'", source.name, name)
                interrupted = True
                continue
            except Exception:
                logger.warning("Error consultando %s para '%s'", source.name, name, exc_info=True)
                interrupted = True
                continue
            if specs:
                return specs, interrupted
        return None, interrupted

    def _ordered_sources(self) -> Sequence[SpecsSource]:
        """Respeta la preferencia de fuentes, pero reparte la carga cuando la preferida acumula cola."""
        limit = max(1, self._settings.source_backlog_limit)
        return sorted(
            self._sources,
            key=lambda source: (source.throttle.is_cooling_down, source.throttle.backlog // limit),
        )
