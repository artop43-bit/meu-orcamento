"""Contratos internos e plano estruturado de consulta do motor composicional do bot."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class PeriodSpec:
    start: date
    end: date
    label: str
    explicit: bool = True
    day_start: date | None = None
    day_end: date | None = None
    all_time: bool = False

    @property
    def single(self) -> bool:
        return self.start == self.end and self.day_start is None and not self.all_time

    def dump(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "explicit": self.explicit,
            "day_start": self.day_start.isoformat() if self.day_start else None,
            "day_end": self.day_end.isoformat() if self.day_end else None,
            "all_time": self.all_time,
        }

    @staticmethod
    def load(data: Any) -> PeriodSpec | None:
        if not isinstance(data, dict):
            return None
        try:
            return PeriodSpec(
                start=date.fromisoformat(data["start"]),
                end=date.fromisoformat(data["end"]),
                label=str(data["label"])[:80],
                explicit=bool(data.get("explicit", True)),
                day_start=date.fromisoformat(data["day_start"]) if data.get("day_start") else None,
                day_end=date.fromisoformat(data["day_end"]) if data.get("day_end") else None,
                all_time=bool(data.get("all_time", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class AmountFilter:
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    target_amount: Decimal | None = None
    tolerance_pct: Decimal = Decimal("0.10")
    raw_expr: str | None = None

    def matches(self, value: Decimal) -> bool:
        if self.target_amount is not None:
            tol = max(Decimal("1.00"), self.target_amount * self.tolerance_pct)
            return abs(value - self.target_amount) <= tol
        if self.min_amount is not None and value < self.min_amount:
            return False
        if self.max_amount is not None and value > self.max_amount:
            return False
        return True

    def describe(self) -> str | None:
        if self.target_amount is not None:
            return f"valor próximo de R$ {self.target_amount:.2f}".replace(".", ",")
        if self.min_amount is not None and self.max_amount is not None:
            return f"entre R$ {self.min_amount:.2f} e R$ {self.max_amount:.2f}".replace(".", ",")
        if self.min_amount is not None:
            return f"acima de R$ {self.min_amount:.2f}".replace(".", ",")
        if self.max_amount is not None:
            return f"até R$ {self.max_amount:.2f}".replace(".", ",")
        return None


@dataclass
class QueryFilters:
    period: PeriodSpec | None = None
    period2: PeriodSpec | None = None
    category_ids: list[uuid.UUID] = field(default_factory=list)
    category_names: list[str] = field(default_factory=list)
    card_ids: list[uuid.UUID] = field(default_factory=list)
    card_names: list[str] = field(default_factory=list)
    account_ids: list[uuid.UUID] = field(default_factory=list)
    account_names: list[str] = field(default_factory=list)
    project_ids: list[uuid.UUID] = field(default_factory=list)
    project_names: list[str] = field(default_factory=list)
    payment_methods: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    amount: AmountFilter = field(default_factory=AmountFilter)
    paid: bool | None = None
    overdue: bool | None = None
    needs_review: bool | None = None
    is_installment: bool | None = None
    is_recurring: bool | None = None
    is_essential: bool | None = None
    deductible: str | None = None  # "saude"|"educacao"|"previdencia"|"pensao"|"any"
    mei: bool | None = None
    text_terms: list[str] = field(default_factory=list)
    unresolved_subject: str | None = None

    def has_data_filters(self) -> bool:
        return bool(
            self.category_ids
            or self.card_ids
            or self.account_ids
            or self.project_ids
            or self.payment_methods
            or self.people
            or self.text_terms
            or self.amount.target_amount is not None
            or self.amount.min_amount is not None
            or self.amount.max_amount is not None
            or self.paid is not None
            or self.overdue is not None
            or self.needs_review is not None
            or self.is_installment is not None
            or self.is_recurring is not None
            or self.is_essential is not None
            or self.deductible is not None
            or self.mei is not None
        )


@dataclass
class QueryPlan:
    intent: str
    domain: str = "expense"  # expense | income | balance | all | entity
    grouping: str | None = None
    order: str = "most"  # most | least
    limit: int = 5
    filters: QueryFilters = field(default_factory=QueryFilters)
    normalized_question: str = ""
    corrected_question: str = ""
    matched_rules: list[str] = field(default_factory=list)
    followup: bool = False

    def to_debug_dict(self) -> dict[str, Any]:
        f = self.filters
        return {
            "intent": self.intent,
            "domain": self.domain,
            "grouping": self.grouping,
            "order": self.order,
            "limit": self.limit,
            "followup": self.followup,
            "normalized_question": self.normalized_question,
            "corrected_question": self.corrected_question,
            "matched_rules": self.matched_rules,
            "filters": {
                "period": f.period.dump() if f.period else None,
                "period2": f.period2.dump() if f.period2 else None,
                "categories": f.category_names,
                "cards": f.card_names,
                "accounts": f.account_names,
                "projects": f.project_names,
                "payment_methods": f.payment_methods,
                "people": f.people,
                "amount": asdict(f.amount),
                "paid": f.paid,
                "overdue": f.overdue,
                "needs_review": f.needs_review,
                "is_installment": f.is_installment,
                "is_recurring": f.is_recurring,
                "is_essential": f.is_essential,
                "deductible": f.deductible,
                "mei": f.mei,
                "text_terms": f.text_terms,
                "unresolved_subject": f.unresolved_subject,
            },
        }
