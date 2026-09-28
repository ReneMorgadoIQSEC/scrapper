from curl_cffi.requests import AsyncSession

from app.config import Settings


def create_session(settings: Settings) -> AsyncSession:
    # Telcel (Akamai) y GSMArena rechazan clientes cuya huella TLS no sea la de un navegador real.
    return AsyncSession(impersonate=settings.http_impersonate, timeout=settings.http_timeout_seconds)
