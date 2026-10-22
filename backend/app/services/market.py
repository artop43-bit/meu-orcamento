"""Mercado: cotações, índices, cripto e renda fixa, só para informação.

Fontes públicas com endereços fixos (o usuário só escolhe o código do ativo, validado):
- brapi.dev: ações, FIIs e índices da B3 (Ibovespa e IFIX exigem o token BRAPI_TOKEN);
- AwesomeAPI: dólar e euro comercial;
- CoinGecko: criptomoedas;
- Banco Central (services/indicators.py): Selic, CDI e IPCA.

Tudo fica em cache por alguns minutos para respeitar os limites gratuitos. Falhas viram
"indisponível" em vez de erro. NUNCA recomenda compra ou venda (CVM, Resolução 20):
os textos descrevem a carteira e explicam conceitos, sem indicar ativos.
"""

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Investment, User, WatchItem
from app.services import indicators

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Informativo, não é recomendação de investimento. Cotações podem ter atraso; "
    "rentabilidade passada não garante rentabilidade futura."
)
TIMEOUT_SECONDS = 6
QUOTE_TTL = 120
LIST_TTL = 300
CHART_TTL = 900
FAIL_TTL = 60
# Se a fonte recusar (limite de consultas) ou cair, a tela continua com o último dado bom
# por até 12 horas, mostrando o horário dele, em vez de ficar vazia.
STALE_MAX_SECONDS = 12 * 3600
# O plano grátis da brapi recusa consultas simultâneas: uma de cada vez, com um respiro.
BRAPI_GAP_SECONDS = 0.35
RETRY_WAIT_SECONDS = 1.5

BRAPI = "https://brapi.dev/api"
AWESOME = "https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL"
COINGECKO = "https://api.coingecko.com/api/v3"

# Código curto → id no CoinGecko.
CRYPTO = {
    "BTC": ("bitcoin", "Bitcoin"),
    "ETH": ("ethereum", "Ethereum"),
    "SOL": ("solana", "Solana"),
    "USDT": ("tether", "Tether (dólar digital)"),
    "BNB": ("binancecoin", "BNB"),
    "XRP": ("ripple", "XRP"),
    "ADA": ("cardano", "Cardano"),
    "DOGE": ("dogecoin", "Dogecoin"),
}
INDEXES = {"^BVSP": "Ibovespa", "IFIX.SA": "IFIX"}
SYMBOL_RE = re.compile(r"^\^?[A-Z0-9]{2,10}(\.SA)?$")
RANGES = {"5d": ("5d", "1d"), "1mo": ("1mo", "1d"), "3mo": ("3mo", "1d"), "1y": ("1y", "1wk")}
CRYPTO_DAYS = {"5d": 5, "1mo": 30, "3mo": 90, "1y": 365}

# chave → (expira_em, valor, obtido_em [monotônico], obtido_em [data/hora])
_cache: dict[str, tuple[float, Any, float, datetime]] = {}
_lock = threading.Lock()
_brapi_lock = threading.Lock()
_brapi_last = 0.0
_sleep = time.sleep  # substituído nos testes
# Chaves sendo atualizadas em segundo plano (uma atualização por chave de cada vez).
_refreshing: set[str] = set()


def _spawn(job: Any) -> None:
    """Roda a atualização fora da requisição (substituído nos testes)."""
    threading.Thread(target=job, daemon=True).start()


def clear_cache() -> None:
    global _brapi_last
    with _lock:
        _cache.clear()
    _brapi_last = 0.0


def get_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "MeuOrcamento"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (URLs fixas)
        return json.load(response)


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, HTTPError) and exc.code == 429


