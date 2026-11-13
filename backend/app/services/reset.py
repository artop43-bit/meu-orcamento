"""Começar do zero (v0.9): apaga as áreas escolhidas dos dados da conta, de uma vez só.

A conta, o login, o perfil, as preferências e as solicitações à administração nunca são
apagados. As dependências entre as áreas são resolvidas aqui, explicitamente (sem depender do
ON DELETE do banco): o que fica nunca aponta para algo que sumiu.
"""

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.models import (
    BudgetMonth,
    Category,
    CategoryRule,
    CreditCard,
    Expense,
    Goal,
    ImportBatch,
    ImportMapping,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    NetWorthSnapshot,
    OtherDebt,
    PersonalLoan,
    PlannedExpense,
    RecurringItem,
    SavedAnalysis,
    SplitShare,
    StoredFile,
    Transfer,
    User,
    WatchItem,
)
from app.services.auth import Mailer

CONFIRMATION = "COMEÇAR DO ZERO"

AREAS: dict[str, str] = {
    "entries": "Lançamentos",
    "recurring": "Recorrências",
    "accounts": "Contas",
    "cards": "Cartões e faturas",
    "goals": "Metas",
    "investments": "Investimentos",
    "categories": "Categorias e regras",
    "analyses": "Análises salvas",
    "debts": "Financiamentos e dívidas",
}


def _count(db: Session, model: Any, user: User) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id)) or 0


def preview(db: Session, user: User) -> dict[str, int]:
    """Quantos itens cada área tem hoje."""
    from app.services.budget import DEFAULT_CATEGORIES

    defaults = [name for name, _, _ in DEFAULT_CATEGORIES]
    custom = (
        db.scalar(
            select(func.count()).where(Category.user_id == user.id, Category.name.not_in(defaults))
        )
        or 0
    )
    return {
        "entries": _count(db, Expense, user)
        + _count(db, Income, user)
        + _count(db, PlannedExpense, user)
        + _count(db, Transfer, user),
        "recurring": _count(db, RecurringItem, user),
        "accounts": _count(db, MoneyAccount, user),
        "cards": _count(db, CreditCard, user),
        "goals": _count(db, Goal, user),
        "investments": _count(db, Investment, user) + _count(db, WatchItem, user),
        "categories": custom + _count(db, CategoryRule, user),
        "analyses": _count(db, SavedAnalysis, user),
        "debts": _count(db, Loan, user)
        + _count(db, OtherDebt, user)
        + _count(db, PersonalLoan, user),
    }


