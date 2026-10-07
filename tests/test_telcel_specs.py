from app.enrichment.telcel_specs import parse_telcel_detail

PRODUCT = {"code": "1", "marca": "XIAOMI", "nombreComercial": "Redmi Note 14 Pro 256GB"}


def detail(**fields):
    return {"nombreComercial": PRODUCT["nombreComercial"], "capacidad": {"unit": "GB", "value": "256"}, **fields}


def test_structured_fields():
    specs = parse_telcel_detail(detail(procesadorMarca="SEC", procesadorModelo="S5E8845", tecnologia="5G"), PRODUCT)
    assert specs.source == "telcel"
    assert specs.chipset == "SEC S5E8845"
    assert specs.has_5g is True


def test_processor_brand_is_not_repeated():
    specs = parse_telcel_detail(detail(procesadorMarca="Mediatek", procesadorModelo="MediaTek G100-Ultra"), PRODUCT)
    assert specs.chipset == "MediaTek G100-Ultra"


def test_lte_advanced_is_not_5g():
    assert parse_telcel_detail(detail(tecnologia="4.5G"), PRODUCT).has_5g is False


def test_marketing_text():
    description = (
        "<p>Pantalla AMOLED de 120Hz con muestreo de 240 Hz de muestreo táctil. Su batería de 5,500&nbsp;mAh "
        "y memoria RAM de 8 GB, con hasta 16 GB de RAM dinámica. Incluye cámara de vapor.</p>"
    )
    specs = parse_telcel_detail(detail(description=description), PRODUCT)
    assert specs.display_type == "AMOLED"
    assert specs.refresh_rate_hz == 120
    assert specs.battery_mah == 5500
    assert specs.ram_options == {"256": [8.0]}
    assert specs.gaming_features == ["cámara de vapor"]


def test_contradictory_or_virtual_values_are_ignored():
    description = "Batería de 7700mAh. Con batería de 8,000 mAh y hasta 24 GB de RAM dinámica."
    specs = parse_telcel_detail(detail(description=description), PRODUCT)
    assert specs.battery_mah is None
    assert specs.ram_options == {}


def test_bundle_text_is_ignored():
    product = {**PRODUCT, "nombreComercial": 'Galaxy S26 Ultra 256GB + TV 43" UHD 4K'}
    specs = parse_telcel_detail({"nombreComercial": product["nombreComercial"], "description": "TV de 60Hz"}, product)
    assert specs.refresh_rate_hz is None
    assert specs.source == "none"
