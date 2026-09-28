import logging
import re
from typing import Dict, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.enrichment.matching import rank_candidates
from app.enrichment.naming import search_query
from app.enrichment.specs import DeviceSpecs
from app.enrichment.throttle import SourceRateLimitedError, Throttle

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


class NanoreviewScraper:
    name = "nanoreview"

    def __init__(self, session: AsyncSession, throttle: Throttle, base_url: str):
        self._session = session
        self.throttle = throttle
        self._base_url = base_url

    async def lookup(self, brand: str, name: str, model_code: str) -> Optional[DeviceSpecs]:
        query = search_query(brand, name)
        response = await self._get("api/search", params={"q": query, "limit": "10", "type": "phone"})
        results = response.json() if response is not None else []
        candidates = [(item.get("name") or "", item) for item in results if item.get("content_type") == "phone"]
        ranked = rank_candidates(query, name, candidates)
        if not ranked:
            logger.info("nanoreview sin coincidencias para '%s'", query)
            return None

        best = ranked[0][1]
        url = urljoin(self._base_url, f"en/phone/{best['slug']}")
        page = await self._get(url)
        return parse_phone_page(page.text, best["name"], url) if page is not None else None

    async def _get(self, path: str, params: Optional[Dict[str, str]] = None):
        url = urljoin(self._base_url, path)
        async with self.throttle.slot():
            response = await self._session.get(url, params=params)
        if response.status_code in (403, 429):
            self.throttle.trip()
            raise SourceRateLimitedError(self.name)
        if response.status_code != 200:
            logger.warning("nanoreview %s respondió %s", url, response.status_code)
            return None
        return response


def _number(text: Optional[str]) -> Optional[float]:
    match = _NUMBER.search(text or "")
    return float(match.group(1)) if match else None


def parse_phone_page(text: str, matched_name: str, url: str) -> Optional[DeviceSpecs]:
    soup = BeautifulSoup(text, "lxml")
    fields: Dict[str, str] = {}
    for row in soup.select("tr"):
        header, value = row.select_one("td.cell-h"), row.select_one("td.cell-s")
        if header and value:
            fields.setdefault(header.get_text(" ", strip=True), value.get_text(" ", strip=True))

    chipset = fields.get("Chipset")
    display_type = fields.get("Type")
    if not (chipset or display_type):
        return None

    ram = _number(fields.get("RAM size"))
    storage = _number(fields.get("Storage size"))
    refresh = _number(fields.get("Refresh rate"))
    battery = _number(fields.get("Capacity"))
    five_g = fields.get("5G support")
    page_text = soup.get_text(" ", strip=True).lower()
    return DeviceSpecs(
        source="nanoreview",
        matched_name=matched_name,
        source_url=url,
        chipset=chipset,
        ram_options={str(int(storage or 0)): [ram]} if ram else {},
        display_type=display_type,
        refresh_rate_hz=int(refresh) if refresh else (60 if display_type else None),
        has_5g=five_g.lower().startswith("yes") if five_g else None,
        battery_mah=int(battery) if battery else None,
        gaming_features=[keyword for keyword in ("vapor chamber", "liquid cooling", "shoulder trigger") if keyword in page_text],
    )
