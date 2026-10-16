"""Conta de demonstração para testar o app (Codespaces, local).

Por padrão a conta nasce vazia (só as categorias padrão), para testar como um usuário novo.
Com `with_data=True` ela vem preenchida com 6 meses de exemplo.

Nunca roda em produção. A senha é aleatória a cada execução e só é mostrada no terminal
(e gravada num arquivo local fora do Git, se pedido).
"""

import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.months import add_months, current_month, format_month, with_day
from app.db.types import utcnow
from app.models import Category, Expense, Goal, Income, Investment, User
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


class DemoNotAllowed(RuntimeError):
    pass


def _category(db: Session, user: User, name: str) -> Category:
    category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name))
    assert category is not None, name
    return category


def seed_demo(
    db: Session, email: str = DEMO_EMAIL, *, with_data: bool = False, reset: bool = False
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
    start = format_month(first)

    # Fixas (lançadas automaticamente em cada mês aberto).
    for data in (
        {"kind": "income", "description": "Salário", "amount": Decimal("4500.00")},
        {"kind": "income", "description": "Freelas", "amount": Decimal("600.00")},
        {
            "kind": "expense",
            "description": "Aluguel",
            "amount": Decimal("1400.00"),
            "category_id": moradia.id,
            "due_day": 10,
        },
        {
            "kind": "expense",
            "description": "Internet",
            "amount": Decimal("99.90"),
            "category_id": servicos.id,
            "due_day": 15,
        },
        {
            "kind": "expense",
            "description": "Faculdade",
            "amount": Decimal("563.00"),
            "category_id": educacao.id,
            "due_day": 5,
        },
        {
            "kind": "expense",
            "description": "Academia",
            "amount": Decimal("89.90"),
            "category_id": lazer.id,
            "due_day": 20,
        },
    ):
        budget.create_recurring(db, user, {**data, "start_month": start, "end_month": None})

    # Abre do mais antigo até o próximo mês (lança as fixas) e adiciona os gastos variáveis.
    for offset in range(7):
        month = add_months(first, offset)
        budget.ensure_month(db, user, month)
        if offset < len(VARIABLE):
            market, transport, fun = VARIABLE[offset]
            for description, amount, category, day in (
                ("Mercado", market, alimentacao, 8),
                ("Combustível e Uber", transport, transporte, 18),
                ("Restaurantes e cinema", fun, lazer, 24),
            ):
                db.add(
                    Expense(
                        user_id=user.id,
                        month=month,
                        description=description,
                        amount=Decimal(amount),
                        category_id=category.id,
                        due_date=with_day(month, day),
                    )
                )

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
                invested_amount=Decimal("2000.00"),
                current_value=Decimal("1874.20"),
            ),
        ]
    )