def fetch_json(url: str, *, brapi: bool = False) -> Any:
    """Busca com fila (brapi: uma consulta por vez) e uma nova tentativa se a fonte recusar."""
    global _brapi_last
    for attempt in range(2):
        try:
            if not brapi:
                return get_json(url)
            with _brapi_lock:
                wait = _brapi_last + BRAPI_GAP_SECONDS - time.monotonic()
                if wait > 0:
                    _sleep(wait)
                try:
                    return get_json(url)
                finally:
                    _brapi_last = time.monotonic()
        except Exception as exc:
            if attempt == 0 and _is_rate_limit(exc):
                _sleep(RETRY_WAIT_SECONDS)
                continue
            raise
    raise RuntimeError("inalcançável")  # pragma: no cover


def _cached(key: str, ttl: int, fetch: Any) -> Any:
    """Resultado em cache. Vencido, a tela recebe na hora o último dado bom (até 12 h) e a
    atualização roda em segundo plano (v1.4.3): ninguém espera a fonte externa, que pode
    levar segundos ou recusar por limite. Só a primeira consulta, sem dado guardado, espera."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        usable = hit is not None and hit[1] is not None and now - hit[2] <= STALE_MAX_SECONDS
        if usable and key in _refreshing:
            return hit[1]
        if usable:
            _refreshing.add(key)
    if usable:
        assert hit is not None

        def job() -> None:
            try:
                _refresh(key, ttl, fetch, hit)
            finally:
                with _lock:
                    _refreshing.discard(key)

        _spawn(job)
        return hit[1]
    return _refresh(key, ttl, fetch, hit)


def _refresh(key: str, ttl: int, fetch: Any, hit: Any) -> Any:
    """Busca na fonte e guarda. Se falhar, mantém o último dado bom (até 12 h) e tenta de
    novo em 1 minuto; sem dado anterior, devolve None."""
    now = time.monotonic()
    try:
        value = fetch()
        entry = (now + ttl, value, now, datetime.now(UTC))
    except Exception as exc:  # rede, limite, formato inesperado
        logger.warning("Mercado: falha em %s: %s", key, exc)
        if hit and hit[1] is not None and now - hit[2] <= STALE_MAX_SECONDS:
            entry = (now + FAIL_TTL, hit[1], hit[2], hit[3])
        else:
            entry = (now + FAIL_TTL, None, now, datetime.now(UTC))
    with _lock:
        _cache[key] = entry
    return entry[1]


def as_of(key: str, ttl: int) -> datetime | None:
    """Quando o dado em cache foi obtido, se já passou da validade (dado antigo em uso).
    Um minuto de folga: enquanto a atualização em segundo plano corre, o dado não é "antigo"."""
    with _lock:
        hit = _cache.get(key)
    if not hit or hit[1] is None:
        return None
    return hit[3] if time.monotonic() - hit[2] > ttl + 60 else None


def normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if not SYMBOL_RE.match(value):
        raise AppError(400, "invalid_symbol", "Código inválido. Ex.: PETR4, MXRF11, BTC.")
    return value


def is_crypto(symbol: str) -> bool:
    return symbol in CRYPTO


def _brapi_url(path: str, params: dict[str, Any] | None = None) -> str:
    params = dict(params or {})
    token = get_settings().brapi_token
    if token:
        params["token"] = token
    query = f"?{urlencode(params)}" if params else ""
    return f"{BRAPI}/{path}{query}"


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- cotações


def _stock_quote(raw: dict[str, Any]) -> dict[str, Any]:
    symbol = str(raw.get("symbol", ""))
    return {
        "symbol": symbol,
        "name": INDEXES.get(symbol) or raw.get("longName") or raw.get("shortName") or symbol,
        "kind": "index" if symbol in INDEXES else ("fii" if symbol.endswith("11") else "stock"),
        "price": _float(raw.get("regularMarketPrice")),
        "change_pct": _float(raw.get("regularMarketChangePercent")),
        "day_high": _float(raw.get("regularMarketDayHigh")),
        "day_low": _float(raw.get("regularMarketDayLow")),
        "volume": _float(raw.get("regularMarketVolume")),
        "year_high": _float(raw.get("fiftyTwoWeekHigh")),
        "year_low": _float(raw.get("fiftyTwoWeekLow")),
        "currency": raw.get("currency") or "BRL",
        "logo": raw.get("logourl"),
        "updated_at": raw.get("regularMarketTime"),
    }


def stock_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Cotações da B3 (uma chamada por ativo: o plano grátis não aceita vários de uma vez)."""
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        data = _cached(
            f"quote:{symbol}",
            QUOTE_TTL,
            lambda s=symbol: fetch_json(_brapi_url(f"quote/{quote(s)}"), brapi=True),
        )
        if data and data.get("results"):
            result[symbol] = _stock_quote(data["results"][0])
    return result


