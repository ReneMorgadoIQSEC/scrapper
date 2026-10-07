import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

BASE_DIR = Path(__file__).resolve().parent.parent

TELCEL_FIELDS = (
    "products(categories(FULL),marca,modelo,code,requiereMSI,name,summary,price(FULL),"
    "images(DEFAULT),stock(FULL),averageRating,variantOptions,productSpecification,"
    "productOfferingPrice(FULL),storage)"
)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_list(name: str, default: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    telcel_base_url: str = os.getenv("TELCEL_BASE_URL", "https://www.telcel.com/occ/v2/telcel")
    telcel_query: str = os.getenv("TELCEL_QUERY", ":relevance:allCategories:telefonos-y-smartphones")
    telcel_fields: str = os.getenv("TELCEL_FIELDS", TELCEL_FIELDS)
    telcel_page_size: int = _env_int("TELCEL_PAGE_SIZE", 50)
    telcel_page_ttl_seconds: int = _env_int("TELCEL_PAGE_TTL_SECONDS", 600)

    catalog_size: int = _env_int("CATALOG_SIZE", 10)
    catalog_max_pages: int = _env_int("CATALOG_MAX_PAGES", 6)
    enrich_batch_size: int = _env_int("ENRICH_BATCH_SIZE", 10)
    warmup_pages: int = _env_int("WARMUP_PAGES", 2)

    gsmarena_base_url: str = os.getenv("GSMARENA_BASE_URL", "https://m.gsmarena.com/")
    gsmarena_concurrency: int = _env_int("GSMARENA_CONCURRENCY", 3)
    # GSMArena tolera ~2 peticiones/s sostenidas; con ráfagas mayores responde "please slow down".
    gsmarena_min_interval_seconds: float = _env_float("GSMARENA_MIN_INTERVAL_SECONDS", 0.5)
    nanoreview_base_url: str = os.getenv("NANOREVIEW_BASE_URL", "https://nanoreview.net/")
    nanoreview_concurrency: int = _env_int("NANOREVIEW_CONCURRENCY", 2)
    nanoreview_min_interval_seconds: float = _env_float("NANOREVIEW_MIN_INTERVAL_SECONDS", 0.5)
    scraper_cooldown_seconds: float = _env_float("SCRAPER_COOLDOWN_SECONDS", 60)
    source_backlog_limit: int = _env_int("SOURCE_BACKLOG_LIMIT", 4)

    # Orígenes del frontend separados por coma; "*" permite cualquiera.
    cors_origins: Tuple[str, ...] = _env_list("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")

    http_timeout_seconds: float = _env_float("HTTP_TIMEOUT_SECONDS", 20)
    http_impersonate: str = os.getenv("HTTP_IMPERSONATE", "chrome")

    specs_cache_path: Path = field(
        default_factory=lambda: Path(os.getenv("SPECS_CACHE_PATH", BASE_DIR / "data" / "specs_cache.json"))
    )
    specs_ttl_found_seconds: int = _env_int("SPECS_TTL_FOUND_SECONDS", 30 * 24 * 3600)
    specs_ttl_fallback_seconds: int = _env_int("SPECS_TTL_FALLBACK_SECONDS", 3 * 24 * 3600)
    specs_ttl_rate_limited_seconds: int = _env_int("SPECS_TTL_RATE_LIMITED_SECONDS", 15 * 60)


settings = Settings()
