import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.container import build_container
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
