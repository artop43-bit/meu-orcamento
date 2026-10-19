"""Conta de demonstração para testar o app (Codespaces, local).

Por padrão a conta vem preenchida com 6 meses de exemplo (fixas, parcelas, um mês no
vermelho, limites, metas, investimentos e uma análise fixada), para demonstrar o app.
Com `with_data=False` ela nasce vazia, como um usuário novo (usado no QA automático).

Nunca roda em produção. A senha é aleatória a cada execução e só é mostrada no terminal
(e gravada num arquivo local fora do Git, se pedido).
"""

import json
import secrets
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.months import add_months, current_month, format_month, with_day
from app.db.types import utcnow
from app.models import (
    Category,
    CategoryRule,
    CreditCard,
    Expense,
    Goal,
    Income,
    Investment,
    MoneyAccount,
    PlannedExpense,
    SavedAnalysis,
    Transfer,
    User,
    WatchItem,
)
from app.services import budget

DEMO_EMAIL = "admin@example.com"

# Gastos variáveis por mês (do mais antigo para o atual): mercado, transporte, lazer.
VARIABLE = [
    ("820.40", "245.00", "310.00"),
    ("765.90", "198.50", "150.00"),
    ("901.15", "260.00", "420.00"),
    ("845.00", "230.00", "275.50"),
    ("790.30", "212.80", "190.00"),
    ("610.00", "140.00", "95.00"),  # mês atual, ainda em andamento
]
PHARMACY = ["42.90", "118.40", "36.00", "64.70", "29.90", "51.20"]
# Renda variável (freelance) de cada mês: a previsão usa a média.
FREELAS = ["450.00", "820.00", "300.00", "950.00", "600.00", "380.00", "600.00"]


class DemoNotAllowed(RuntimeError):
    pass


def _category(db: Session, user: User, name: str) -> Category:
    category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name))
    assert category is not None, name
    return category


def seed_demo(
    db: Session, email: str = DEMO_EMAIL, *, with_data: bool = True, reset: bool = False
) -> tuple[str, bool]:
    """Cria (ou redefine a senha de) a conta de demonstração. Retorna (senha, criada_agora).

    `reset` apaga a conta existente e todos os dados dela antes de criar de novo.
    """
    if get_settings().is_production:
        raise DemoNotAllowed("A conta de demonstração não pode ser criada em produção.")

    password = secrets.token_urlsafe(12)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and reset:
        db.delete(user)  # as demais tabelas apagam junto (ON DELETE CASCADE)
        db.commit()
        user = None
    if user is not None:
        user.password_hash = security.hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        return password, False

    now = utcnow()
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        email_verified_at=now,
        terms_accepted_at=now,
        terms_version=get_settings().terms_version,
    )
    db.add(user)
    db.flush()
    budget.create_default_categories(db, user)
    db.flush()
    if with_data:
        _fill(db, user)
    db.commit()
    return password, True


