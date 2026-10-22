"""Índices das chaves estrangeiras que ainda não tinham (v1.4.4).

Sem índice, apagar uma categoria, conta, cartão ou despesa obriga o banco a varrer as tabelas
que apontam para ela, e as telas que filtram por esses campos ficam mais lentas conforme os
dados crescem. Ficam aqui, num lugar só, para a migração 0027 e o `alembic check` baterem.
"""

from sqlalchemy import Index

from app.models.budget import (
    CategoryRule,
    Challenge,
    CreditCard,
    Expense,
    MoneyAccount,
    PlannedExpense,
    RecurringItem,
    Transfer,
)
from app.models.debts import Loan
from app.models.support import Announcement, AnnouncementReply, SupportMessage

FOREIGN_KEY_INDEXES = [
    Index("ix_money_accounts_benefit_category_id", MoneyAccount.benefit_category_id),
    Index("ix_money_accounts_recurring_id", MoneyAccount.recurring_id),
    Index("ix_recurring_items_category_id", RecurringItem.category_id),
    Index("ix_recurring_items_account_id", RecurringItem.account_id),
    Index("ix_announcements_author_id", Announcement.author_id),
    Index("ix_credit_cards_account_id", CreditCard.account_id),
    Index("ix_transfers_from_account_id", Transfer.from_account_id),
    Index("ix_transfers_to_account_id", Transfer.to_account_id),
    Index("ix_announcement_replies_author_id", AnnouncementReply.author_id),
    Index("ix_category_rules_category_id", CategoryRule.category_id),
    Index("ix_challenges_category_id", Challenge.category_id),
    Index("ix_loans_account_id", Loan.account_id),
    Index("ix_loans_category_id", Loan.category_id),
    Index("ix_expenses_category_id", Expense.category_id),
    Index("ix_expenses_debit_card_id", Expense.debit_card_id),
    Index("ix_support_messages_author_id", SupportMessage.author_id),
    Index("ix_planned_expenses_category_id", PlannedExpense.category_id),
    Index("ix_planned_expenses_expense_id", PlannedExpense.expense_id),
]
