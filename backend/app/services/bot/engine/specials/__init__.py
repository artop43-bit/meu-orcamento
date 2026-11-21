"""Regras especializadas do motor determinístico de dúvidas, divididas por domínio."""

from app.services.bot.engine.specials.budget_overview import (
    can_spend_summary,
    logged_summary,
    planned_summary,
    projects_summary,
    recurring_summary,
    review_pending_summary,
    salary_summary,
)
from app.services.bot.engine.specials.cards_and_due import (
    cards_summary,
    due_summary,
    installments_summary,
    invoices_summary,
)
from app.services.bot.engine.specials.navigation import navigate
from app.services.bot.engine.specials.wealth_and_tax import (
    accounts_summary,
    challenges_summary,
    friend_loans_summary,
    goals_summary,
    investments_summary,
    loans_summary,
    mei_summary,
    net_worth_summary,
    tax_deductible_summary,
    transfers_summary,
)

__all__ = [
    "accounts_summary",
    "can_spend_summary",
    "cards_summary",
    "challenges_summary",
    "due_summary",
    "friend_loans_summary",
    "goals_summary",
    "installments_summary",
    "investments_summary",
    "invoices_summary",
    "loans_summary",
    "logged_summary",
    "mei_summary",
    "navigate",
    "net_worth_summary",
    "planned_summary",
    "projects_summary",
    "recurring_summary",
    "review_pending_summary",
    "salary_summary",
    "tax_deductible_summary",
    "transfers_summary",
]
