"""Indicadores econômicos (Selic, CDI, IPCA) da API pública do Banco Central (SGS).

Os endereços são fixos (nunca vêm do usuário) e o resultado fica em cache por algumas horas.
Se o Banco Central estiver fora do ar, a API responde sem os valores em vez de falhar.
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

SERIES = {
    "selic": 432,  # Meta Selic definida pelo Copom (% a.a.)
    "cdi": 4389,  # CDI anualizado base 252 (% a.a.)
    "ipca_12m": 13522,  # IPCA acumulado em 12 meses (%)
}
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/1?formato=json"
CACHE_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 5

_cache: dict[str, Any] = {}
_lock = threading.Lock()


def fetch_series(code: int) -> tuple[float, str]:
    """Último valor da série: (valor, data dd/mm/aaaa)."""
    request = Request(URL.format(code=code), headers={"Accept": "application/json"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (URL fixa)
        data = json.load(response)
    last = data[-1]
    return float(last["valor"]), str(last["data"])


def get_indicators() -> dict[str, Any]:
    with _lock:
        if _cache and time.monotonic() - _cache["fetched"] < CACHE_SECONDS:
            return _cache["value"]

    values: dict[str, Any] = {"available": True}
    for key, code in SERIES.items():
        try:
            value, date = fetch_series(code)
            values[key] = {"value": value, "date": date}
        except Exception as exc:  # rede, formato inesperado etc.
            logger.warning("Falha ao buscar a série %s do BCB: %s", code, exc)
            values[key] = None
            values["available"] = False
    values["fetched_at"] = datetime.now(UTC)

    # Só guarda em cache se veio tudo, para tentar de novo na próxima chamada.
    if values["available"]:
        with _lock:
            _cache.update({"fetched": time.monotonic(), "value": values})
    return values


def clear_cache() -> None:
    with _lock:
        _cache.clear()
