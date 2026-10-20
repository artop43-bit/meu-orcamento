"""v0.6: cartões e faturas, regras, ações em lote, saldo dia a dia, assinaturas e sugestões."""

import uuid

from fastapi import APIRouter, status

from app.api.budget import _changes
from app.api.deps import CurrentUser, DbSession
from app.core.months import current_month, parse_month
from app.schemas.budget import (
    BulkIn,
    CardIn,
    CardOut,
    CardPatch,
    CardSummary,
    DailyOut,
    ExpenseOut,
    InvoiceOut,
    PayInvoiceIn,
    PromoteIn,
    RecurringOut,
    RuleIn,
    RuleOut,
    SubscriptionsOut,
)
from app.services import budget, cards, daily, rules, subscriptions

router = APIRouter(tags=["conforto (v0.6)"])


# ---------------------------------------------------------------- cartões


@router.get("/cards")
def list_cards(user: CurrentUser, db: DbSession) -> list[CardSummary]:
    """Cartões com limite usado, disponível, melhor dia de compra e faturas atual/fechada."""
    return [
        CardSummary.model_validate({**s, "card": CardOut.model_validate(s["card"])})
        for s in cards.summary(db, user)
    ]


@router.post("/cards", status_code=status.HTTP_201_CREATED)
def create_card(body: CardIn, user: CurrentUser, db: DbSession) -> CardOut:
    return CardOut.model_validate(cards.create_card(db, user, body.model_dump()))


@router.patch("/cards/{card_id}")
def update_card(card_id: uuid.UUID, body: CardPatch, user: CurrentUser, db: DbSession) -> CardOut:
    changes = _changes(body, nullable={"limit_amount", "color", "account_id"})
    return CardOut.model_validate(cards.update_card(db, user, card_id, changes))


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    cards.delete_card(db, user, card_id)


@router.get("/cards/{card_id}/invoices")
def list_invoices(card_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[InvoiceOut]:
    return [InvoiceOut.model_validate(i) for i in cards.invoices(db, user, card_id)]


@router.get("/cards/{card_id}/invoices/{month}")
def invoice_items(
    card_id: uuid.UUID, month: str, user: CurrentUser, db: DbSession
) -> list[ExpenseOut]:
    items = cards.invoice_items(db, user, card_id, parse_month(month))
    return [ExpenseOut.model_validate(e) for e in items]


@router.post("/cards/{card_id}/invoices/{month}/pay")
def pay_invoice(
    card_id: uuid.UUID, month: str, body: PayInvoiceIn, user: CurrentUser, db: DbSession
) -> dict[str, int]:
    """Pagar a fatura marca as compras dela como pagas (não cria outra conta)."""
    return {"updated": cards.pay_invoice(db, user, card_id, parse_month(month), body.paid)}


# ---------------------------------------------------------------- lote e regras


@router.post("/expenses/bulk")
def bulk(body: BulkIn, user: CurrentUser, db: DbSession) -> dict[str, int]:
    count = budget.bulk_expenses(db, user, body.ids, body.action, body.category_id)
    return {"count": count}


@router.get("/rules")
def list_rules(user: CurrentUser, db: DbSession) -> list[RuleOut]:
    return [RuleOut.model_validate(r) for r in rules.list_rules(db, user)]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: CurrentUser, db: DbSession) -> RuleOut:
    return RuleOut.model_validate(rules.create_rule(db, user, body.pattern, body.category_id))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    rules.delete_rule(db, user, rule_id)


# ---------------------------------------------------------------- planejamento


@router.get("/daily")
def daily_forecast(user: CurrentUser, db: DbSession, month: str | None = None) -> DailyOut:
    """Saldo dia a dia do mês e o valor disponível por dia até o fim do mês."""
    target = parse_month(month) if month else current_month(user.month_start_day)
    return DailyOut.model_validate(daily.forecast(db, user, target))


@router.get("/subscriptions")
def list_subscriptions(user: CurrentUser, db: DbSession) -> SubscriptionsOut:
    return SubscriptionsOut.model_validate(subscriptions.overview(db, user))


@router.post("/subscriptions/promote", status_code=status.HTTP_201_CREATED)
def promote(body: PromoteIn, user: CurrentUser, db: DbSession) -> RecurringOut:
    return RecurringOut.model_validate(subscriptions.promote(db, user, body.model_dump()))