def _fill(db: Session, user: User) -> None:
    this_month = current_month()
    first = add_months(this_month, -5)
    moradia = _category(db, user, "Moradia")
    alimentacao = _category(db, user, "Alimentação")
    transporte = _category(db, user, "Transporte")
    servicos = _category(db, user, "Serviços")
    lazer = _category(db, user, "Lazer")
    educacao = _category(db, user, "Educação")
    saude = _category(db, user, "Saúde")
    start = format_month(first)

    # Fixas (lançadas automaticamente em cada mês aberto).
    for data in (
        {
            "kind": "income",
            "description": "Salário",
            "amount": Decimal("4500.00"),
            "income_type": "fixed",
            "due_day": 5,
        },
        {
            "kind": "income",
            "description": "Freelance",
            "amount": Decimal("600.00"),
            "income_type": "variable",
            "notes": "Design de logos e posts",
        },
        {
            "kind": "expense",
            "description": "Aluguel",
            "amount": Decimal("1400.00"),
            "category_id": moradia.id,
            "due_day": 10,
            "payment_method": "boleto",
        },
        {
            "kind": "expense",
            "description": "Internet",
            "amount": Decimal("99.90"),
            "category_id": servicos.id,
            "due_day": 15,
            "payment_method": "credit",
        },
        {
            "kind": "expense",
            "description": "Faculdade",
            "amount": Decimal("563.00"),
            "category_id": educacao.id,
            "due_day": 5,
            "payment_method": "pix",
        },
        {
            "kind": "expense",
            "description": "Academia",
            "amount": Decimal("89.90"),
            "category_id": lazer.id,
            "due_day": 20,
            "payment_method": "credit",
        },
        {
            # Conta que não é mensal: seguro do carro a cada 6 meses.
            "kind": "expense",
            "description": "Seguro do carro",
            "amount": Decimal("780.00"),
            "category_id": transporte.id,
            "due_day": 25,
            "interval_months": 6,
            "payment_method": "boleto",
        },
    ):
        budget.create_recurring(db, user, {**data, "start_month": start, "end_month": None})

    # Abre do mais antigo até o próximo mês (lança as fixas) e adiciona os gastos variáveis.
    for offset in range(7):
        month = add_months(first, offset)
        budget.ensure_month(db, user, month)
        if offset < len(VARIABLE):
            market, transport, fun = VARIABLE[offset]
            extras = [("Farmácia", PHARMACY[offset], saude, 14)]
            if offset == 1:
                # Um mês com resultado negativo: viagem no feriado (os Insights reagem a isso).
                extras.append(("Viagem do feriado", "1950.00", lazer, 21))
            methods = {"Mercado": "debit", "Combustível e Uber": "pix", "Farmácia": "credit"}
            for description, amount, category, day in (
                ("Mercado", market, alimentacao, 8),
                ("Combustível e Uber", transport, transporte, 18),
                ("Restaurantes e cinema", fun, lazer, 24),
                *extras,
            ):
                db.add(
                    Expense(
                        user_id=user.id,
                        month=month,
                        description=description,
                        amount=Decimal(amount),
                        category_id=category.id,
                        due_date=with_day(month, day),
                        payment_method=methods.get(description, "credit"),
                    )
                )
        # A renda variável muda de mês para mês.
        db.flush()
        for income in db.scalars(
            select(Income).where(
                Income.user_id == user.id, Income.month == month, Income.description == "Freelance"
            )
        ):
            income.amount = Decimal(FREELAS[offset])

    # Compra parcelada em 10x, começando há 3 meses.
    budget.create_expense(
        db,
        user,
        add_months(this_month, -3),
        {
            "description": "Notebook",
            "amount": Decimal("350.00"),
            "category_id": educacao.id,
            "due_date": with_day(add_months(this_month, -3), 12),
            "installments": 10,
            "payment_method": "credit",
        },
    )
    db.flush()

    # Meses passados: tudo pago. Mês atual: só o que já venceu.
    today = date.today()
    for expense in db.scalars(select(Expense).where(Expense.user_id == user.id)):
        if expense.month < this_month or (
            expense.due_date is not None and expense.due_date < today
        ):
            expense.paid = True
            expense.paid_at = utcnow()

    # Um bônus pontual para o histórico ficar mais interessante.
    db.add(
        Income(
            user_id=user.id,
            month=add_months(this_month, -2),
            description="13º / bônus",
            amount=Decimal("2200.00"),
        )
    )

    db.add_all(
        [
            Goal(
                user_id=user.id,
                name="Reserva de emergência",
                target_amount=Decimal("18000.00"),
                current_amount=Decimal("6420.00"),
            ),
            Goal(
                user_id=user.id,
                name="Viagem de férias",
                target_amount=Decimal("5000.00"),
                current_amount=Decimal("1200.00"),
                target_date=with_day(add_months(this_month, 8), 1),
            ),
            Investment(
                user_id=user.id,
                name="Tesouro Selic 2029",
                kind="tesouro",
                institution="Banco X",
                invested_amount=Decimal("6000.00"),
                current_value=Decimal("6420.00"),
                is_emergency_reserve=True,
            ),
            Investment(
                user_id=user.id,
                name="CDB 110% CDI",
                kind="renda_fixa",
                institution="Banco Y",
                invested_amount=Decimal("3000.00"),
                current_value=Decimal("3185.70"),
            ),
            Investment(
                user_id=user.id,
                name="ETF BOVA11",
                kind="acoes",
                institution="Corretora Z",
                ticker="BOVA11",
                quantity=Decimal("15"),
                invested_amount=Decimal("2000.00"),
                current_value=Decimal("1874.20"),
            ),
            WatchItem(user_id=user.id, symbol="PETR4"),
            WatchItem(user_id=user.id, symbol="BTC"),
        ]
    )

    # Cartão de crédito: compras do mês e um celular parcelado, cada um na fatura certa.
    card = CreditCard(
        user_id=user.id,
        name="Cartão Roxo",
        limit_amount=Decimal("4000.00"),
        closing_day=3,
        due_day=10,
        color="#8a05be",
    )
    db.add(card)
    db.flush()
    for description, amount, days_ago, category in (
        ("iFood", "58.90", 2, alimentacao),
        ("Uber", "23.40", 5, transporte),
        ("Farmácia Pague Menos", "37.80", 9, saude),
    ):
        budget.create_expense(
            db,
            user,
            this_month,
            {
                "description": description,
                "amount": Decimal(amount),
                "category_id": category.id,
                "card_id": card.id,
                "purchase_date": today - timedelta(days=days_ago),
            },
        )
    budget.create_expense(
        db,
        user,
        this_month,
        {
            "description": "Fone Bluetooth",
            "amount": Decimal("420.00"),
            "category_id": lazer.id,
            "card_id": card.id,
            "purchase_date": today - timedelta(days=20),
            "installments": 3,
            "amount_mode": "total",
        },
    )
    # Faturas que já venceram estão pagas.
    for expense in db.scalars(select(Expense).where(Expense.card_id == card.id)):
        if expense.due_date is not None and expense.due_date < today:
            expense.paid = True
            expense.paid_at = utcnow()
    db.add(CategoryRule(user_id=user.id, pattern="ifood", category_id=alimentacao.id))

    # Conta corrente com saldo inicial; receitas, despesas e a fatura do cartão saem dela.
    account = MoneyAccount(
        user_id=user.id, name="Conta corrente", kind="checking", initial_balance=Decimal("1850.00")
    )
    savings = MoneyAccount(
        user_id=user.id, name="Poupança", kind="savings", initial_balance=Decimal("3200.00")
    )
    db.add_all([account, savings])
    db.flush()
    card.account_id = account.id
    for income in db.scalars(select(Income).where(Income.user_id == user.id)):
        income.account_id = account.id
    for expense in db.scalars(
        select(Expense).where(Expense.user_id == user.id, Expense.card_id.is_(None))
    ):
        expense.account_id = account.id
    # Cartão de débito: a compra entra paga e sai da conta corrente (sem fatura e sem limite).
    debit = CreditCard(
        user_id=user.id, name="Débito Conta corrente", kind="debit", account_id=account.id
    )
    db.add(debit)
    db.flush()
    budget.create_expense(
        db,
        user,
        this_month,
        {
            "description": "Padaria",
            "amount": Decimal("18.50"),
            "category_id": alimentacao.id,
            "debit_card_id": debit.id,
            "purchase_date": today,
        },
    )
    db.add(
        Transfer(
            user_id=user.id,
            from_account_id=account.id,
            to_account_id=savings.id,
            amount=Decimal("300.00"),
            date=today.replace(day=6) if today.day >= 6 else today,
            notes="Reserva mensal",
        )
    )

    # Gastos planejados (Calendário): entram na previsão até virarem conta.
    db.add_all(
        [
            PlannedExpense(
                user_id=user.id,
                date=today + timedelta(days=4),
                description="Presente de aniversário da mãe",
                amount=Decimal("250.00"),
                category_id=lazer.id,
            ),
            PlannedExpense(
                user_id=user.id,
                date=with_day(add_months(this_month, 2), 15),
                description="IPVA (cota única)",
                amount=Decimal("1380.00"),
                category_id=transporte.id,
                notes="Pagar à vista tem desconto",
            ),
        ]
    )

    # Limites por categoria (o Lazer fica perto do limite no mês atual: gera alerta).
    lazer.monthly_limit = Decimal("220.00")
    alimentacao.monthly_limit = Decimal("900.00")

    # Uma análise montada e fixada no Resumo da Análise financeira.
    db.add(
        SavedAnalysis(
            user_id=user.id,
            name="Gastos por categoria",
            config=json.dumps(
                {
                    "metric": "expenses",
                    "period": "6m",
                    "start": None,
                    "end": None,
                    "group": "month_category",
                    "categories": [],
                    "compare": "none",
                    "chart": "stacked",
                }
            ),
            pinned=True,
        )
    )
