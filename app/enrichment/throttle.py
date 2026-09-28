import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional


class SourceRateLimitedError(Exception):
    pass


class Throttle:
    """Limita concurrencia y ritmo de peticiones a un sitio, y lo pausa por completo si nos pide bajar el ritmo."""

    def __init__(self, name: str, concurrency: int, min_interval_seconds: float, cooldown_seconds: float):
        self.name = name
        self._concurrency = concurrency
        self._min_interval = min_interval_seconds
        self._cooldown_seconds = cooldown_seconds
        # En Python 3.9 las primitivas de asyncio se atan al loop activo al crearse, por eso se crean al primer uso.
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._pace_lock: Optional[asyncio.Lock] = None
        self._last_request_at = 0.0
        self._blocked_until = 0.0
        self._pending = 0

    @property
    def is_cooling_down(self) -> bool:
        return time.monotonic() < self._blocked_until

    @property
    def backlog(self) -> int:
        """Peticiones en curso o esperando turno."""
        return self._pending

    def trip(self) -> None:
        self._blocked_until = time.monotonic() + self._cooldown_seconds

    @asynccontextmanager
    async def slot(self):
        if self.is_cooling_down:
            raise SourceRateLimitedError(self.name)
        if self._semaphore is None or self._pace_lock is None:
            self._semaphore = asyncio.Semaphore(self._concurrency)
            self._pace_lock = asyncio.Lock()
        self._pending += 1
        try:
            async with self._semaphore:
                async with self._pace_lock:
                    wait = self._last_request_at + self._min_interval - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._last_request_at = time.monotonic()
                # Otra petición pudo activar la pausa mientras esta esperaba turno.
                if self.is_cooling_down:
                    raise SourceRateLimitedError(self.name)
                yield
        finally:
            self._pending -= 1
