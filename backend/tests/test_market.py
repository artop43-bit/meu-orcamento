from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.services import indicators, market
from tests.conftest import create_verified_user, login

CALLS: list[str] = []


def stock(symbol: str, price: float, change: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "longName": f"Empresa {symbol}",
        "regularMarketPrice": price,
        "regularMarketChangePercent": change,
        "regularMarketVolume": 1_000_000,
        "historicalDataPrice": [
            {"date": 1792000000, "close": price - 1},
            {"date": 1792086400, "close": price},
        ],
    }


def fake_get_json(url: str) -> Any:
    CALLS.append(url)
    if "quote/list" in url:
        return {
            "stocks": [
                {"stock": "AAAA3F", "name": "Fracionário", "close": 1, "change": 90, "volume": 9e6},
                {"stock": "BBBB3", "name": "Pouco negócio", "close": 1, "change": 50, "volume": 10},
                {"stock": "PETR4", "name": "Petrobras", "close": 60, "change": 4, "volume": 5e7},
            ]
        }
    if "brapi.dev/api/quote/" in url:
        symbol = url.split("quote/")[1].split("?")[0]
        if symbol == "XXXX3":
            return {"results": []}
        return {"results": [stock(symbol.replace("%5E", "^"), 60.0, 4.0)]}
    if "awesomeapi" in url:
        return {
            "USDBRL": {"bid": "5.06", "pctChange": "0.04"},
            "EURBRL": {"bid": "5.68", "pctChange": "-0.3"},
        }
    if "simple/price" in url:
        return {
            "bitcoin": {"brl": 400000.0, "brl_24h_change": 1.5},
            "ethereum": {"brl": 12000.0, "brl_24h_change": -0.5},
            "solana": {"brl": 900.0, "brl_24h_change": 2.0},
        }
    if "market_chart" in url:
        return {"prices": [[1792000000000, 390000.0], [1792086400000, 400000.0]]}
    raise AssertionError(f"URL inesperada: {url}")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    CALLS.clear()
    market.clear_cache()
    indicators.clear_cache()
    monkeypatch.setattr(market, "get_json", fake_get_json)
    rates = {432: 15.0, 4389: 14.9, 13522: 5.0}
    monkeypatch.setattr(indicators, "fetch_series", lambda code: (rates[code], "01/10/2026"))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def test_market_requires_login(client: TestClient) -> None:
    assert client.get("/api/market/overview").status_code == 401


def test_overview_without_token(user: TestClient) -> None:
    data = user.get("/api/market/overview").json()
    assert data["indexes"] == []
    assert data["indexes_need_token"] is True
    assert [c["symbol"] for c in data["currencies"]] == ["USD", "EUR"]
    assert [c["symbol"] for c in data["crypto"]] == ["BTC", "ETH", "SOL"]
    # Fracionário e papel sem liquidez ficam fora dos rankings.
    assert [g["symbol"] for g in data["gainers"]] == ["PETR4"]
    assert data["fixed_income"]["selic"]["value"] == 15.0
    assert "não é recomendação" in data["disclaimer"]
    assert not any("token=" in url for url in CALLS)


def test_overview_with_token_has_indexes(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "brapi_token", "teste")
    data = user.get("/api/market/overview").json()
    assert [i["name"] for i in data["indexes"]] == ["Ibovespa", "IFIX"]
    assert all(i["kind"] == "index" for i in data["indexes"])


def test_results_are_cached(user: TestClient) -> None:
    user.get("/api/market/overview")
    first = len(CALLS)
    user.get("/api/market/overview")
    assert len(CALLS) == first


def test_asset_sheet_stock_and_crypto(user: TestClient) -> None:
    data = user.get("/api/market/asset/petr4?range=1mo").json()
    assert data["quote"]["symbol"] == "PETR4"
    assert [p["close"] for p in data["history"]] == [59.0, 60.0]
    crypto = user.get("/api/market/asset/BTC").json()
    assert crypto["quote"]["kind"] == "crypto"
    assert len(crypto["history"]) == 2
    assert user.get("/api/market/asset/XXXX3").status_code == 404
    assert user.get("/api/market/asset/PETR4;rm").status_code == 400
    assert user.get("/api/market/asset/PETR4?range=10y").status_code == 422


def test_watchlist(user: TestClient) -> None:
    assert user.post("/api/market/watchlist", json={"symbol": "petr4"}).status_code == 201
    assert user.post("/api/market/watchlist", json={"symbol": "BTC"}).status_code == 201
    assert user.post("/api/market/watchlist", json={"symbol": "PETR4"}).status_code == 409
    assert user.post("/api/market/watchlist", json={"symbol": "a b"}).status_code == 422
    quotes = user.get("/api/market/watchlist").json()
    assert [(q["symbol"], q["price"]) for q in quotes] == [("PETR4", 60.0), ("BTC", 400000.0)]
    assert user.delete("/api/market/watchlist/PETR4").status_code == 204
    assert [q["symbol"] for q in user.get("/api/market/watchlist").json()] == ["BTC"]


def test_fixed_income_simulator(user: TestClient) -> None:
    data = user.get("/api/market/fixed-income/simulate?amount=1000&months=12").json()
    rows = {r["key"]: r for r in data["results"]}
    assert set(rows) == {"poupanca", "tesouro_selic", "cdb", "lci_lca"}
    # Selic acima de 8,5%: poupança rende 0,5% ao mês (~6,17% a.a.).
    assert rows["poupanca"]["annual_rate"] == pytest.approx(6.17, abs=0.01)
    assert rows["poupanca"]["ir_pct"] == 0
    assert rows["cdb"]["ir_pct"] == 20.0
    assert rows["cdb"]["gross"] == pytest.approx(1149.0, abs=0.01)
    assert rows["cdb"]["net"] == pytest.approx(1119.2, abs=0.01)
    assert rows["lci_lca"]["net"] == rows["lci_lca"]["gross"]


def test_portfolio_refresh_prices_tickers(user: TestClient) -> None:
    base = {"kind": "acoes", "invested_amount": "500.00", "current_value": "500.00"}
    user.post(
        "/api/investments", json={**base, "name": "Petrobras", "ticker": "petr4", "quantity": "10"}
    )
    user.post(
        "/api/investments",
        json={**base, "name": "CDB", "kind": "renda_fixa", "current_value": "100.00"},
    )
    data = user.post("/api/market/portfolio/refresh").json()
    assert [(u["ticker"], u["current_value"]) for u in data["updated"]] == [("PETR4", "600.00")]
    values = {i["name"]: i["current_value"] for i in user.get("/api/investments").json()}
    assert values == {"Petrobras": "600.00", "CDB": "100.00"}
    titles = [c["title"] for c in data["comments"]]
    assert "Carteira concentrada" in titles
    texts = " ".join(c["text"] for c in data["comments"]).lower()
    # CVM: descreve, nunca manda comprar/vender.
    assert "compre" not in texts and "venda " not in texts
