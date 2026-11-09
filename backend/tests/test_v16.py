"""v1.6: estilo visual salvo na conta."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_verified_user, login
from tests.test_analysis import MONTH, expense
from tests.test_budget import Outbox


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def test_style_is_saved_on_the_account(user: TestClient) -> None:
    # Ainda não escolheu: o site usa o Padrão.
    assert user.get("/api/auth/me").json()["style"] is None
    out = user.patch("/api/me/appearance", json={"style": "glass"})
    assert out.json() == {"theme": None, "accent": None, "style": "glass"}
    assert user.get("/api/auth/me").json()["style"] == "glass"
    # Só o que foi enviado muda.
    out = user.patch("/api/me/appearance", json={"accent": "roxo"}).json()
    assert out["style"] == "glass" and out["accent"] == "roxo"
    assert user.patch("/api/me/appearance", json={"style": "padrao"}).json()["style"] == "padrao"


def test_unknown_style_is_rejected(user: TestClient) -> None:
    assert user.patch("/api/me/appearance", json={"style": "neon"}).status_code == 422
    assert user.get("/api/auth/me").json()["style"] is None


# ---------------------------------------------------------------- parcelas na previsão


def test_projection_reports_installments_part(user: TestClient) -> None:
    user.get(f"/api/months/{MONTH}")
    expense(user, "500", None, installments=3)  # parcela: entra em "installments"
    expense(user, "200", None)  # gasto avulso: não entra
    points = user.get(f"/api/analysis/projection?start={MONTH}&months=4").json()
    assert [Decimal(p["installments"]) for p in points] == [
        Decimal("500"),
        Decimal("500"),
        Decimal("500"),
        Decimal("0"),
    ]
    assert Decimal(points[0]["expenses"]) == Decimal("700")
