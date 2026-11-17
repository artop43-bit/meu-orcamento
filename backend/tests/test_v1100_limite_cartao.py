"""v1.10: compra no cartão de crédito nunca entra paga e sempre ocupa o limite.

O formulário marcava "Já paga" sozinho para compras do dia; no crédito isso deixava a compra
fora do limite usado e a fatura como paga.
"""

from fastapi.testclient import TestClient

from tests.test_data import user  # noqa: F401  (fixture)
from tests.test_v06 import add_expense, new_card


def test_credit_purchase_sent_as_paid_still_uses_the_limit(user: TestClient) -> None:  # noqa: F811
    card = new_card(user, name="Cartão pai", limit_amount="1000.00", closing_day=30, due_day=10)
    created = add_expense(
        user,
        description="Mercado",
        amount="150.30",
        card_id=card["id"],
        purchase_date="2030-01-15",
        paid=True,  # como o formulário antigo mandava
    )
    assert all(item["paid"] is False for item in created)
    [summary] = user.get("/api/cards").json()
    assert summary["used"] == "150.30" and summary["available"] == "849.70"
    # Pagar a fatura em Cartões continua liberando o limite.
    month = created[0]["month"][:7]
    user.post(f"/api/cards/{card['id']}/invoices/{month}/pay", json={"paid": True})
    assert user.get("/api/cards").json()[0]["used"] == "0.00"


def test_installments_on_credit_all_stay_open(user: TestClient) -> None:  # noqa: F811
    card = new_card(user, limit_amount="1000.00")
    created = add_expense(
        user,
        amount="100.00",  # valor de cada parcela
        card_id=card["id"],
        purchase_date="2030-01-05",
        installments=3,
        paid=True,
    )
    assert len(created) == 3 and all(item["paid"] is False for item in created)
    assert user.get("/api/cards").json()[0]["used"] == "300.00"


def test_data_fix_reopens_purchases_marked_paid_at_creation(user: TestClient, db) -> None:  # noqa: ANN001, F811
    """A migração 0033 reabre o que foi marcado pago no próprio lançamento; fatura paga
    depois (em Cartões) continua paga."""
    import importlib.util
    from datetime import timedelta
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import select

    from app.models import Expense

    card = new_card(user, limit_amount="1000.00")
    wrong = add_expense(user, amount="150.30", card_id=card["id"], purchase_date="2030-01-15")
    later = add_expense(user, amount="40.00", card_id=card["id"], purchase_date="2030-01-16")
    for item, delay in ((wrong[0], timedelta(seconds=1)), (later[0], timedelta(days=3))):
        expense = db.get(Expense, __import__("uuid").UUID(item["id"]))
        expense.paid = True
        expense.paid_at = expense.created_at + delay
    db.commit()
    path = Path(__file__).parents[1] / "alembic/versions/20261117_0033_v1100_limite_cartao.py"
    spec = importlib.util.spec_from_file_location("m0033", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    with db.bind.begin() as conn:
        ctx = MigrationContext.configure(conn)
        module.op = Operations(ctx)
        module.upgrade()
    db.expire_all()
    paid = {str(e.id): e.paid for e in db.scalars(select(Expense))}
    assert paid[wrong[0]["id"]] is False
    assert paid[later[0]["id"]] is True
