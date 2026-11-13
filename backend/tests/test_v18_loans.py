"""v1.8: empréstimos a amigos com juros e parcelas (tela Divisões)."""

import io
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models import User
from app.services import alerts
from app.services import loans_calc as calc
from tests.test_data import user  # noqa: F401  (fixture)

D = Decimal
FIRST = date(2030, 2, 10)
BASE = {"person": "João Silva", "principal": "1000", "first_due": "2030-02-10"}


def money(value: str | float) -> Decimal:
    return D(str(value)).quantize(D("0.01"))


# ---------------------------------------------------------------- contas


def test_rate_on_total_split_by_frequency() -> None:
    """ "Empresto mil e cobro 5%: quanto recebo por mês, semana ou dia?\""""
    for frequency, count, each in (("month", 1, "1050"), ("week", 4, "262.50"), ("day", 30, "35")):
        rows = calc.schedule(D("1000"), "total", 5, count, frequency, FIRST)
        assert sum(r.amount for r in rows) == D("1050")
        assert rows[0].amount == money(each)
    weekly = calc.schedule(D("1000"), "total", 5, 4, "week", FIRST)
    assert [r.due_date.day for r in weekly] == [10, 17, 24, 3]


def test_cents_close_on_the_last_installment() -> None:
    rows = calc.schedule(D("1000"), "total", 0, 3, "month", FIRST)
    assert [r.amount for r in rows] == [D("333.33"), D("333.33"), D("333.34")]
    assert rows[-1].balance == 0
    sac = calc.schedule(D("1000"), "sac", 3, 12, "month", FIRST)
    assert sum(r.principal for r in sac) == D("1000")
    assert sac[0].amount > sac[-1].amount


@pytest.mark.parametrize("mode", ["total", "simple", "price", "sac"])
def test_profit_gives_the_rate(mode: str) -> None:
    """ "Empresto mil e quero lucrar 200: quanto de taxa preciso colocar?\""""
    rate = calc.solve_rate(D("1000"), mode, 12, "month", FIRST, "profit", D("200"))
    assert rate is not None
    total = sum(r.amount for r in calc.schedule(D("1000"), mode, rate, 12, "month", FIRST))
    assert abs(total - D("1200")) <= D("0.02")


def test_known_rates_and_equivalents() -> None:
    assert calc.solve_rate(D("1000"), "total", 12, "month", FIRST, "profit", D("200")) == 20
    price = calc.solve_rate(D("1000"), "price", 12, "month", FIRST, "installment", D("100"))
    assert price == pytest.approx(2.922, abs=0.001)
    summary = calc.summary(D("1000"), "price", 2, 12, "month", FIRST)
    assert summary["monthly_equivalent"] == pytest.approx(2, abs=0.01)
    assert summary["yearly_equivalent"] == pytest.approx(26.82, abs=0.05)
    assert summary["usury_warning"] is True
    assert calc.summary(D("1000"), "price", 1, 12, "month", FIRST)["usury_warning"] is False
    # Impossível: lucro negativo ou parcela menor que a sem juros.
    assert calc.solve_rate(D("1000"), "price", 12, "month", FIRST, "total", D("900")) is None
    assert calc.solve_rate(D("1000"), "price", 12, "month", FIRST, "installment", D("50")) is None


def test_risk_and_late_charge() -> None:
    rows = calc.schedule(D("1000"), "total", 20, 12, "month", FIRST)
    assert calc.payback(rows, D("1000")) == 10
    assert calc.loss_if_stops(rows, D("1000"), 6) == D("400")
    assert calc.late_charge(D("100"), 15, 2, 1) == D("2.49")
    assert calc.late_charge(D("100"), 15, None, None) == 0


def test_market_comparison() -> None:
    out = calc.market(D("1000"), D("200"), 12, 10.0, 4.0)
    assert out is not None
    assert out["cdb_net"] == D("82.50")  # 10% ao ano, IR de 17,5%
    assert out["real_profit"] == D("153.85")
    assert calc.market(D("1000"), D("200"), 12, None, None) is None


# ---------------------------------------------------------------- API


