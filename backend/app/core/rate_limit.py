"""Limite de requisições por IP (janela deslizante, em memória).

Suficiente para um único servidor. Se um dia a API rodar em várias instâncias,
troque por um armazenamento compartilhado (ex.: Redis).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Registra uma tentativa. Retorna quantos segundos esperar, ou None se liberado."""
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % 1000 == 0:
                self._prune(now, window)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return hits[0] + window - now
            hits.append(now)
            return None

    def _prune(self, now: float, window: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
            del self._hits[key]

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[[Request], None]:
    """Dependência do FastAPI: até `limit` requisições por IP a cada `window_seconds`."""

    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        wait = limiter.hit(f"{name}:{client_ip(request)}", limit, window_seconds)
        if wait is not None:
            minutes = max(1, math.ceil(wait / 60))
            raise AppError(
                429,
                "rate_limited",
                f"Muitas tentativas a partir desta conexão. Tente de novo em {minutes} min.",
                headers={"Retry-After": str(math.ceil(wait))},
            )

    return dependency
