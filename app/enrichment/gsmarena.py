import html
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.enrichment.matching import rank_candidates
from app.enrichment.naming import normalize_model_code, search_query
from app.enrichment.specs import DeviceSpecs
from app.enrichment.throttle import SourceRateLimitedError, Throttle

logger = logging.getLogger(__name__)

SECOND_CANDIDATE_MAX_GAP = 0.15

_RESULT_PATTERN = re.compile(
    r"<a href=[\"']?(?P<href>[\w\-]+\.php)[\"']?>\s*<img(?P<img>[^>]*)>\s*<strong>(?P<name>.*?)</strong>",
    re.IGNORECASE | re.DOTALL,
)
_RAM_BY_STORAGE = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|TB)\s+(\d+(?:\.\d+)?)\s*GB\s+RAM", re.IGNORECASE)
# \b evita confundir la frecuencia de atenuación PWM (p. ej. "3840Hz PWM") con la de actualización.
_HZ_PATTERN = re.compile(r"\b(\d{2,3})\s*Hz\b(?!\s*PWM)", re.IGNORECASE)
_MAH_PATTERN = re.compile(r"(\d{3,5})\s*mAh", re.IGNORECASE)
_GAMING_KEYWORDS = (
    "vapor chamber",
    "liquid cooling",
    "cooling system",
    "shoulder trigger",
    "air trigger",
    "touch sampling",
    "touch-sampling",
    "game turbo",
    "gaming mode",
    "game mode",
)


@dataclass(frozen=True)
class SearchResult:
    name: str
    url: str


@dataclass(frozen=True)
class SpecPage:
    specs: DeviceSpecs
    model_codes: List[str]

    def matches_model(self, telcel_model_code: str) -> bool:
        telcel_code = normalize_model_code(telcel_model_code)
        if len(telcel_code) < 5:
            return False
        for code in map(normalize_model_code, self.model_codes):
            if len(code) >= 5 and (telcel_code.startswith(code) or code.startswith(telcel_code)):
                return True
        return False


class GsmArenaScraper:
    name = "gsmarena"

    def __init__(self, session: AsyncSession, throttle: Throttle, base_url: str):
        self._session = session
        self.throttle = throttle
        self._base_url = base_url

    async def lookup(self, brand: str, name: str, model_code: str) -> Optional[DeviceSpecs]:
        query = search_query(brand, name)
        ranked = await self._search_ranked(query, name)
        if not ranked:
            # La marca de Telcel no siempre coincide con la de GSMArena (p. ej. submarcas o distribuidores).
            query_without_brand = search_query("", name)
            if query_without_brand != query:
                ranked = await self._search_ranked(query_without_brand, name)
        if not ranked:
            logger.info("GSMArena sin coincidencias para '%s'", query)
            return None

        best_score, best = ranked[0]
        best_page = await self.fetch_spec_page(best)
        if best_page is None or best_page.matches_model(model_code):
            return best_page.specs if best_page else None

        # El mejor nombre no confirmó el código de modelo: se revisa un segundo candidato muy cercano.
        if len(ranked) > 1 and best_score - ranked[1][0] <= SECOND_CANDIDATE_MAX_GAP:
            second_page = await self.fetch_spec_page(ranked[1][1])
            if second_page and second_page.matches_model(model_code):
                return second_page.specs
        return best_page.specs

    async def _search_ranked(self, query: str, telcel_name: str):
        text = await self._get("results.php3", params={"sQuickSearch": "yes", "sName": query})
        results = parse_search_results(text, self._base_url)
        return rank_candidates(query, telcel_name, [(result.name, result) for result in results])

    async def fetch_spec_page(self, result: SearchResult) -> Optional[SpecPage]:
        page = parse_spec_page(await self._get(result.url), result)
        if page is None:
            logger.warning("Ficha de GSMArena sin datos técnicos: %s", result.url)
        return page

    async def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        url = urljoin(self._base_url, path)
        async with self.throttle.slot():
            response = await self._session.get(url, params=params)
        # GSMArena responde 200 con "please slow down" cuando supera su límite de peticiones.
        if response.status_code == 429 or "slow down" in response.text[:500].lower():
            self.throttle.trip()
            raise SourceRateLimitedError(self.name)
        if response.status_code != 200 or "Turnstile" in response.text[:2000]:
            logger.warning("GSMArena %s respondió %s", url, response.status_code)
            return ""
        return response.text


def parse_search_results(text: str, base_url: str) -> List[SearchResult]:
    results = []
    for match in _RESULT_PATTERN.finditer(text or ""):
        raw_name = re.sub(r"<br\s*/?>", " ", match.group("name"), flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw_name))).strip()
        # El texto visible y el title se complementan: uno omite "5G" y otro "4G" según el modelo.
        title_match = re.search(r"title=\"([^\"]*)\"", match.group("img"))
        title = html.unescape(title_match.group(1)).strip() if title_match else ""
        if len(title.split()) > len(name.split()):
            name = title
        results.append(SearchResult(name=name, url=urljoin(base_url, match.group("href"))))
    return results


def parse_spec_page(text: str, result: SearchResult) -> Optional[SpecPage]:
    if not text:
        return None
    soup = BeautifulSoup(text, "lxml")
    fields: Dict[str, str] = {}
    for node in soup.select("[data-spec]"):
        value = node.get_text(" ", strip=True)
        if value:
            fields.setdefault(node["data-spec"], value)

    display_type = fields.get("displaytype")
    chipset = fields.get("chipset") or fields.get("chipset-hl")
    ram_options = parse_ram_options(fields.get("internalmemory") or "")
    if not (display_type or chipset or ram_options):
        return None

    refresh_rates = [int(value) for value in _HZ_PATTERN.findall(display_type or "")]
    battery = _MAH_PATTERN.search(fields.get("batdescription1") or "")
    if not battery and fields.get("batsize-hl", "").isdigit():
        battery = re.match(r"(\d+)", fields["batsize-hl"])
    nettech = fields.get("nettech")
    page_text = soup.get_text(" ", strip=True).lower()

    specs = DeviceSpecs(
        source="gsmarena",
        matched_name=result.name,
        source_url=result.url,
        chipset=chipset,
        ram_options=ram_options,
        display_type=display_type,
        refresh_rate_hz=max(refresh_rates) if refresh_rates else (60 if display_type else None),
        has_5g=("5G" in nettech) if nettech else None,
        battery_mah=int(battery.group(1)) if battery else None,
        gaming_features=[keyword for keyword in _GAMING_KEYWORDS if keyword in page_text],
    )
    model_codes = [code.strip() for code in (fields.get("models") or "").split(",") if code.strip()]
    return SpecPage(specs=specs, model_codes=model_codes)


def parse_ram_options(internal_memory: str) -> Dict[str, List[float]]:
    options: Dict[str, List[float]] = {}
    for storage, unit, ram in _RAM_BY_STORAGE.findall(internal_memory):
        storage_gb = int(float(storage) * (1024 if unit.upper() == "TB" else 1))
        values = options.setdefault(str(storage_gb), [])
        if float(ram) not in values:
            values.append(float(ram))
    return options
