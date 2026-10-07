import pytest

from app.segmentation.processors import Tier, classify_processor


@pytest.mark.parametrize(
    "chipset, tier, gaming",
    [
        ("Qualcomm SM8650-AB Snapdragon 8 Gen 3 (4 nm)", Tier.HIGH, True),
        ("Qualcomm SM8750-AB Snapdragon 8 Elite (3 nm)", Tier.HIGH, True),
        ("Qualcomm Snapdragon 8 Elite Gen 5", Tier.HIGH, True),
        ("Qualcomm SM8635 Snapdragon 8s Gen 3 (4 nm)", Tier.HIGH, True),
        ("Qualcomm Snapdragon 8 Plus Gen 1", Tier.HIGH, True),
        ("Qualcomm SM7675-AB Snapdragon 7+ Gen 3 (4 nm)", Tier.MID, True),
        ("Qualcomm Snapdragon 7 Plus Gen 2", Tier.MID, True),
        ("Qualcomm SM7550-AB Snapdragon 7 Gen 3 (4 nm)", Tier.MID, False),
        ("Qualcomm SM7635 Snapdragon 7s Gen 3 (4 nm)", Tier.MID, False),
        ("Qualcomm SM6475-AB Snapdragon 6 Gen 3 (4 nm)", Tier.MID, False),
        ("Qualcomm SM4450 Snapdragon 4 Gen 2 (4 nm)", Tier.ENTRY, False),
        ("Qualcomm SM6225 Snapdragon 680 4G (6 nm)", Tier.ENTRY, False),
        ("Qualcomm SM6375 Snapdragon 695 5G (6 nm)", Tier.MID, False),
        ("Qualcomm SM8350 Snapdragon 888 5G (5 nm)", Tier.HIGH, True),
        ("Qualcomm SM6475", Tier.MID, False),
        ("Qualcomm SM6225", Tier.ENTRY, False),
        ("Mediatek Dimensity 6300 (6 nm)", Tier.ENTRY, False),
        ("Mediatek MT6835 Dimensity 6100+ (6 nm)", Tier.ENTRY, False),
        ("Mediatek Dimensity 7300 (4 nm)", Tier.MID, False),
        ("Mediatek Dimensity 8350 Ultra (4 nm)", Tier.MID, True),
        ("Mediatek Dimensity 9400+ (3 nm)", Tier.HIGH, True),
        ("Mediatek Dimensity 1300 (6 nm)", Tier.MID, False),
        ("Mediatek Dimensity 700 (7 nm)", Tier.ENTRY, False),
        ("Mediatek Helio G99 (6 nm)", Tier.ENTRY, False),
        ("Mediatek MT6765 Helio P35 (12nm)", Tier.ENTRY, False),
        ("Unisoc T606 (12 nm)", Tier.ENTRY, False),
        ("UNISOC Tiger T612", Tier.ENTRY, False),
        ("Exynos 2400 (4 nm)", Tier.HIGH, False),
        ("Exynos 1580 (4 nm)", Tier.MID, False),
        ("Exynos 1330 (5 nm)", Tier.ENTRY, False),
        ("Exynos 850 (8 nm)", Tier.ENTRY, False),
        ("Google Tensor G4 (4 nm)", Tier.HIGH, False),
        ("Apple A18 Pro (3 nm)", Tier.HIGH, False),
        ("Apple Chip A20 Pro", Tier.HIGH, False),
        ("Apple A13 Bionic (7 nm+)", Tier.MID, False),
        ("Kirin 9020 (7 nm)", Tier.HIGH, False),
        ("Kirin 8000 (7 nm)", Tier.MID, False),
        ("Kirin 710A", Tier.ENTRY, False),
        # Nomenclatura del detalle de producto de Telcel.
        ("SEC S5E8845", Tier.MID, False),
        ("Exynos S5E9945", Tier.HIGH, False),
        ("Mediatek MTK-24M (MT6878)", Tier.MID, False),
        ("Mediatek - Dimensity D7060", Tier.MID, False),
        ("MediaTek G100-Ultra", Tier.ENTRY, False),
        ("Qualcomm™ SM8850, Snapdragon® 8 Elite Gen 5,", Tier.HIGH, True),
        ("Qualcomm Snapdragon 6s 4G Gen 2", Tier.ENTRY, False),
        ("Qualcomm Snapdragon 6s Gen 2 4G (SM6225-AF)", Tier.ENTRY, False),
    ],
)
def test_classify_processor(chipset, tier, gaming):
    info = classify_processor(chipset)
    assert info.tier == tier
    assert info.gaming is gaming


def test_unknown_processor():
    assert classify_processor(None).tier is None
    assert classify_processor("Chip misterioso X1").tier is None
