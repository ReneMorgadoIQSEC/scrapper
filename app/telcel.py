import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi.requests import AsyncSession

from app.config import Settings

logger = logging.getLogger(__name__)

JSON_HEADERS = {"Accept": "application/json", "Accept-Language": "es-MX,es;q=0.9"}


class TelcelUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class TelcelPage:
    number: int
    total_pages: int
    products: List[Dict[str, Any]]


class TelcelClient:
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings
        self._pages: Dict[int, Tuple[float, TelcelPage]] = {}
        self._page_locks: Dict[int, asyncio.Lock] = {}

    async def get_page(self, number: int) -> TelcelPage:
        cached = self._pages.get(number)
        if cached and time.monotonic() - cached[0] < self._settings.telcel_page_ttl_seconds:
            return cached[1]

        lock = self._page_locks.setdefault(number, asyncio.Lock())
        async with lock:
            cached = self._pages.get(number)
            if cached and time.monotonic() - cached[0] < self._settings.telcel_page_ttl_seconds:
                return cached[1]
            page = await self._fetch_page(number)
            self._pages[number] = (time.monotonic(), page)
            return page

    async def get_product_detail(self, code: str) -> Optional[Dict[str, Any]]:
        url = f"{self._settings.telcel_base_url}/products/{code}"
        try:
            response = await self._session.get(
                url, params={"fields": "FULL", "lang": "es_MX", "curr": "MXN"}, headers=JSON_HEADERS
            )
        except Exception:
            logger.warning("Error consultando detalle Telcel %s", code, exc_info=True)
            return None
        if response.status_code != 200:
            logger.warning("Detalle Telcel %s respondió %s", code, response.status_code)
            return None
        return response.json()

    async def _fetch_page(self, number: int) -> TelcelPage:
        params = {
            "fields": self._settings.telcel_fields,
            "query": self._settings.telcel_query,
            "pageSize": self._settings.telcel_page_size,
            "lang": "es_MX",
            "curr": "MXN",
            "currentPage": number,
        }
        started = time.monotonic()
        try:
            response = await self._session.get(
                f"{self._settings.telcel_base_url}/products/search", params=params, headers=JSON_HEADERS
            )
        except Exception as exc:
            raise TelcelUnavailableError(f"No fue posible conectar con Telcel: {exc}") from exc

        if response.status_code != 200:
            raise TelcelUnavailableError(f"Telcel respondió {response.status_code} para la página {number}")

        payload = response.json()
        pagination = payload.get("pagination") or {}
        page = TelcelPage(
            number=number,
            total_pages=int(pagination.get("totalPages") or 0),
            products=payload.get("products") or [],
        )
        logger.info(
            "Telcel página %s: %s productos en %.2fs", number, len(page.products), time.monotonic() - started
        )
        return page
