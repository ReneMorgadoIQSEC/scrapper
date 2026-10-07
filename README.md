El entry point es `app/main.py`: ahí está la instancia de FastAPI llamada `app`, y la levantas con `uvicorn app.main:app`. Uvicorn es el servidor web que carga esa instancia y atiende las peticiones.

## Cómo correrlo

El entorno virtual `.venv` ya está creado y con las dependencias instaladas, así que basta con:

```bash
source .venv/bin/activate
uvicorn app.main:app --port 8000
```

Si algún día lo montas desde cero (en otra máquina, por ejemplo):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt + pytest
uvicorn app.main:app --port 8000
```

Para desarrollo, `--reload` reinicia el servidor cada vez que guardas un archivo:

```bash
uvicorn app.main:app --port 8000 --reload
```

## Endpoints

| Ruta | Qué hace |
|---|---|
| `GET /catalog/{segmento}` | 10 equipos de Telcel del segmento (`baja`, `media`, `alta`, `gamer`) |
| `GET /catalog/{segmento}?debug=true` | Añade las especificaciones y los puntajes de cada equipo evaluado |
| `GET /catalog/{segmento}?limit=5` | Cambia cuántos equipos regresa (de 1 a 50) |
| `GET /catalog` | Lista de segmentos disponibles |
| `GET /health` | Verifica que el servicio esté arriba |
| `GET /docs` | Documentación interactiva que FastAPI genera sola (Swagger) |

Ejemplo:

```bash
curl http://localhost:8000/catalog/gamer
```

## Qué pasa al arrancar

En `app/main.py`, la función `lifespan` hace esto:

1. Llama a `build_container()` (en `app/container.py`), que arma todas las piezas:
   - el cliente de Telcel, que también es la fuente principal de especificaciones;
   - los scrapers de GSMArena y nanoreview (solo de respaldo), cada uno con su control de ritmo de peticiones;
   - la caché en disco;
   - el servicio de catálogo.
2. Lanza en segundo plano la precarga de las primeras 2 páginas de Telcel. El servidor ya responde mientras tanto.
3. Al apagarse, guarda la caché en `data/specs_cache.json` y cierra las conexiones.

El recorrido de una petición es: `main.py` → `CatalogService.get_segment()` (`catalog.py`) → `SpecsEnricher` (`enrichment/service.py`) → `classify()` (`segmentation/rules.py`).

## De dónde salen las especificaciones

1. **Telcel (fuente principal):** del detalle de producto se toman el procesador y la tecnología (5G), y de la descripción comercial la pantalla, los Hz, los mAh y la RAM cuando aparecen sin contradicciones (`enrichment/telcel_specs.py`).
2. **GSMArena y nanoreview (respaldo):** solo se consultan si a Telcel le falta algún dato que usa la segmentación, y únicamente rellenan esos huecos; lo que reporta Telcel nunca se sobrescribe. La excepción es un procesador que Telcel reporta con un código interno imposible de clasificar (p. ej. `MTK-25M+`).

El campo `specsSource` de `?debug=true` indica el origen: `telcel`, `telcel+gsmarena`, `telcel+nanoreview`, o solo la fuente externa si el detalle de Telcel no respondió.

## Configuración

Todo se ajusta con variables de entorno, definidas en `app/config.py`. Las más útiles:

```bash
WARMUP_PAGES=0 uvicorn app.main:app      # sin precarga al arrancar (arranque más ligero)
CATALOG_SIZE=12                           # equipos por respuesta (default 10)
CATALOG_MAX_PAGES=6                       # máximo de páginas de Telcel a recorrer
GSMARENA_MIN_INTERVAL_SECONDS=0.5         # ritmo del scraping (~2 peticiones/s)
SPECS_CACHE_PATH=/ruta/cache.json         # dónde se guarda la caché
CORS_ORIGINS=https://mi-landing.com       # orígenes del frontend, separados por coma (default: localhost:5500)
```

## Otros comandos

```bash
# Tests
python -m pytest -q

# Ver cómo se clasifica cada equipo de las páginas 0 y 1
# (también sirve para precargar la caché antes de desplegar)
python -m scripts.classify_catalog 0 1
```

La primera vez que se consulta un equipo nuevo hay que consultar Telcel y, casi siempre, el respaldo para completar datos; una página completa tarda unos 25–30 s. Después queda en caché 30 días y las respuestas bajan a milisegundos. Si borras `data/specs_cache.json`, la siguiente carga vuelve a ser lenta.

## Despliegue en Railway

Railway detecta el `Dockerfile` y lo usa para construir: Python 3.12 y uvicorn escuchando en el `PORT` que asigna Railway.

1. **Crear el servicio:** New Project → Deploy from GitHub repo → elegir este repositorio.
2. **Variables** (pestaña Variables del servicio):
   - `CORS_ORIGINS`: dominio(s) de la landing, p. ej. `https://mi-landing.com`. Sin esto el navegador bloquea las peticiones.
   - Opcionales: las de la sección Configuración (`CATALOG_SIZE`, `WARMUP_PAGES`...).
3. **Volumen para la caché** (recomendado): clic derecho sobre el servicio → Attach Volume → mount path `/data`. El `Dockerfile` ya apunta `SPECS_CACHE_PATH` a `/data/specs_cache.json`. Sin volumen funciona igual, pero cada despliegue empieza con la caché vacía y vuelve a consultar GSMArena y nanoreview.
4. **Healthcheck:** Settings → Deploy → Healthcheck Path = `/health`.
5. **Dominio público:** Settings → Networking → Generate Domain. La landing consume `https://<dominio>.up.railway.app/catalog/{segmento}`.

Mantén una sola réplica: la caché, los límites de peticiones a los scrapers y la deduplicación viven en memoria del proceso.

Para probar la imagen localmente:

```bash
docker build -t landings-service .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" landings-service
```