import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from app.enrichment.specs import DeviceSpecs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedSpecs:
    specs: DeviceSpecs
    stale: bool


class SpecsCache:
    """Caché persistente en disco: las especificaciones de un equipo casi nunca cambian.

    Las entradas vencidas no se borran: se siguen sirviendo como "stale" mientras se refrescan en segundo plano.
    """

    def __init__(self, path: Path):
        self._path = path
        self._entries: Dict[str, dict] = {}
        self._dirty = False
        self._load()

    def get(self, key: str) -> Optional[CachedSpecs]:
        entry = self._entries.get(key)
        if not entry:
            return None
        return CachedSpecs(specs=DeviceSpecs.from_dict(entry["specs"]), stale=entry["expires_at"] < time.time())

    def set(self, key: str, specs: DeviceSpecs, ttl_seconds: int) -> None:
        self._entries[key] = {"expires_at": time.time() + ttl_seconds, "specs": specs.to_dict()}
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(self._entries, tmp_file, ensure_ascii=False, indent=1)
        os.replace(tmp_path, self._path)
        self._dirty = False

    def __len__(self) -> int:
        return len(self._entries)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._entries = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("No se pudo leer la caché %s; se inicia vacía", self._path, exc_info=True)
            self._entries = {}