def _reset_categories(db: Session, user: User) -> None:
    """Volta às categorias padrão: as criadas pela pessoa somem e o que as usava vira "Outros"."""
    from app.services.budget import DEFAULT_CATEGORIES

    existing = {c.name: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    for name, essential, color in DEFAULT_CATEGORIES:
        category = existing.pop(name, None)
        if category is None:
            db.add(Category(user_id=user.id, name=name, is_essential=essential, color=color))
        else:
            category.is_essential = essential
            category.color = color
            category.monthly_limit = None
    db.flush()
    other = db.scalar(
        select(Category.id).where(Category.user_id == user.id, Category.name == "Outros")
    )
    removed = [c.id for c in existing.values()]
    if removed:
        for model in (Expense, RecurringItem, PlannedExpense):
            db.execute(
                update(model)
                .where(model.user_id == user.id, model.category_id.in_(removed))
                .values(category_id=other)
            )
    db.execute(delete(CategoryRule).where(CategoryRule.user_id == user.id))
    if removed:
        db.execute(delete(Category).where(Category.id.in_(removed)))


def reset(
    db: Session,
    user: User,
    areas: list[str],
    password: str,
    confirmation: str,
    code: str | None,
    mail: Mailer,
) -> dict[str, int]:
    from app.services import auth, notify

    chosen = [a for a in AREAS if a in set(areas)]
    if not chosen:
        raise AppError(400, "nothing_selected", "Escolha pelo menos uma área para zerar.")
    if confirmation.strip().upper() != CONFIRMATION:
        raise AppError(400, "wrong_confirmation", f"Digite {CONFIRMATION} para confirmar.")
    if not security.verify_password(user.password_hash, password):
        raise AppError(400, "wrong_password", "Senha incorreta.")
    if user.totp_enabled and (not code or not auth._verify_second_factor(db, user, code)):
        raise AppError(400, "invalid_code", "Informe um código válido do aplicativo autenticador.")

    before = preview(db, user)
    uid = user.id
    try:
        if "entries" in chosen:
            db.execute(delete(PlannedExpense).where(PlannedExpense.user_id == uid))
            db.execute(delete(SplitShare).where(SplitShare.user_id == uid))
            db.execute(delete(Transfer).where(Transfer.user_id == uid))
            expense_ids = select(Expense.id).where(Expense.user_id == uid)
            db.execute(delete(StoredFile).where(StoredFile.expense_id.in_(expense_ids)))
            db.execute(delete(Expense).where(Expense.user_id == uid))
            db.execute(delete(Income).where(Income.user_id == uid))
            db.execute(delete(ImportBatch).where(ImportBatch.user_id == uid))
            db.execute(delete(ImportMapping).where(ImportMapping.user_id == uid))
            # Meses "abertos" de novo: as recorrências que ficarem voltam a ser lançadas.
            db.execute(delete(BudgetMonth).where(BudgetMonth.user_id == uid))
        if "recurring" in chosen:
            # Lançamentos já feitos ficam; só deixam de nascer nos próximos meses.
            for model in (Expense, Income):
                db.execute(update(model).where(model.user_id == uid).values(recurring_id=None))
            db.execute(delete(RecurringItem).where(RecurringItem.user_id == uid))
        if "cards" in chosen:
            card_ids = select(CreditCard.id).where(CreditCard.user_id == uid)
            db.execute(
                update(Expense)
                .where(Expense.user_id == uid, Expense.card_id.in_(card_ids))
                .values(card_id=None)
            )
            db.execute(
                update(Expense)
                .where(Expense.user_id == uid, Expense.debit_card_id.in_(card_ids))
                .values(debit_card_id=None)
            )
            db.execute(delete(CreditCard).where(CreditCard.user_id == uid))
        if "accounts" in chosen:
            for model in (Expense, Income):
                db.execute(update(model).where(model.user_id == uid).values(account_id=None))
            db.execute(update(CreditCard).where(CreditCard.user_id == uid).values(account_id=None))
            db.execute(delete(Transfer).where(Transfer.user_id == uid))
            db.execute(delete(MoneyAccount).where(MoneyAccount.user_id == uid))
        if "goals" in chosen:
            goal_ids = select(Goal.id).where(Goal.user_id == uid)
            db.execute(delete(StoredFile).where(StoredFile.goal_id.in_(goal_ids)))
            db.execute(delete(Goal).where(Goal.user_id == uid))
        if "investments" in chosen:
            db.execute(delete(Investment).where(Investment.user_id == uid))
            db.execute(delete(WatchItem).where(WatchItem.user_id == uid))
        if "categories" in chosen:
            _reset_categories(db, user)
        if "analyses" in chosen:
            db.execute(delete(SavedAnalysis).where(SavedAnalysis.user_id == uid))
            from app.services import ask_history

            ask_history.remove(db, user)  # conversas do Tire sua dúvida
        if "debts" in chosen:
            # Parcelas já pagas ficam no histórico (sem o vínculo); as a pagar somem com o contrato.
            db.execute(
                delete(Expense).where(
                    Expense.user_id == uid, Expense.loan_id.is_not(None), Expense.paid.is_(False)
                )
            )
            db.execute(update(Expense).where(Expense.user_id == uid).values(loan_id=None))
            db.execute(delete(Loan).where(Loan.user_id == uid))
            # v1.8: empréstimos a amigos (o que já foi recebido ou pago fica, sem o vínculo).
            from app.services import personal_loans

            for friend_loan in list(
                db.scalars(select(PersonalLoan).where(PersonalLoan.user_id == uid))
            ):
                personal_loans.remove(db, user, friend_loan.id, commit=False)
            db.execute(delete(OtherDebt).where(OtherDebt.user_id == uid))
            db.execute(delete(NetWorthSnapshot).where(NetWorthSnapshot.user_id == uid))
        elif "entries" in chosen:
            # Contratos que ficam: as parcelas a pagar voltam a ser lançadas.
            from app.services import loans

            for loan in loans.list_loans(db, user):
                loans._materialize(db, user, loan)
            from app.services import personal_loans

            for friend_loan in db.scalars(select(PersonalLoan).where(PersonalLoan.user_id == uid)):
                personal_loans.sync(db, user, friend_loan)
        if len(chosen) == len(AREAS):
            user.onboarded_at = None  # recomeço completo: a configuração inicial aparece de novo
        auth._record(db, user, "data_reset")
        db.commit()
    except Exception:
        db.rollback()
        raise

    removed = {a: before[a] for a in chosen}
    names = ", ".join(AREAS[a].lower() for a in chosen)
    info = auth.request_info()
    message = notify.Message(
        subject="Dados apagados da sua conta",
        heading="Dados apagados",
        intro=f"Como você pediu, estas áreas da sua conta voltaram ao padrão: {names}.",
        sections=[
            notify.Section(
                title="Detalhes",
                rows=[
                    ("Quando", notify.local_now().strftime("%d/%m/%Y às %H:%M"), ""),
                    ("Aparelho", notify.device_label(info.user_agent), ""),
                ],
                note="Se não foi você, troque sua senha agora e ative a verificação em "
                "duas etapas.",
            )
        ],
        button=("Abrir o Meu Orçamento", notify._link("/orcamento")),
    )
    text, body_html, headers = notify.render(message, user)
    mail(user.email, message.subject, text, body_html, headers)
    db.commit()  # registro do e-mail no painel
    return removed
