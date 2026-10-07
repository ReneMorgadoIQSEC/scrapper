import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.container import build_container
from app.enrichment.naming import listing_key
from app.segmentation.rules import RULES, Segment
from app.telcel import TelcelUnavailableError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SEGMENT_ALIASES = {
    "gama-baja": Segment.BAJA,
    "gama-media": Segment.MEDIA,
    "gama-alta": Segment.ALTA,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = build_container(settings)
    app.state.catalog = container.catalog
    app.state.telcel = container.telcel

    warm_up = None
    if settings.warmup_pages > 0:
        warm_up = asyncio.ensure_future(container.catalog.warm_up(settings.warmup_pages))
    try:
        yield
    finally:
        if warm_up and not warm_up.done():
            warm_up.cancel()
        await container.close()


app = FastAPI(title="Landings Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def resolve_segment(slug: str) -> Segment:
    slug = slug.lower().strip()
    if slug in SEGMENT_ALIASES:
        return SEGMENT_ALIASES[slug]
    try:
        return Segment(slug)
    except ValueError:
        valid = ", ".join(segment.value for segment in Segment)
        raise HTTPException(status_code=404, detail=f"Segmento '{slug}' no existe. Opciones: {valid}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/catalog")
async def list_segments():
    return {"segments": [{"slug": segment.value, "name": rule.title} for segment, rule in RULES.items()]}


@app.get("/catalog/{segment}")
async def catalog(
    segment: str,
    limit: Optional[int] = Query(default=None, ge=1, le=50),
    debug: bool = Query(default=False, description="Incluye las especificaciones y puntajes de cada equipo evaluado"),
):
    resolved = resolve_segment(segment)
    try:
        result = await app.state.catalog.get_segment(resolved, limit=limit, debug=debug)
    except TelcelUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    response = {
        "segment": resolved.value,
        "segmentName": RULES[resolved].title,
        "total": len(result.products),
        "pagesConsulted": result.pages_consulted,
        "elapsedSeconds": result.elapsed_seconds,
        "products": result.products,
    }
    if debug:
        response["debug"] = result.debug
    return response


LimitQuery = Query(default=None, ge=1, le=50, description="Cantidad de productos (default CATALOG_SIZE)")


async def telcel_category(slug: str, name: str, query: str, limit: Optional[int]):
    """Primeros productos de una categoría de Telcel, en su orden de relevancia y sin enriquecer."""
    started = time.monotonic()
    size = limit or settings.catalog_size
    try:
        # Se pide una página completa para que, tras quitar repetidos, sigan alcanzando los productos pedidos.
        page = await app.state.telcel.get_page(0, query=query)
    except TelcelUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    products, seen = [], set()
    for product in page.products:
        key = listing_key(product)
        if key not in seen:
            seen.add(key)
            products.append(product)
    products = products[:size]
    return {
        "category": slug,
        "categoryName": name,
        "total": len(products),
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "products": products,
    }


@app.get("/celulares")
async def celulares(limit: Optional[int] = LimitQuery):
    return await telcel_category("celulares", "Celulares", settings.telcel_query, limit)


@app.get("/tablets")
async def tablets(limit: Optional[int] = LimitQuery):
    return await telcel_category("tablets", "Tablets", settings.telcel_tablets_query, limit)


@app.get("/smartwatches")
async def smartwatches(limit: Optional[int] = LimitQuery):
    return await telcel_category("smartwatches", "Smartwatches", settings.telcel_smartwatches_query, limit)
