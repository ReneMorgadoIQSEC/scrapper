from app.segmentation.processors import classify_processor
from app.segmentation.profile import DeviceProfile
from app.segmentation.rules import Segment, classify


def profile(chipset=None, ram=None, storage=None, display=None, hz=None, five_g=None, battery=None, features=()):
    return DeviceProfile(
        processor=classify_processor(chipset),
        chipset=chipset,
        ram_gb=ram,
        storage_gb=storage,
        display_tech=display,
        refresh_rate_hz=hz,
        has_5g=five_g,
        battery_mah=battery,
        gaming_features=list(features),
    )


def segments(device):
    return classify(device).segments


def test_entry_device_is_baja():
    device = profile("Mediatek Helio G99", ram=4, storage=128, display="LCD", hz=90, five_g=False, battery=5000)
    assert segments(device) == [Segment.BAJA]


def test_isolated_superior_feature_does_not_upgrade_tier():
    device = profile("Mediatek Dimensity 6300", ram=4, storage=256, display="LCD", hz=90, five_g=True)
    assert segments(device) == [Segment.BAJA]


def test_mid_range_device_is_media():
    device = profile("Snapdragon 6 Gen 3", ram=6, storage=128, display="OLED", hz=120, five_g=True, battery=5000)
    assert segments(device) == [Segment.MEDIA]


def test_flagship_is_alta_and_gamer():
    device = profile("Snapdragon 8 Elite", ram=12, storage=256, display="OLED", hz=120, five_g=True, battery=5000)
    assert segments(device) == [Segment.ALTA, Segment.GAMER]


def test_mid_range_with_gaming_chip_is_media_and_gamer():
    device = profile("Dimensity 8350 Ultra", ram=12, storage=256, display="OLED", hz=120, five_g=True, battery=5500)
    assert segments(device) == [Segment.MEDIA, Segment.GAMER]


def test_recent_iphone_is_alta_even_with_60hz():
    device = profile("Apple A16 Bionic", ram=6, storage=256, display="OLED", hz=60, five_g=True, battery=3349)
    assert segments(device) == [Segment.ALTA]


def test_gamer_requires_high_refresh_rate():
    device = profile("Snapdragon 8 Gen 3", ram=12, storage=256, display="OLED", hz=60, five_g=True, battery=5000)
    assert Segment.GAMER not in segments(device)


def test_gamer_requires_known_values():
    device = profile("Snapdragon 8 Gen 3", storage=256, five_g=True)
    assert Segment.GAMER not in segments(device)


def test_processor_only_fallback_still_assigns_tier():
    device = profile("Qualcomm SM6225", storage=128, five_g=False)
    assert segments(device) == [Segment.BAJA]


def test_without_information_there_is_no_segment():
    assert segments(profile(storage=128)) == []
