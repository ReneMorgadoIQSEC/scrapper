import asyncio
from dataclasses import replace

from app.catalog import CatalogService
from app.config import Settings
from app.enrichment.cache import SpecsCache
from app.enrichment.service import SpecsEnricher
from app.enrichment.specs import DeviceSpecs
from app.enrichment.throttle import SourceRateLimitedError, Throttle
from app.segmentation.rules import Segment
from app.telcel import TelcelPage

ENTRY = DeviceSpecs(source="fake", chipset="Helio G85", ram_options={"128": [4.0]}, display_type="IPS LCD",
                    refresh_rate_hz=90, has_5g=False, battery_mah=5000)
FLAGSHIP = DeviceSpecs(source="fake", chipset="Snapdragon 8 Elite", ram_options={"256": [12.0]},
                       display_type="AMOLED, 120Hz", refresh_rate_hz=120, has_5g=True, battery_mah=5000)


def product(code, name, storage="128 GB"):
    return {"code": code, "marca": "ACME", "modelo": code, "nombreComercial": name, "capacidad": {"value": storage}}


class FakeTelcel:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    async def get_page(self, number):
        self.requested.append(number)
        return TelcelPage(number=number, total_pages=len(self.pages), products=self.pages[number])

    async def get_product_detail(self, code):
        return {"procesadorMarca": "Qualcomm", "procesadorModelo": "SM6225", "tecnologia": "4G"}


class FakeSource:
    name = "fake"

    def __init__(self, specs_by_name=None, rate_limited=False):
        self.throttle = Throttle("fake", 5, 0, 60)
        self.specs_by_name = specs_by_name or {}
        self.rate_limited = rate_limited
        self.calls = []

    async def lookup(self, brand, name, model_code):
        self.calls.append(name)
        if self.rate_limited:
            raise SourceRateLimitedError(self.name)
        for prefix, specs in self.specs_by_name.items():
            if name.startswith(prefix):
                return specs
        return None


def build(tmp_path, pages, source, **overrides):
    settings = replace(Settings(), specs_cache_path=tmp_path / "cache.json", **overrides)
    telcel = FakeTelcel(pages)
    enricher = SpecsEnricher([source], telcel, SpecsCache(settings.specs_cache_path), settings)
    return CatalogService(telcel, enricher, settings), telcel, enricher


def test_fills_segment_using_following_pages(tmp_path):
    pages = [
        [product(f"e{i}", f"Entry {i}") for i in range(8)] + [product("f0", "Flagship 0", "256 GB")],
        [product(f"f{i}", f"Flagship {i}", "256 GB") for i in range(1, 12)],
    ]
    source = FakeSource({"Entry": ENTRY, "Flagship": FLAGSHIP})
    catalog, telcel, _ = build(tmp_path, pages, source)

    result = asyncio.run(catalog.get_segment(Segment.ALTA))

    assert [item["code"] for item in result.products] == [f"f{i}" for i in range(10)]
    assert result.pages_consulted == 2
    assert result.products[0] is pages[0][8]


def test_stops_on_first_page_when_segment_is_complete(tmp_path):
    pages = [[product(f"e{i}", f"Entry {i}") for i in range(20)], [product("x", "Entry x")]]
    source = FakeSource({"Entry": ENTRY})
    catalog, telcel, _ = build(tmp_path, pages, source, enrich_batch_size=5)

    result = asyncio.run(catalog.get_segment(Segment.BAJA))

    assert len(result.products) == 10
    assert result.pages_consulted == 1
    # Solo se enriquecen los lotes necesarios para completar el segmento.
    assert len(source.calls) == 10


def test_color_variants_are_listed_once_and_scraped_once(tmp_path):
    pages = [[product("a", "Entry 1"), product("b", "Entry 1"), product("c", "Entry 1 256GB", "256 GB")]]
    source = FakeSource({"Entry": ENTRY})
    catalog, _, _ = build(tmp_path, pages, source)

    result = asyncio.run(catalog.get_segment(Segment.BAJA))

    assert [item["code"] for item in result.products] == ["a", "c"]
    assert source.calls == ["Entry 1"]


def test_same_device_published_with_different_names_is_listed_once(tmp_path):
    razr = replace(FLAGSHIP, source_url="https://m.gsmarena.com/motorola_razr_50_ultra-13095.php")
    pages = [[product("a", "moto razr 50 ultra", "512 GB"), product("b", "razr 50 Ultra", "512 GB")]]
    catalog, _, _ = build(tmp_path, pages, FakeSource({"moto razr": razr, "razr": razr}))

    result = asyncio.run(catalog.get_segment(Segment.GAMER))

    assert [item["code"] for item in result.products] == ["a"]


def test_rate_limited_source_falls_back_to_telcel_detail(tmp_path):
    pages = [[product("a", "Entry 1")]]
    catalog, _, enricher = build(tmp_path, pages, FakeSource(rate_limited=True))

    specs = asyncio.run(enricher.get_specs(pages[0][0]))

    assert specs.source == "telcel"
    assert specs.chipset == "Qualcomm SM6225"
    assert asyncio.run(catalog.get_segment(Segment.BAJA)).products == pages[0]


def test_stale_scraped_specs_are_not_replaced_by_partial_fallback(tmp_path):
    item = product("a", "Flagship 1", "256 GB")
    source = FakeSource({"Flagship": FLAGSHIP})
    _, _, enricher = build(tmp_path, [[item]], source, specs_ttl_found_seconds=-1)

    async def scenario():
        first = await enricher.get_specs(item)
        source.rate_limited = True
        stale = await enricher.get_specs(item)
        await asyncio.gather(*enricher._background)
        return first, stale, await enricher.get_specs(item)

    first, stale, after_refresh = asyncio.run(scenario())
    assert first == stale == after_refresh == FLAGSHIP
