"""Enriquece y clasifica páginas del catálogo de Telcel, mostrando el resultado por equipo.

Uso: python -m scripts.classify_catalog [páginas]   (por defecto: 0)
También sirve para precargar la caché de especificaciones antes de desplegar.
"""
import asyncio
import logging
import sys
import time

from app.config import settings
from app.container import build_container
from app.enrichment.naming import device_key, listing_key, product_display_name
from app.segmentation.profile import build_profile
from app.segmentation.rules import classify


def _fmt(value, width):
    return str(value if value is not None else "-")[:width].ljust(width)


async def main(pages):
    container = build_container(settings)
    telcel, enricher = container.telcel, container.enricher
    try:
        for number in pages:
            started = time.monotonic()
            page = await telcel.get_page(number)
            specs_by_device = await enricher.enrich_many(page.products)
            print(f"\n=== Página {number}: {len(page.products)} productos, {len(specs_by_device)} equipos únicos, "
                  f"{time.monotonic() - started:.1f}s")
            seen = set()
            for product in page.products:
                if listing_key(product) in seen:
                    continue
                seen.add(listing_key(product))
                specs = specs_by_device[device_key(product)]
                profile = build_profile(product, specs)
                tier = profile.processor.tier.value if profile.processor.tier else None
                print(" | ".join([
                    _fmt(product_display_name(product), 30),
                    _fmt(specs.source, 10),
                    _fmt(specs.matched_name, 26),
                    _fmt(profile.processor.family, 22),
                    _fmt(tier, 7),
                    _fmt(profile.ram_gb, 4) + "GB",
                    _fmt(profile.storage_gb, 4) + "GB",
                    _fmt(profile.display_tech, 4),
                    _fmt(profile.refresh_rate_hz, 3) + "Hz",
                    "5G" if profile.has_5g else "  ",
                    _fmt(profile.battery_mah, 5) + "mAh",
                    ",".join(segment.value for segment in classify(profile).segments),
                ]))
    finally:
        await container.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main([int(arg) for arg in sys.argv[1:]] or [0]))
