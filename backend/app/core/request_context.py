"""IP e navegador da requisição atual, para registrar eventos sem passar isso por toda função.

Em produção a API fica atrás do Caddy; o uvicorn roda com `--proxy-headers` para que
`request.client.host` seja o IP real do visitante (e não o do proxy).
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestInfo:
    ip: str | None = None
    user_agent: str | None = None


_EMPTY = RequestInfo()
_current: ContextVar[RequestInfo | None] = ContextVar("request_info", default=None)


def set_request_info(info: RequestInfo) -> None:
    _current.set(info)


def request_info() -> RequestInfo:
    return _current.get() or _EMPTY
