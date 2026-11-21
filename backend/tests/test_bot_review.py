"""Regressões da revisão do bot: valores das telas, contexto e histórico grande."""

import time
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import (
    CreditCard,
    Expense,
    Goal,
    Income,
    Loan,
    LoanInstallment,
    PersonalLoan,
    PlannedExpense,
    SplitShare,
    User,
)
from app.services import ask, cards, daily, goals, lexicon, loans, splits, suggest
from app.services.bot.contracts import QueryPlan
from app.services.bot.engine import locator, specials
from app.services.bot.lexicon import core
from app.services.bot.nlu.corrector import fix_typos

TODAY = date(2030, 3, 20)
MONTH = date(2030, 3, 1)


@pytest.fixture
def owner(db: Session) -> User:
    user = User(email="review-bot@example.com", password_hash="test", month_start_day=1)
    db.add(user)
    db.flush()
    return user


def test_daily_answer_uses_forecast_including_planned(db: Session, owner: User) -> None:
    db.add(
        Income(user_id=owner.id, month=MONTH, description="Salário", amount=Decimal(1000), day=1)
    )
    db.add(Expense(user_id=owner.id, month=MONTH, description="Conta", amount=Decimal(100)))
    db.add(
        PlannedExpense(
            user_id=owner.id, date=date(2030, 3, 25), description="Viagem", amount=Decimal(200)
        )
    )
    db.flush()
    expected = daily.forecast(db, owner, MONTH, TODAY)["can_spend"]
    out = ask.answer(db, owner, "Quanto posso gastar hoje?", today=TODAY)
    from app.services.bot.text_utils import brl

    assert brl(expected["today"]) in out["answer"]
    assert brl(expected["rest_of_month"]) in out["answer"]
    assert expected["rest_of_month"] == Decimal(700)


def test_loan_balance_is_the_same_as_the_screen(db: Session, owner: User) -> None:
    loan = Loan(
        user_id=owner.id,
        kind="vehicle",
        name="Carro",
        principal=Decimal(36000),
        rate=Decimal("1.2"),
        rate_period="monthly",
        system="price",
        installments=36,
        first_due=date(2025, 1, 10),
        paid_before=12,
    )
    db.add(loan)
    db.flush()
    expected = loans.summary(db, loan)["balance"]
    out = specials.loans_summary(db, owner)
    from app.services.bot.text_utils import brl

    assert out["items"][0]["value"] == brl(expected)
    assert expected != Decimal(24000)  # não é principal / parcelas restantes


def test_invoice_never_combines_other_months(db: Session, owner: User) -> None:
    card = CreditCard(user_id=owner.id, name="Cartão", kind="credit", closing_day=10, due_day=17)
    db.add(card)
    db.flush()
    for month, amount in ((date(2030, 3, 1), 123), (date(2030, 5, 1), 456)):
        db.add(
            Expense(
                user_id=owner.id,
                month=month,
                card_id=card.id,
                payment_method="credit",
                description="Compra",
                amount=Decimal(amount),
                paid=False,
            )
        )
    db.flush()
    expected = cards.invoice(db, card, MONTH, TODAY)
    out = specials.invoices_summary(db, owner, QueryPlan(intent="invoices"), TODAY)
    assert "R$ 123,00" in out["answer"]
    assert expected["due_date"].strftime("%d/%m/%Y") in out["answer"]
    assert "579,00" not in out["answer"]


def test_splits_and_proportional_interest_use_the_screen_services(db: Session, owner: User) -> None:
    loan = PersonalLoan(
        user_id=owner.id,
        person="Ana",
        direction="owes_me",
        principal=Decimal(500),
        mode="total",
        rate=Decimal(10),
        frequency="month",
        count=1,
        first_due=TODAY,
    )
    db.add(loan)
    db.flush()
    db.add(
        LoanInstallment(
            loan_id=loan.id,
            number=1,
            due_date=TODAY,
            amount=Decimal(550),
            interest=Decimal(50),
            principal_part=Decimal(500),
            received_amount=Decimal(275),
            received_at=TODAY,
        )
    )
    db.add(
        SplitShare(
            user_id=owner.id,
            person="Ana",
            direction="i_owe",
            amount=Decimal(25),
            description="Jantar",
        )
    )
    db.flush()
    expected = splits.board(db, owner)
    from app.services.bot.text_utils import brl

    balances = specials.friend_loans_summary(db, owner, QueryPlan(intent="friend_loans"))
    assert brl(expected["owed_to_me"]) in balances["answer"]
    profits = specials.friend_loans_summary(
        db, owner, QueryPlan(intent="friend_loans", corrected_question="lucro de juros")
    )
    assert brl(expected["loans"]["profit_received"]) in profits["answer"]
    assert expected["loans"]["profit_received"] == Decimal(25)


def test_goal_projection_is_the_same_as_the_screen(db: Session, owner: User) -> None:
    goal = Goal(
        user_id=owner.id,
        name="Viagem",
        current_amount=Decimal(200),
        target_amount=Decimal(1200),
        monthly_plan=Decimal(100),
        target_date=date(2031, 3, 1),
        is_main=True,
    )
    db.add(goal)
    db.flush()
    expected = goals.projection(db, owner, goal, TODAY)
    out = specials.goals_summary(db, owner, TODAY)
    from app.services.bot.months import month_label
    from app.services.bot.text_utils import brl

    assert brl(expected["remaining"]) in out["items"][0]["detail"]
    assert month_label(expected["eta"]) in out["items"][0]["detail"]


