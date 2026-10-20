"""v1.0 (A): financiamentos e empréstimos, outras dívidas, patrimônio e peso das dívidas."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.models import Expense, NetWorthSnapshot
from app.services import budget as budget_service
from app.services import loans as loan_service
from tests.conftest import create_verified_user, login


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def new_loan(client: TestClient, **data: Any) -> dict[str, Any]:
    payload = {
        "kind": "personal",
        "name": "Empréstimo do carro",
        "principal": "10000.00",
        "rate": "1",
        "rate_period": "monthly",
        "system": "price",
        "installments": 12,
        "first_due": "2030-01-10",
        **data,
    }
    response = client.post("/api/loans", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def loan_expenses(db: Session, loan_id: str) -> list[Expense]:
    db.expire_all()
    return list(
        db.scalars(
            select(Expense)
            .where(Expense.loan_id == __import__("uuid").UUID(loan_id))
            .order_by(Expense.installment_number)
        )
    )


# ---------------------------------------------------------------- matemática


def test_price_schedule_matches_formula() -> None:
    rows = loan_service.schedule(Decimal("10000"), 0.01, 12, "price")
    assert len(rows) == 12
    # PMT = 10000 * 0,01 / (1 − 1,01^−12) = 888,49
    assert {r.payment for r in rows[:-1]} == {Decimal("888.49")}
    assert rows[0].interest == Decimal("100.00") and rows[0].amortization == Decimal("788.49")
    assert rows[-1].balance == 0
    assert sum(r.amortization for r in rows) == Decimal("10000")
    # A última parcela absorve os centavos (fica a poucos centavos da fixa).
    assert abs(rows[-1].payment - Decimal("888.49")) < Decimal("0.10")


def test_sac_schedule_decreases() -> None:
    rows = loan_service.schedule(Decimal("12000"), 0.01, 12, "sac")
    assert rows[0].payment == Decimal("1120.00") and rows[-1].payment == Decimal("1010.00")
    assert all(r.amortization == Decimal("1000.00") for r in rows)
    assert rows[-1].balance == 0


def test_rates_and_cet() -> None:
    assert round(loan_service.monthly_rate(Decimal("12"), "yearly") * 100, 4) == 0.9489
    assert round(loan_service.yearly_from_monthly(0.01) * 100, 2) == 12.68
    rows = loan_service.schedule(Decimal("10000"), 0.01, 12, "price")
    assert (
        round(loan_service.cet_monthly(Decimal("10000"), [r.payment for r in rows]) * 100, 2) == 1.0
    )
    # Seguro na parcela encarece o custo efetivo.
    with_insurance = loan_service.schedule(Decimal("10000"), 0.01, 12, "price", Decimal("20"))
    cet = loan_service.cet_monthly(Decimal("10000"), [r.payment for r in with_insurance])
    assert cet * 100 > 1.3


def test_zero_rate_splits_evenly() -> None:
    rows = loan_service.schedule(Decimal("1200"), 0.0, 12, "price")
    assert {r.payment for r in rows} == {Decimal("100.00")} and rows[-1].balance == 0


# ---------------------------------------------------------------- financiamento no orçamento


def test_loan_creates_installments_and_tracks_balance(user: TestClient, db: Session) -> None:
    loan = new_loan(user)
    assert loan["first_payment"] == "888.49" and loan["paid_installments"] == 0
    assert loan["balance"] == "10000.00" and loan["cet_monthly"] == pytest.approx(1.0, abs=0.01)
    assert loan["end"] == "2030-12-10"
    expenses = loan_expenses(db, loan["id"])
    assert len(expenses) == 12
    first = expenses[0]
    assert (first.month, first.due_date, first.amount) == (
        date(2030, 1, 1),
        date(2030, 1, 10),
        Decimal("888.49"),
    )
    assert first.description == "Empréstimo do carro (1/12)"
    # A categoria padrão do empréstimo pessoal é "Outros".
    cats = {c["id"]: c["name"] for c in user.get("/api/categories").json()}
    assert cats[str(first.category_id)] == "Outros"
    # Pagar a parcela no orçamento baixa o saldo devedor.
    user.patch(f"/api/expenses/{first.id}", json={"paid": True})
    [row] = user.get("/api/debts").json()["loans"]
    assert row["paid_installments"] == 1 and row["balance"] == "9211.51"
    assert row["next_payment"] == "888.49" and row["next_due"] == "2030-02-10"


def test_loan_in_progress_and_home_category(user: TestClient, db: Session) -> None:
    loan = new_loan(
        user,
        kind="home",
        name="Apartamento",
        principal="240000.00",
        rate="9.5",
        rate_period="yearly",
        system="sac",
        installments=360,
        first_due="2027-03-05",
        paid_before=34,
        insurance_monthly="45.00",
    )
    expenses = loan_expenses(db, loan["id"])
    assert len(expenses) == 326 and expenses[0].installment_number == 35
    assert expenses[0].due_date == date(2030, 1, 5)
    cats = {c["id"]: c["name"] for c in user.get("/api/categories").json()}
    assert cats[str(expenses[0].category_id)] == "Moradia"
    # SAC com seguro: parcela 35 = amortização + juros + seguro; saldo depois de 34 parcelas.
    assert Decimal(loan["balance"]) == Decimal("240000.00") - Decimal("666.67") * 34
    assert expenses[0].amount > expenses[-1].amount
    bad = user.post(
        "/api/loans",
        json={
            "kind": "personal",
            "name": "x",
            "principal": "1000",
            "rate": "1",
            "installments": 10,
            "first_due": "2030-01-01",
            "paid_before": 10,
        },
    )
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_paid"


def test_update_regenerates_only_unpaid(user: TestClient, db: Session) -> None:
    loan = new_loan(user)
    first = loan_expenses(db, loan["id"])[0]
    user.patch(f"/api/expenses/{first.id}", json={"paid": True})
    updated = user.patch(f"/api/loans/{loan['id']}", json={"rate": "2", "name": "Empréstimo"})
    assert updated.status_code == 200, updated.text
    expenses = loan_expenses(db, loan["id"])
    assert len(expenses) == 12
    assert expenses[0].id == first.id and expenses[0].amount == Decimal("888.49")
    assert expenses[1].amount > Decimal("900") and expenses[1].description == "Empréstimo (2/12)"


def test_delete_keeps_paid_history(user: TestClient, db: Session) -> None:
    loan = new_loan(user)
    first = loan_expenses(db, loan["id"])[0]
    user.patch(f"/api/expenses/{first.id}", json={"paid": True})
    assert user.delete(f"/api/loans/{loan['id']}").status_code == 204
    db.expire_all()
    left = list(db.scalars(select(Expense)))
    assert [e.id for e in left] == [first.id] and left[0].loan_id is None


def test_table_and_extra_amortization(user: TestClient) -> None:
    loan = new_loan(user)
    table = user.get(f"/api/loans/{loan['id']}/table").json()
    assert len(table) == 12 and table[0]["due"] == "2030-01-10" and table[-1]["balance"] == "0.00"
    term = user.post(
        f"/api/loans/{loan['id']}/simulate", json={"amount": "3000.00", "after": 2, "mode": "term"}
    ).json()
    assert term["months_before"] == 10 and term["months_after"] < 10
    assert Decimal(term["interest_saved"]) > 0
    assert term["payment_after"] == term["payment_before"]
    payment = user.post(
        f"/api/loans/{loan['id']}/simulate",
        json={"amount": "3000.00", "after": 2, "mode": "payment"},
    ).json()
    assert payment["months_after"] == 10
    assert Decimal(payment["payment_after"]) < Decimal(payment["payment_before"])
    too_much = user.post(f"/api/loans/{loan['id']}/simulate", json={"amount": "99999.00"})
    assert too_much.status_code == 400


def test_sac_extra_amortization_shortens_term(user: TestClient) -> None:
    loan = new_loan(user, system="sac", principal="12000.00")
    out = user.post(
        f"/api/loans/{loan['id']}/simulate", json={"amount": "2000.00", "mode": "term"}
    ).json()
    assert out["months_before"] == 12 and out["months_after"] == 10


def test_loans_are_private(client: TestClient, outbox: list[OutgoingEmail], db: Session) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    loan = new_loan(client)
    client.post("/api/auth/logout")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    assert client.get(f"/api/loans/{loan['id']}/table").status_code == 404
    assert client.patch(f"/api/loans/{loan['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/loans/{loan['id']}").status_code == 404
    assert client.get("/api/debts").json()["loans"] == []


# ---------------------------------------------------------------- outras dívidas e patrimônio


def test_overview_net_worth_and_snapshot(user: TestClient, db: Session) -> None:
    new_loan(user)
    other = user.post(
        "/api/other-debts",
        json={"name": "Acordo com o banco", "balance": "1500.00", "monthly_payment": "250.00"},
    )
    assert other.status_code == 201, other.text
    user.put(
        f"/api/other-debts/{other.json()['id']}",
        json={"name": "Acordo com o banco", "balance": "1250.00", "monthly_payment": "250.00"},
    )
    user.post(
        "/api/investments",
        json={
            "name": "Tesouro Selic",
            "kind": "tesouro",
            "invested_amount": "5000.00",
            "current_value": "5200.00",
        },
    )
    card = user.post("/api/cards", json={"name": "Nubank", "closing_day": 3, "due_day": 10}).json()
    user.post(
        "/api/months/2030-01/expenses",
        json={
            "description": "Geladeira",
            "amount": "3000.00",
            "installments": 3,
            "amount_mode": "total",
            "card_id": card["id"],
            "purchase_date": "2030-01-02",
        },
    )
    data = user.get("/api/debts").json()
    # Parcelas do cartão em meses futuros (fev e mar) contam como dívida assumida.
    assert data["card_installments"] == "2000.00"
    assert data["debts"] == "13250.00"  # 10000 + 1250 + 2000
    assert data["monthly_payments"] == "1138.49"
    assert Decimal(data["assets"]) >= Decimal("5200.00")
    assert Decimal(data["net_worth"]) == Decimal(data["assets"]) - Decimal("13250.00")
    assert len(data["history"]) == 1
    # Ver de novo no mesmo mês atualiza a foto em vez de duplicar.
    user.get("/api/debts")
    db.expire_all()
    assert len(list(db.scalars(select(NetWorthSnapshot)))) == 1
    assert user.delete(f"/api/other-debts/{other.json()['id']}").status_code == 204


def test_consultant_warns_about_heavy_debts(user: TestClient) -> None:
    user.post("/api/months/2030-01/incomes", json={"description": "Salário", "amount": "2500.00"})
    new_loan(user)  # 888,49 por mês = 35,5% da renda
    insights = user.get("/api/analysis/insights?month=2030-01").json()
    titles = [a["title"] for a in insights["alerts"]]
    assert "Parcelas de dívidas acima da referência" in titles


def test_backup_and_start_over_include_debts(user: TestClient, db: Session) -> None:
    from tests.conftest import PASSWORD

    loan = new_loan(user)
    user.post("/api/other-debts", json={"name": "Acordo", "balance": "900.00"})
    backup = user.get("/api/export/backup").json()
    assert len(backup["loans"]) == 1 and len(backup["other_debts"]) == 1
    assert sum(1 for e in backup["expenses"] if e["loan_id"] == loan["id"]) == 12

    counts = user.get("/api/account/reset").json()["counts"]
    assert counts["debts"] == 2
    first = loan_expenses(db, loan["id"])[0]
    user.patch(f"/api/expenses/{first.id}", json={"paid": True})
    out = user.post(
        "/api/account/reset",
        json={"areas": ["debts"], "password": PASSWORD, "confirmation": "COMEÇAR DO ZERO"},
    )
    assert out.status_code == 200, out.text
    db.expire_all()
    left = list(db.scalars(select(Expense)))
    # A parcela paga fica no histórico, sem o vínculo; as a pagar somem com o contrato.
    assert [e.id for e in left] == [first.id] and left[0].loan_id is None
    assert user.get("/api/debts").json()["loans"] == []

    # Restaurar o backup traz o contrato e as parcelas de volta, sem duplicar a já existente.
    import json

    raw = json.dumps(backup).encode()
    restored = user.post(
        "/api/import/restore", files={"file": ("backup.json", raw, "application/json")}
    )
    assert restored.status_code == 200, restored.text
    data = user.get("/api/debts").json()
    assert len(data["loans"]) == 1 and len(data["others"]) == 1
