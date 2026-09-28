import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.config import Settings
from app.enrichment.naming import device_key, listing_key, product_display_name
from app.enrichment.service import SpecsEnricher
from app.enrichment.specs import DeviceSpecs
from app.segmentation.profile import DeviceProfile, build_profile
from app.segmentation.rules import Segment, classify
from app.telcel import TelcelClient, TelcelPage

logger = logging.getLogger(__name__)


@dataclass
class CatalogResult:
    segment: Segment
    products: List[Dict[str, Any]]
    pages_consulted: int
    elapsed_seconds: float
    debug: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class _Selection:
    segment: Segment
    limit: int
    debug: bool
    products: List[Dict[str, Any]] = field(default_factory=list)
    debug_rows: List[Dict[str, Any]] = field(default_factory=list)
    seen_listings: Set[str] = field(default_factory=set)
    seen_devices: Set[str] = field(default_factory=set)

    @property
    def is_full(self) -> bool:
        return len(self.products) >= self.limit


def _physical_device_key(product: Dict[str, Any], specs: DeviceSpecs, profile: DeviceProfile) -> str:
    # Telcel publica a veces el mismo equipo con nombres distintos ("moto razr 50 ultra" / "razr 50 Ultra");
    # si ambos apuntan a la misma ficha técnica y capacidad, es el mismo producto para el cliente.
    identity = specs.source_url if specs.is_scraped and specs.source_url else device_key(product)
    return f"{identity}|{profile.storage_gb}"


class CatalogService:
    def __init__(self, telcel: TelcelClient, enricher: SpecsEnricher, settings: Settings):
        self._telcel = telcel
        self._enricher = enricher
        self._settings = settings

    async def get_segment(self, segment: Segment, limit: Optional[int] = None, debug: bool = False) -> CatalogResult:
        started = time.monotonic()
        selection = _Selection(segment=segment, limit=limit or self._settings.catalog_size, debug=debug)
        pages_consulted = 0
        next_page: Optional["asyncio.Future[TelcelPage]"] = None

        for page_number in range(self._settings.catalog_max_pages):
            page = await next_page if next_page else await self._telcel.get_page(page_number)
            pages_consulted += 1
            has_more = page_number + 1 < min(page.total_pages, self._settings.catalog_max_pages)
            # Mientras se enriquece esta página, la siguiente ya se va descargando por si hace falta.
            next_page = asyncio.ensure_future(self._telcel.get_page(page_number + 1)) if has_more else None

            await self._select_from(page.products, selection)
            if selection.is_full or not has_more:
                break

        if next_page and not next_page.done():
            next_page.cancel()

        return CatalogResult(
            segment=segment,
            products=selection.products,
            pages_consulted=pages_consulted,
            elapsed_seconds=round(time.monotonic() - started, 3),
            debug=selection.debug_rows,
        )

    async def warm_up(self, pages: int) -> None:
        """Precalienta la caché de especificaciones con las primeras páginas del catálogo."""
        started = time.monotonic()
        try:
            for page_number in range(pages):
                page = await self._telcel.get_page(page_number)
                await self._enricher.enrich_many(page.products)
                if page_number + 1 >= page.total_pages:
                    break
            logger.info("Precalentamiento de %s páginas terminado en %.1fs", pages, time.monotonic() - started)
        except Exception:
            logger.exception("Falló el precalentamiento del catálogo")

    async def _select_from(self, products: List[Dict[str, Any]], selection: _Selection) -> None:
        candidates = []
        for product in products:
            key = listing_key(product)
            if key not in selection.seen_listings:
                selection.seen_listings.add(key)
                candidates.append(product)

        # Se enriquece por lotes en orden de relevancia para no scrapear equipos que ya no se necesitan.
        batch_size = self._settings.enrich_batch_size
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start:start + batch_size]
            specs_by_device = await self._enricher.enrich_many(batch)
            for product in batch:
                self._consider(product, specs_by_device[device_key(product)], selection)
            if selection.is_full:
                return

    def _consider(self, product: Dict[str, Any], specs: DeviceSpecs, selection: _Selection) -> None:
        profile = build_profile(product, specs)
        classification = classify(profile)
        physical_key = _physical_device_key(product, specs, profile)
        selected = (
            selection.segment in classification.segments
            and not selection.is_full
            and physical_key not in selection.seen_devices
        )
        if selected:
            selection.products.append(product)
            selection.seen_devices.add(physical_key)

        if selection.debug:
            selection.debug_rows.append({
                "code": product.get("code"),
                "name": product_display_name(product),
                "matchedName": specs.matched_name,
                "sourceUrl": specs.source_url,
                "profile": profile.to_dict(),
                "selected": selected,
                **classification.to_dict(),
            })
