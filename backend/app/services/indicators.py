"""Indicadores econômicos (Selic, CDI, IPCA) da API pública do Banco Central (SGS).

Os endereços são fixos (nunca vêm do usuário) e o resultado fica em cache por algumas horas.
Se o Banco Central estiver fora do ar, a API responde sem os valores em vez de falhar.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
FAIL_SECONDS = 120
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


def _fetch_one(key: str, code: int) -> tuple[str, dict[str, Any] | None]:
    try:
        value, date = fetch_series(code)
        return key, {"value": value, "date": date}
    except Exception as exc:  # rede, formato inesperado etc.
        logger.warning("Falha ao buscar a série %s do BCB: %s", code, exc)
        return key, None


def get_indicators() -> dict[str, Any]:
    with _lock:
        if _cache and time.monotonic() < _cache["expires"]:
            return _cache["value"]
        previous = _cache.get("value")

    # As três séries em paralelo: se o BCB estiver lento, espera uma vez só.
    with ThreadPoolExecutor(max_workers=len(SERIES)) as pool:
        results = dict(pool.map(lambda item: _fetch_one(*item), SERIES.items()))

    values: dict[str, Any] = {"available": True}
    for key in SERIES:
        found = results.get(key)
        if found is None and previous and previous.get(key):
            found = previous[key]  # último valor bom (taxas mudam pouco)
        values[key] = found
        if found is None:
            values["available"] = False
    values["fetched_at"] = datetime.now(UTC)

    # Falha fica em cache curto: tenta de novo daqui a pouco sem travar cada tela.
    complete = all(results.get(key) for key in SERIES)
    with _lock:
        _cache.update(
            {
                "expires": time.monotonic() + (CACHE_SECONDS if complete else FAIL_SECONDS),
                "value": values,
            }
        )
    return values


def clear_cache() -> None:
    with _lock:
        _cache.clear()
