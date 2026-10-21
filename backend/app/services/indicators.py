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


# ---------------------------------------------------------------- inflação (v1.3)

IPCA_MONTHLY = 433  # IPCA, variação mensal (%)
IPCA_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial=01/01/1995"
)
_ipca: dict[str, Any] = {}


def ipca_monthly() -> dict[str, float]:
    """IPCA de cada mês desde 1995 ("AAAA-MM" → % no mês). Cache de 12 h; guarda o último bom."""
    with _lock:
        if _ipca and time.monotonic() < _ipca["expires"]:
            return _ipca["value"]
        previous = _ipca.get("value")
    try:
        request = Request(IPCA_URL, headers={"Accept": "application/json"})
        with urlopen(request, timeout=TIMEOUT_SECONDS * 2) as response:  # noqa: S310 (URL fixa)
            data = json.load(response)
        value = {f"{row['data'][6:10]}-{row['data'][3:5]}": float(row["valor"]) for row in data}
        expires = time.monotonic() + 12 * 3600
    except Exception as exc:  # rede, formato inesperado etc.
        logger.warning("Falha ao buscar o IPCA mensal do BCB: %s", exc)
        value = previous or {}
        expires = time.monotonic() + FAIL_SECONDS
    with _lock:
        _ipca.update({"expires": expires, "value": value})
    return value


def correct_by_inflation(amount: float, start: str, end: str) -> dict[str, Any]:
    """Corrige um valor de `start` (AAAA-MM) até `end` pelo IPCA dos meses seguintes ao inicial."""
    from app.core.errors import AppError

    series = ipca_monthly()
    if not series:
        raise AppError(
            503, "ipca_unavailable", "O IPCA do Banco Central não respondeu. Tente mais tarde."
        )
    last = max(series)
    end = min(end, last)
    if start >= end:
        raise AppError(400, "invalid_period", "Escolha um mês inicial anterior ao final.")
    if start < min(series):
        raise AppError(400, "invalid_period", "O IPCA está disponível a partir de janeiro de 1995.")
    factor = 1.0
    months = 0
    for month in sorted(series):
        if start < month <= end:
            factor *= 1 + series[month] / 100
            months += 1
    return {
        "amount": round(amount, 2),
        "corrected": round(amount * factor, 2),
        "inflation_pct": round((factor - 1) * 100, 2),
        "start": start,
        "end": end,
        "months": months,
        "last_available": last,
    }
