import asyncio
import logging
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence, Set, Tuple

from app.config import Settings
from app.enrichment.cache import SpecsCache
from app.enrichment.naming import device_key, product_display_name
from app.enrichment.specs import DeviceSpecs
from app.enrichment.throttle import SourceRateLimitedError, Throttle
from app.telcel import TelcelClient

logger = logging.getLogger(__name__)


class SpecsSource(Protocol):
    name: str
    throttle: Throttle

    async def lookup(self, brand: str, name: str, model_code: str) -> Optional[DeviceSpecs]:
        ...


class SpecsEnricher:
    """Obtiene especificaciones probando las fuentes en orden; el detalle de Telcel es el último recurso."""

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
            if previous and previous.specs.is_scraped and not specs.is_scraped:
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
                return specs, self._settings.specs_ttl_found_seconds

        # Si alguna fuente no pudo responder, el resultado parcial se guarda poco tiempo para reintentar pronto.
        ttl = self._settings.specs_ttl_rate_limited_seconds if interrupted else self._settings.specs_ttl_fallback_seconds
        return await self._telcel_fallback(product), ttl

    def _ordered_sources(self) -> Sequence[SpecsSource]:
        """Respeta la preferencia de fuentes, pero reparte la carga cuando la preferida acumula cola."""
        limit = max(1, self._settings.source_backlog_limit)
        return sorted(
            self._sources,
            key=lambda source: (source.throttle.is_cooling_down, source.throttle.backlog // limit),
        )

    async def _telcel_fallback(self, product: Dict[str, Any]) -> DeviceSpecs:
        detail: Optional[Dict[str, Any]] = None
        if product.get("code"):
            detail = await self._telcel.get_product_detail(product["code"])
        if not detail:
            return DeviceSpecs(source="none")

        chipset = " ".join(
            part for part in (detail.get("procesadorMarca"), detail.get("procesadorModelo")) if part
        ).strip()
        technology = (detail.get("tecnologia") or "").upper()
        return DeviceSpecs(
            source="telcel",
            matched_name=product_display_name(product),
            source_url=product.get("pdpUrl"),
            chipset=chipset or None,
            has_5g=("5G" in technology) if technology else None,
        )