def test_simulate_endpoint(user: TestClient) -> None:  # noqa: F811
    body = {**BASE, "mode": "price", "target": "profit", "value": "200", "count": 12}
    out = user.post("/api/friend-loans/simulate", json=body).json()
    assert out["total"] == "1200.00" or abs(D(out["total"]) - 1200) <= D("0.02")
    assert len(out["schedule"]) == 12 and out["usury_warning"] is True
    assert {c["mode"] for c in out["compare"]} == {"total", "simple", "price", "sac"}
    assert out["payback"] == 10
    bad = user.post("/api/friend-loans/simulate", json={**body, "target": "total", "value": "500"})
    assert bad.status_code == 400 and bad.json()["error"] == "impossible"
    too_many = user.post(
        "/api/friend-loans/simulate", json={**body, "frequency": "month", "count": 200}
    )
    assert too_many.status_code == 422


def _create(user: TestClient, **extra: object) -> dict:  # noqa: F811
    body = {**BASE, "mode": "total", "rate": "20", "count": 12, **extra}
    response = user.post("/api/friend-loans", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _month(user: TestClient, value: str) -> dict:  # noqa: F811
    return user.get(f"/api/months/{value}").json()


def test_loan_becomes_planned_income(user: TestClient) -> None:  # noqa: F811
    loan = _create(user)
    assert loan["total"] == "1200.00" and loan["profit"] == "200.00"
    assert loan["remaining"] == "1200.00" and loan["paid_count"] == 0
    feb = [i for i in _month(user, "2030-02")["incomes"] if "Empréstimo" in i["description"]]
    assert len(feb) == 1
    assert feb[0]["description"] == "Empréstimo · João Silva · 1/12"
    assert feb[0]["amount"] == "100.00"
    jan_2031 = _month(user, "2031-01")["incomes"]
    assert [i["description"] for i in jan_2031] == ["Empréstimo · João Silva · 12/12"]
    # Pagamento por semana: várias parcelas no mesmo mês viram uma linha só.
    weekly = _create(user, person="Ana", frequency="week", count=8, rate="5")
    lines = [i for i in _month(user, "2030-02")["incomes"] if "Ana" in i["description"]]
    assert len(lines) == 1 and lines[0]["description"] == "Empréstimo · Ana · 3 pagamentos"
    assert weekly["installments"][0]["amount"] == "131.25"


def test_receive_partial_early_and_undo(user: TestClient) -> None:  # noqa: F811
    loan = _create(user)
    lid = loan["id"]
    paid = user.post(
        f"/api/friend-loans/{lid}/receive", json={"number": 1, "on": "2030-02-08"}
    ).json()
    assert paid["paid_count"] == 1 and paid["received"] == "100.00"
    assert paid["profit_received"] == "16.67"
    feb = [i for i in _month(user, "2030-02")["incomes"] if "Empréstimo" in i["description"]]
    assert [(i["amount"], i["notes"]) for i in feb] == [("100.00", "Recebido")]
    # Parcial: R$ 40 da parcela 2 (fica parcial, com R$ 60 em aberto no mês dela).
    part = user.post(
        f"/api/friend-loans/{lid}/receive", json={"number": 2, "amount": "40", "on": "2030-03-01"}
    ).json()
    second = part["installments"][1]
    assert second["status"] == "partial" and second["open"] == "60.00"
    march = sorted(
        (i["amount"], i["notes"])
        for i in _month(user, "2030-03")["incomes"]
        if "Empréstimo" in i["description"]
    )
    assert march == [("40.00", "Recebido"), ("60.00", "Previsto (empréstimo na tela Divisões)")]
    # Adiantado: R$ 260 completa a 2 e paga a 3 e a 4.
    ahead = user.post(
        f"/api/friend-loans/{lid}/receive", json={"number": 2, "amount": "260", "on": "2030-03-02"}
    ).json()
    assert ahead["paid_count"] == 4 and ahead["remaining"] == "800.00"
    too_much = user.post(f"/api/friend-loans/{lid}/receive", json={"number": 5, "amount": "5000"})
    assert too_much.status_code == 400
    undone = user.delete(f"/api/friend-loans/{lid}/receive/4").json()
    assert undone["paid_count"] == 3 and undone["remaining"] == "900.00"


def test_payoff_with_discount_and_term(user: TestClient) -> None:  # noqa: F811
    loan = _create(user, late_fee="2", late_interest="1", description="Conserto do carro")
    lid = loan["id"]
    quote = user.get(f"/api/friend-loans/{lid}/payoff?on=2030-01-20").json()
    assert quote["remaining"] == "1200.00"
    assert D(quote["discount"]) == D("200.00")  # nenhuma venceu: sai todo o juro
    assert quote["value"] == "1000.00"
    pdf = user.get(f"/api/friend-loans/{lid}/term.pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert 'filename="termo-emprestimo_joaosilva.pdf"' in pdf.headers["content-disposition"]
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    text = re.sub(r"\s+", " ", text)
    assert "Termo de empréstimo" in text and "João Silva" in text
    assert "R$ 1.000,00" in text and "R$ 1.200,00" in text
    assert "multa de 2%" in text and "Conserto do carro" in text
    done = user.post(
        f"/api/friend-loans/{lid}/payoff", json={"on": "2030-01-20", "discount": True}
    ).json()
    assert done["settled_at"] and done["remaining"] == "0.00" and done["total"] == "1000.00"
    incomes = [i for i in _month(user, "2030-01")["incomes"] if "Empréstimo" in i["description"]]
    assert [i["amount"] for i in incomes] == ["1000.00"]
    assert not [i for i in _month(user, "2030-05")["incomes"] if "Empréstimo" in i["description"]]


def test_i_owe_becomes_expenses_and_delete_keeps_received(user: TestClient) -> None:  # noqa: F811
    loan = _create(user, direction="i_owe", person="Maria", count=3, rate="0", mode="none")
    lid = loan["id"]
    feb = [e for e in _month(user, "2030-02")["expenses"] if "Maria" in e["description"]]
    assert len(feb) == 1 and feb[0]["amount"] == "333.33" and feb[0]["paid"] is False
    user.post(f"/api/friend-loans/{lid}/receive", json={"number": 1, "on": "2030-02-10"})
    feb = [e for e in _month(user, "2030-02")["expenses"] if "Maria" in e["description"]]
    assert feb[0]["paid"] is True
    assert user.delete(f"/api/friend-loans/{lid}").status_code == 204
    assert [e["description"] for e in _month(user, "2030-02")["expenses"]] == [
        "Empréstimo · Maria · 1/3"
    ]
    assert not [e for e in _month(user, "2030-03")["expenses"] if "Maria" in e["description"]]
    assert user.get(f"/api/friend-loans/{lid}").status_code == 404


def test_board_alerts_and_bot(user: TestClient, db: Session) -> None:  # noqa: F811
    _create(user)
    user.post("/api/splits", json={"person": "joão silva", "amount": "50", "direction": "owes_me"})
    board = user.get("/api/splits").json()
    joao = board["people"][0]
    assert joao["person"] in ("João Silva", "joão silva")
    assert joao["balance"] == "1250.00" and len(joao["loans"]) == 1
    assert board["owed_to_me"] == "1250.00"
    assert board["loans"]["lent"] == "1000.00" and board["loans"]["profit_expected"] == "200.00"
    loans = user.get("/api/friend-loans").json()
    assert loans["totals"]["lent_count"] == 1

    answer = user.post("/api/ask", json={"question": "quanto o João ainda me deve?"}).json()
    assert answer["intent"] == "friend_loans"
    assert answer["answer"].endswith("ainda te deve R$ 1.250,00.")
    profit = user.post("/api/ask", json={"question": "quanto lucrei com empréstimos?"}).json()
    assert profit["intent"] == "friend_loans" and "R$ 200,00" in profit["answer"]
    who = user.post("/api/ask", json={"question": "quem me deve?"}).json()
    assert who["intent"] == "friend_loans" and "Te devem R$ 1.250,00" in who["answer"]

    assert not [a for a in user.get("/api/alerts").json() if a["kind"] == "loan_late"]
    owner = db.query(User).one()
    late = [
        a
        for a in alerts.month_alerts(db, owner, date(2030, 6, 1), date(2030, 6, 15))
        if a["kind"] == "loan_late"
    ]
    assert late and late[0]["title"] == "João Silva está com 5 parcelas atrasadas"
    assert "R$ 500,00 em aberto" in late[0]["text"] and "desde 10/02" in late[0]["text"]


def test_backup_and_reset_include_loans(user: TestClient) -> None:  # noqa: F811
    _create(user)
    backup = user.get("/api/export/backup").json()
    assert len(backup["friend_loans"]) == 1
    assert len(backup["friend_loans"][0]["installments"]) == 12


def test_loans_need_login(client: TestClient) -> None:
    assert client.get("/api/friend-loans").status_code == 401
    assert client.post("/api/friend-loans/simulate", json=BASE).status_code == 401