def crypto_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    wanted = [s for s in symbols if s in CRYPTO]
    if not wanted:
        return {}
    ids = ",".join(sorted(CRYPTO[s][0] for s in wanted))
    params = urlencode({"ids": ids, "vs_currencies": "brl", "include_24hr_change": "true"})
    data = _cached(
        f"crypto:{ids}", QUOTE_TTL, lambda: fetch_json(f"{COINGECKO}/simple/price?{params}")
    )
    result: dict[str, dict[str, Any]] = {}
    for symbol in wanted:
        coin_id, name = CRYPTO[symbol]
        row = (data or {}).get(coin_id)
        if row:
            result[symbol] = {
                "symbol": symbol,
                "name": name,
                "kind": "crypto",
                "price": _float(row.get("brl")),
                "change_pct": _float(row.get("brl_24h_change")),
                "currency": "BRL",
            }
    return result


def quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [normalize_symbol(s) for s in symbols]
    result = crypto_quotes([s for s in normalized if is_crypto(s)])
    result.update(stock_quotes([s for s in normalized if not is_crypto(s)]))
    return result


def currencies() -> list[dict[str, Any]]:
    data = _cached("currencies", QUOTE_TTL, lambda: fetch_json(AWESOME)) or {}
    out = []
    for key, name in (("USDBRL", "Dólar"), ("EURBRL", "Euro")):
        row = data.get(key)
        if row:
            out.append(
                {
                    "symbol": key[:3],
                    "name": name,
                    "kind": "currency",
                    "price": _float(row.get("bid")),
                    "change_pct": _float(row.get("pctChange")),
                    "currency": "BRL",
                }
            )
    return out


# ---------------------------------------------------------------- painel


LIST_KEY = "list:volume"


def _liquid_stocks() -> list[dict[str, Any]]:
    """Ações mais negociadas do dia (uma consulta à brapi). Altas e baixas saem desta lista:
    assim o ranking só tem papéis com volume relevante e a fonte recebe 1 consulta, não 3."""
    params = {"sortBy": "volume", "sortOrder": "desc", "limit": 100, "type": "stock"}
    data = _cached(
        LIST_KEY, LIST_TTL, lambda: fetch_json(_brapi_url("quote/list", params), brapi=True)
    )
    rows = []
    for row in (data or {}).get("stocks", []):
        symbol = str(row.get("stock", ""))
        volume = _float(row.get("volume")) or 0
        change = _float(row.get("change"))
        # Fora: mercado fracionário (final F) e papéis quase sem negócio (distorcem a lista).
        if symbol.endswith("F") or volume < 500_000:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": row.get("name") or symbol,
                "kind": "fii" if symbol.endswith("11") else "stock",
                "price": _float(row.get("close")),
                "change_pct": change,
                "volume": volume,
                "logo": row.get("logo"),
                "currency": "BRL",
            }
        )
    return rows


