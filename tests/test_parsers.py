from pathlib import Path

from app.enrichment.gsmarena import SearchResult, parse_ram_options, parse_search_results, parse_spec_page
from app.enrichment.matching import rank_candidates
from app.enrichment.naming import clean_model_name, device_key, search_query, storage_gb
from app.enrichment.nanoreview import parse_phone_page

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_gsmarena_search_results():
    results = parse_search_results(read("gsmarena_search_galaxy_a17.html"), "https://m.gsmarena.com/")
    assert [result.name for result in results] == ["Samsung Galaxy A17 5G", "Samsung Galaxy A17 4G"]
    assert results[1].url == "https://m.gsmarena.com/samsung_galaxy_a17-14157.php"


def test_parse_gsmarena_spec_page():
    result = SearchResult(name="Samsung Galaxy A17 4G", url="https://m.gsmarena.com/samsung_galaxy_a17-14157.php")
    page = parse_spec_page(read("gsmarena_galaxy_a17.html"), result)
    specs = page.specs
    assert specs.chipset == "Mediatek Helio G99 (6 nm)"
    assert specs.display_type == "Super AMOLED, 90Hz"
    assert specs.refresh_rate_hz == 90
    assert specs.has_5g is False
    assert specs.battery_mah == 5000
    assert specs.ram_options == {"128": [4.0, 6.0, 8.0], "256": [4.0, 8.0]}
    assert page.matches_model("SM-A175F")
    assert not page.matches_model("SM-A176B")


def test_rate_limit_page_is_not_a_spec_page():
    result = SearchResult(name="x", url="https://m.gsmarena.com/x.php")
    assert parse_spec_page("B:H208 - please slow down! Try again in a minute.", result) is None


def test_parse_nanoreview_page():
    specs = parse_phone_page(read("nanoreview_galaxy_a17.html"), "Samsung Galaxy A17 4G", "https://nanoreview.net/x")
    assert specs.chipset == "MediaTek Helio G99"
    assert specs.display_type == "Super AMOLED"
    assert specs.refresh_rate_hz == 90
    assert specs.battery_mah == 5000
    assert specs.has_5g is False
    assert specs.ram_options == {"128": [4.0]}


def test_refresh_rate_ignores_pwm_frequency():
    html = '<td data-spec="displaytype">LTPO OLED, 1B colors, 120Hz, 1440Hz PWM, 3000 nits (peak)</td>'
    page = parse_spec_page(html, SearchResult(name="x", url="https://m.gsmarena.com/x.php"))
    assert page.specs.refresh_rate_hz == 120


def test_parse_ram_options_with_terabytes():
    assert parse_ram_options("256GB 12GB RAM, 1TB 16GB RAM") == {"256": [12.0], "1024": [16.0]}


def test_clean_names_and_queries():
    assert clean_model_name('Galaxy S26 Ultra 256GB + TV 43" UHD 4K') == "Galaxy S26 Ultra"
    assert clean_model_name("Redmi 15C 256/4GB") == "Redmi 15C"
    assert search_query("SAMSUNG", "Galaxy A55 5G 256GB") == "samsung Galaxy A55"
    assert search_query("HONOR", "HONOR X6c") == "HONOR X6c"
    assert search_query("TECNOMOBILE", "Pop 5S") == "tecno Pop 5S"


def test_device_key_is_shared_between_storage_variants():
    a = {"marca": "APPLE", "nombreComercial": "iPhone 17 256GB"}
    b = {"marca": "APPLE", "nombreComercial": "iPhone 17 512GB"}
    assert device_key(a) == device_key(b)


def test_storage_from_capacity_or_name():
    assert storage_gb({"capacidad": {"value": "256 GB"}}) == 256
    assert storage_gb({"capacidad": {"unit": "GB", "value": "128"}}) == 128
    assert storage_gb({"nombreComercial": "iPhone 17 Pro 1TB"}) == 1024


def test_ranking_rejects_different_model_numbers():
    ranked = rank_candidates("vivo v25 pro", "vivo V25 Pro", [("vivo V27 Pro", 1), ("vivo V25 Pro", 2)])
    assert [value for _, value in ranked] == [2]


def test_ranking_prefers_network_variant_from_telcel_name():
    candidates = [("Xiaomi Redmi Note 14 Pro 5G", "5g"), ("Xiaomi Redmi Note 14 Pro 4G", "4g")]
    ranked = rank_candidates("xiaomi redmi note 14 pro", "Redmi Note 14 Pro 256GB", candidates)
    assert ranked[0][1] == "4g"