def test_logged_uses_creation_in_brasilia_not_purchase_date(db: Session, owner: User) -> None:
    db.add_all(
        [
            Expense(
                user_id=owner.id,
                month=date(2029, 1, 1),
                description="Criado hoje",
                amount=Decimal(25),
                purchase_date=date(2029, 1, 10),
                created_at=datetime(2030, 3, 21, 2, 30, tzinfo=UTC),
            ),
            Expense(
                user_id=owner.id,
                month=MONTH,
                description="Comprado hoje",
                amount=Decimal(99),
                purchase_date=TODAY,
                created_at=datetime(2030, 3, 20, 2, 30, tzinfo=UTC),
            ),
        ]
    )
    db.flush()
    out = ask.answer(db, owner, "O que eu cadastrei hoje?", today=TODAY)
    assert out["intent"] == "logged"
    assert [item["label"] for item in out["items"]] == ["Criado hoje"]
    assert "R$ 25,00" in out["answer"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("text_terms", [1]),
        ("category_names", 5),
        ("card_names", {"x": 1}),
        ("account_names", [None]),
        ("project_names", "x"),
        ("payment_methods", [True]),
    ],
)
def test_browser_context_ignores_invalid_list_types(
    db: Session, owner: User, field: str, value: object
) -> None:
    context = {"intent": "sum", "domain": "expense", field: value}
    out = ask.answer(db, owner, "e em setembro?", today=TODAY, context=context)
    assert out["intent"] in {"sum", "empty"}


@pytest.mark.parametrize(
    "question",
    [
        "resumo do mês",
        "vou fechar o mês no azul?",
        "quanto eu devo pra alguém?",
        "e em setembro?",
        "Qual valor mais próximo disso?",
    ],
)
def test_unclear_financial_questions_are_not_out_of_scope(
    db: Session, owner: User, question: str
) -> None:
    out = ask.answer(db, owner, question, today=TODAY)
    assert out["intent"] == "fallback"
    assert "Não tenho certeza" in out["answer"]


def test_shared_vocabulary_and_second_are_preserved() -> None:
    assert core.INCOME_VERBS is lexicon.INCOME_VERBS
    assert core.PAYMENT_TERMS is lexicon.PAYMENTS
    assert core.keyword_category is suggest.keyword_category
    assert fix_typos("qual foi o segundo maior gasto") == "qual foi o segundo maior gasto"


@pytest.mark.parametrize("operation", ["70 + 19", "70 - 19", "70 * 19", "70 / 19", "70 x 19"])
def test_general_arithmetic_stays_out_of_scope(db: Session, owner: User, operation: str) -> None:
    out = ask.answer(db, owner, f"Quanto é {operation}?", today=TODAY)
    assert out["intent"] == "out_of_scope"
    assert "finalidade" in out["answer"].lower()


def test_financial_question_with_numbers_is_not_general_arithmetic(
    db: Session, owner: User
) -> None:
    out = ask.answer(db, owner, "Quanto gastei com compras acima de 70 reais?", today=TODAY)
    assert out["intent"] != "out_of_scope"


def test_locator_keeps_end_of_month_planned_item(db: Session, owner: User) -> None:
    db.add(
        PlannedExpense(
            user_id=owner.id,
            date=date(2030, 3, 31),
            description="Cirurgia especial",
            amount=Decimal(250),
        )
    )
    db.flush()
    out = ask.answer(db, owner, "Onde está a cirurgia especial em março de 2030?", today=TODAY)
    assert out["intent"] == "locate_record"
    assert any(item["label"] == "Cirurgia especial" for item in out["items"])


def test_locator_twenty_thousand_records(
    db: Session, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {
            "user_id": owner.id,
            "month": MONTH,
            "description": f"Despesa comum {i}",
            "amount": Decimal(10),
        }
        for i in range(20000)
    ]
    rows[1234]["description"] = "Antibiótico singular"
    rows[1234]["amount"] = Decimal(157)
    db.execute(insert(Expense), rows)
    db.flush()
    # Reproduz a estratégia anterior de materializar o histórico inteiro para o BM25.
    with monkeypatch.context() as patch:
        patch.setattr(
            locator,
            "_candidate_rows",
            lambda db, user, model, plan, tokens: list(
                db.scalars(select(model).where(model.user_id == user.id))
            ),
        )
        started = time.perf_counter()
        previous = ask.answer(
            db, owner, "Onde está o lançamento do antibiótico singular?", today=TODAY
        )
        previous_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    out = ask.answer(db, owner, "Onde está o lançamento do antibiótico singular?", today=TODAY)
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"LOCATOR_20K_BEFORE_MS={previous_ms:.2f} AFTER_MS={elapsed_ms:.2f}")
    assert out["items"][0] == previous["items"][0]
    assert out["intent"] == "locate_record"
    assert any(
        item["label"] == "Antibiótico singular" and item["value"] == "R$ 157,00"
        for item in out["items"]
    )
    # Correção é estável em CI; a medição é informada separadamente, sem teste de relógio frágil.
    assert len(out["items"]) <= 20