def rankings() -> dict[str, list[dict[str, Any]]]:
    rows = _liquid_stocks()
    with_change = [r for r in rows if r["change_pct"] is not None]
    gainers = sorted(
        (r for r in with_change if r["change_pct"] > 0), key=lambda r: -r["change_pct"]
    )
    losers = sorted((r for r in with_change if r["change_pct"] < 0), key=lambda r: r["change_pct"])
    most = sorted(rows, key=lambda r: -r["volume"])
    return {"gainers": gainers[:5], "losers": losers[:5], "most_traded": most[:5]}


def overview() -> dict[str, Any]:
    """Painel do Mercado: índices, moedas, cripto, rankings do dia e renda fixa."""
    has_token = bool(get_settings().brapi_token)

    def brapi_part() -> dict[str, Any]:
        # Tudo o que é da brapi em sequência (a fila espaça as consultas).
        indexes = list(stock_quotes(list(INDEXES)).values()) if has_token else []
        return {"indexes": indexes, **rankings()}

    # Fontes diferentes em paralelo: a tela espera só pela mais lenta.
    jobs = {
        "brapi": brapi_part,
        "currencies": currencies,
        "crypto": lambda: list(crypto_quotes(["BTC", "ETH", "SOL"]).values()),
        "fixed_income": indicators.get_indicators,
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {key: pool.submit(job) for key, job in jobs.items()}
        result = {key: future.result() for key, future in futures.items()}
    brapi = result.pop("brapi")
    # Seções mostrando o último dado bom (a atualização falhou): a tela informa o horário.
    stale = {
        "indexes": max(
            (t for t in (as_of(f"quote:{s}", QUOTE_TTL) for s in INDEXES) if t), default=None
        ),
        "rankings": as_of(LIST_KEY, LIST_TTL),
        "currencies": as_of("currencies", QUOTE_TTL),
    }
    return {
        **result,
        **brapi,
        "stale_since": {k: v for k, v in stale.items() if v is not None},
        "indexes_need_token": not has_token,
        "disclaimer": DISCLAIMER,
        "fetched_at": datetime.now(UTC),
    }


def asset(symbol: str, range_key: str = "1mo") -> dict[str, Any]:
    """Ficha do ativo: cotação e histórico para o gráfico."""
    symbol = normalize_symbol(symbol)
    if range_key not in RANGES:
        raise AppError(400, "invalid_range", "Período inválido.")
    if is_crypto(symbol):
        found = crypto_quotes([symbol]).get(symbol)
        coin_id = CRYPTO[symbol][0]
        params = urlencode({"vs_currency": "brl", "days": CRYPTO_DAYS[range_key]})
        data = _cached(
            f"chart:{coin_id}:{range_key}",
            CHART_TTL,
            lambda: fetch_json(f"{COINGECKO}/coins/{coin_id}/market_chart?{params}"),
        )
        history = [
            {"date": datetime.fromtimestamp(ts / 1000, UTC).date().isoformat(), "close": price}
            for ts, price in (data or {}).get("prices", [])
        ]
    else:
        api_range, interval = RANGES[range_key]
        data = _cached(
            f"chart:{symbol}:{range_key}",
            CHART_TTL,
            lambda: fetch_json(
                _brapi_url(f"quote/{quote(symbol)}", {"range": api_range, "interval": interval}),
                brapi=True,
            ),
        )
        raw = (data or {}).get("results") or []
        found = _stock_quote(raw[0]) if raw else None
        history = [
            {
                "date": datetime.fromtimestamp(row["date"], UTC).date().isoformat(),
                "close": _float(row.get("close")),
            }
            for row in (raw[0].get("historicalDataPrice") or [] if raw else [])
            if row.get("close") is not None
        ]
    if found is None:
        raise AppError(404, "asset_not_found", "Não encontramos cotação para esse código agora.")
    # Um ponto por dia (o CoinGecko manda o último preço do dia também).
    by_day = {point["date"]: point for point in history}
    return {
        "quote": found,
        "history": list(by_day.values()),
        "range": range_key,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- renda fixa


def _ir_rate(days: int) -> float:
    """IR regressivo de renda fixa (sobre o rendimento)."""
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.20
    if days <= 720:
        return 0.175
    return 0.15


def simulate_fixed_income(amount: float, months: int, cdb_pct: float = 100.0) -> dict[str, Any]:
    """Quanto o valor renderia em cada aplicação, com as taxas de hoje (aproximação)."""
    data = indicators.get_indicators()
    selic = (data.get("selic") or {}).get("value")
    cdi = (data.get("cdi") or {}).get("value")
    ipca = (data.get("ipca_12m") or {}).get("value")
    if selic is None or cdi is None:
        raise AppError(503, "rates_unavailable", "As taxas do Banco Central estão indisponíveis.")
    years = months / 12
    days = months * 30  # convenção: 12 meses = 360 dias (faixas do IR)

    def grow(annual_pct: float) -> float:
        return amount * ((1 + annual_pct / 100) ** years)

    # Poupança: 0,5% ao mês (+TR) se Selic > 8,5%; senão 70% da Selic. TR ignorada.
    poupanca_annual = ((1.005**12) - 1) * 100 if selic > 8.5 else selic * 0.7
    options = [
        ("poupanca", "Poupança", poupanca_annual, 0.0),
        ("tesouro_selic", "Tesouro Selic", selic - 0.2, _ir_rate(days)),  # ~0,2% custódia B3
        ("cdb", f"CDB {cdb_pct:.0f}% do CDI", cdi * cdb_pct / 100, _ir_rate(days)),
        ("lci_lca", "LCI/LCA 90% do CDI", cdi * 0.9, 0.0),
    ]
    results = []
    for key, name, annual, ir in options:
        gross = grow(annual)
        earnings = gross - amount
        net = amount + earnings * (1 - ir)
        results.append(
            {
                "key": key,
                "name": name,
                "annual_rate": round(annual, 2),
                "ir_pct": round(ir * 100, 1),
                "gross": round(gross, 2),
                "net": round(net, 2),
                "earnings_net": round(net - amount, 2),
                "real_gain": (
                    round(net - amount * ((1 + ipca / 100) ** years), 2)
                    if ipca is not None
                    else None
                ),
            }
        )
    return {
        "amount": amount,
        "months": months,
        "selic": selic,
        "cdi": cdi,
        "ipca_12m": ipca,
        "results": results,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- acompanhando (watchlist)

WATCH_LIMIT = 30


def list_watch(db: Session, user: User) -> list[WatchItem]:
    return list(
        db.scalars(
            select(WatchItem).where(WatchItem.user_id == user.id).order_by(WatchItem.created_at)
        )
    )


def add_watch(db: Session, user: User, symbol: str) -> WatchItem:
    symbol = normalize_symbol(symbol)
    items = list_watch(db, user)
    if any(i.symbol == symbol for i in items):
        raise AppError(409, "already_watching", "Você já acompanha esse ativo.")
    if len(items) >= WATCH_LIMIT:
        raise AppError(400, "watch_limit", f"Acompanhe no máximo {WATCH_LIMIT} ativos.")
    item = WatchItem(user_id=user.id, symbol=symbol)
    db.add(item)
    db.commit()
    return item


def remove_watch(db: Session, user: User, symbol: str) -> None:
    symbol = normalize_symbol(symbol)
    item = db.scalar(
        select(WatchItem).where(WatchItem.user_id == user.id, WatchItem.symbol == symbol)
    )
    if item is None:
        raise AppError(404, "not_found", "Item não encontrado.")
    db.delete(item)
    db.commit()


def watch_quotes(db: Session, user: User) -> list[dict[str, Any]]:
    symbols = [i.symbol for i in list_watch(db, user)]
    found = quotes(symbols) if symbols else {}
    return [
        found.get(s) or {"symbol": s, "name": s, "kind": "unknown", "price": None} for s in symbols
    ]


# ---------------------------------------------------------------- carteira


def refresh_portfolio(db: Session, user: User) -> dict[str, Any]:
    """Atualiza o valor atual dos investimentos com código e quantidade pela cotação."""
    items = list(
        db.scalars(
            select(Investment).where(Investment.user_id == user.id).order_by(Investment.created_at)
        )
    )
    priced = [i for i in items if i.ticker and i.quantity]
    found = quotes([i.ticker for i in priced if i.ticker]) if priced else {}
    updated = []
    for item in priced:
        q = found.get((item.ticker or "").upper())
        if not q or q.get("price") is None:
            continue
        value = (Decimal(str(q["price"])) * Decimal(item.quantity or 0)).quantize(Decimal("0.01"))
        item.current_value = value
        updated.append(
            {
                "id": item.id,
                "ticker": item.ticker,
                "price": q["price"],
                "change_pct": q.get("change_pct"),
                "current_value": value,
            }
        )
    db.commit()
    return {"updated": updated, "comments": portfolio_comments(items), "disclaimer": DISCLAIMER}


KIND_LABELS = {
    "poupanca": "poupança",
    "renda_fixa": "renda fixa",
    "tesouro": "Tesouro Direto",
    "fundos": "fundos",
    "acoes": "ações",
    "fiis": "fundos imobiliários",
    "cripto": "cripto",
    "previdencia": "previdência",
    "outro": "outros",
}
VARIABLE_KINDS = {"acoes", "fiis", "cripto"}


def portfolio_comments(items: list[Investment]) -> list[dict[str, str]]:
    """Leitura da carteira em linguagem simples. Descreve e explica; não indica ativos."""
    total = sum((i.current_value for i in items), Decimal("0"))
    if total <= 0:
        return []
    comments: list[dict[str, str]] = []
    by_kind: dict[str, Decimal] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, Decimal("0")) + item.current_value

    biggest = max(items, key=lambda i: i.current_value)
    share = float(biggest.current_value / total * 100)
    if len(items) > 1 and share >= 50:
        comments.append(
            {
                "tone": "info",
                "title": "Carteira concentrada",
                "text": f"{share:.0f}% do total está em {biggest.name}. A concentração amplia o "
                "impacto de um único ativo sobre o patrimônio; a diversificação reduz esse risco.",
            }
        )
    variable = sum((v for k, v in by_kind.items() if k in VARIABLE_KINDS), Decimal("0"))
    variable_pct = float(variable / total * 100)
    if variable_pct > 0:
        comments.append(
            {
                "tone": "info",
                "title": "Renda variável",
                "text": f"{variable_pct:.0f}% da carteira está em renda variável (ações, FIIs, "
                "cripto), sujeita a oscilação diária. Avalie a exposição conforme o prazo e o "
                "perfil de risco.",
            }
        )
    crypto_pct = float(by_kind.get("cripto", Decimal("0")) / total * 100)
    if crypto_pct >= 20:
        comments.append(
            {
                "tone": "warning",
                "title": "Alta volatilidade em cripto",
                "text": f"{crypto_pct:.0f}% está em cripto, que pode variar mais de 10% num dia.",
            }
        )
    reserve = sum((i.current_value for i in items if i.is_emergency_reserve), Decimal("0"))
    if reserve == 0:
        comments.append(
            {
                "tone": "info",
                "title": "Reserva de emergência",
                "text": "Nenhum investimento está marcado como reserva. A reserva deve ter "
                "liquidez imediata e baixo risco; marque-a para que entre no score.",
            }
        )
    largest_kind = max(by_kind, key=lambda k: by_kind[k])
    comments.append(
        {
            "tone": "good",
            "title": "Resumo",
            "text": f"{len(items)} investimento(s); a maior parte em "
            f"{KIND_LABELS.get(largest_kind, largest_kind)} "
            f"({float(by_kind[largest_kind] / total * 100):.0f}%).",
        }
    )
    return comments
