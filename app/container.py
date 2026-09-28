from dataclasses import dataclass
from typing import List

from curl_cffi.requests import AsyncSession

from app.catalog import CatalogService
from app.config import Settings
from app.enrichment.cache import SpecsCache
from app.enrichment.gsmarena import GsmArenaScraper
from app.enrichment.nanoreview import NanoreviewScraper
from app.enrichment.service import SpecsEnricher
from app.enrichment.throttle import Throttle
from app.http_client import create_session
from app.telcel import TelcelClient


@dataclass
class Container:
    catalog: CatalogService
    telcel: TelcelClient
    enricher: SpecsEnricher
    cache: SpecsCache
    sessions: List[AsyncSession]

    async def close(self) -> None:
        self.cache.save()
        for session in self.sessions:
            await session.close()


def build_container(settings: Settings) -> Container:
    telcel_session, gsmarena_session, nanoreview_session = sessions = [create_session(settings) for _ in range(3)]
    telcel = TelcelClient(telcel_session, settings)
    cache = SpecsCache(settings.specs_cache_path)
    sources = [
        GsmArenaScraper(
            gsmarena_session,
            Throttle(
                "gsmarena",
                settings.gsmarena_concurrency,
                settings.gsmarena_min_interval_seconds,
                settings.scraper_cooldown_seconds,
            ),
            settings.gsmarena_base_url,
        ),
        NanoreviewScraper(
            nanoreview_session,
            Throttle(
                "nanoreview",
                settings.nanoreview_concurrency,
                settings.nanoreview_min_interval_seconds,
                settings.scraper_cooldown_seconds,
            ),
            settings.nanoreview_base_url,
        ),
    ]
    enricher = SpecsEnricher(sources, telcel, cache, settings)
    return Container(
        catalog=CatalogService(telcel, enricher, settings),
        telcel=telcel,
        enricher=enricher,
        cache=cache,
        sessions=sessions,
    )
