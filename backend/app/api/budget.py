import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.months import current_month, format_month, parse_month
from app.schemas.budget import (
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    ContributionIn,
    DeleteScope,
    ExpenseIn,
    ExpenseOut,
    ExpensePatch,
    GoalIn,
    GoalOut,
    GoalPatch,
    HistoryPoint,
    IncomeIn,
    IncomeOut,
    IncomePatch,
    MonthOut,
    MonthSummary,
    RecurringIn,
    RecurringOut,
    RecurringPatch,
)
from app.services import budget as service

router = APIRouter(tags=["orçamento"])

Scope = Annotated[DeleteScope, Query(description="one = só este; following = este e os próximos")]


def _changes(body: BaseModel, nullable: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    """Campos enviados no PATCH. null só é aceito onde faz sentido "limpar" o valor."""
    return {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if value is not None or key in nullable
    }


# ---------------------------------------------------------------- categorias


@router.get("/categories")
def list_categories(user: CurrentUser, db: DbSession) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in service.list_categories(db, user)]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, user: CurrentUser, db: DbSession) -> CategoryOut:
    return CategoryOut.model_validate(service.create_category(db, user, body.model_dump()))


@router.patch("/categories/{category_id}")
def update_category(
    category_id: uuid.UUID, body: CategoryPatch, user: CurrentUser, db: DbSession
) -> CategoryOut:
    changes = _changes(body, nullable={"color", "monthly_limit"})
    return CategoryOut.model_validate(service.update_category(db, user, category_id, changes))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_category(db, user, category_id)


# ---------------------------------------------------------------- mês


@router.get("/months/current")
def get_current_month() -> dict[str, str]:
    return {"month": format_month(current_month())}


@router.get("/months/{month}")
def get_month(month: str, user: CurrentUser, db: DbSession) -> MonthOut:
    data = service.get_month(db, user, parse_month(month))
    return MonthOut(
        month=format_month(data.month),
        incomes=[IncomeOut.model_validate(i) for i in data.incomes],
        expenses=[ExpenseOut.model_validate(e) for e in data.expenses],
        summary=MonthSummary.model_validate(data.summary),
    )


@router.get("/history")
def get_history(
    user: CurrentUser,
    db: DbSession,
    until: str | None = None,
    months: Annotated[int, Query(ge=1, le=60)] = 12,
) -> list[HistoryPoint]:
    end = parse_month(until) if until else current_month()
    return [
        HistoryPoint.model_validate({**point, "month": format_month(point["month"])})
        for point in service.history(db, user, end, months)
    ]


# ---------------------------------------------------------------- rendas


@router.post("/months/{month}/incomes", status_code=status.HTTP_201_CREATED)
def create_income(month: str, body: IncomeIn, user: CurrentUser, db: DbSession) -> IncomeOut:
    income = service.create_income(db, user, parse_month(month), body.model_dump())
    return IncomeOut.model_validate(income)


@router.patch("/incomes/{income_id}")
def update_income(
    income_id: uuid.UUID, body: IncomePatch, user: CurrentUser, db: DbSession
) -> IncomeOut:
    return IncomeOut.model_validate(service.update_income(db, user, income_id, _changes(body)))


@router.delete("/incomes/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_income(
    income_id: uuid.UUID, user: CurrentUser, db: DbSession, scope: Scope = "one"
) -> None:
    service.delete_income(db, user, income_id, scope)


# ---------------------------------------------------------------- contas


@router.post("/months/{month}/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(
    month: str, body: ExpenseIn, user: CurrentUser, db: DbSession
) -> list[ExpenseOut]:
    """Cria a conta. Com `installments`, cria uma parcela por mês e retorna todas."""
    expenses = service.create_expense(db, user, parse_month(month), body.model_dump())
    return [ExpenseOut.model_validate(e) for e in expenses]


@router.patch("/expenses/{expense_id}")
def update_expense(
    expense_id: uuid.UUID, body: ExpensePatch, user: CurrentUser, db: DbSession
) -> ExpenseOut:
    changes = _changes(body, nullable={"category_id", "due_date", "notes"})
    return ExpenseOut.model_validate(service.update_expense(db, user, expense_id, changes))


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: uuid.UUID, user: CurrentUser, db: DbSession, scope: Scope = "one"
) -> None:
    service.delete_expense(db, user, expense_id, scope)


# ---------------------------------------------------------------- fixas


@router.get("/recurring")
def list_recurring(user: CurrentUser, db: DbSession) -> list[RecurringOut]:
    return [RecurringOut.model_validate(r) for r in service.list_recurring(db, user)]


@router.post("/recurring", status_code=status.HTTP_201_CREATED)
def create_recurring(body: RecurringIn, user: CurrentUser, db: DbSession) -> RecurringOut:
    return RecurringOut.model_validate(service.create_recurring(db, user, body.model_dump()))


@router.patch("/recurring/{item_id}")
def update_recurring(
    item_id: uuid.UUID, body: RecurringPatch, user: CurrentUser, db: DbSession
) -> RecurringOut:
    changes = _changes(body, nullable={"category_id", "due_day", "end_month"})
    return RecurringOut.model_validate(service.update_recurring(db, user, item_id, changes))


@router.delete("/recurring/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_recurring(db, user, item_id)


# ---------------------------------------------------------------- metas


def _goal_out(goal: Any) -> GoalOut:
    return GoalOut.model_validate(
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "current_amount": goal.current_amount,
            "target_date": goal.target_date,
            "progress_pct": service.goal_progress(goal),
        }
    )


@router.get("/goals")
def list_goals(user: CurrentUser, db: DbSession) -> list[GoalOut]:
    return [_goal_out(g) for g in service.list_goals(db, user)]


@router.post("/goals", status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, user: CurrentUser, db: DbSession) -> GoalOut:
    return _goal_out(service.create_goal(db, user, body.model_dump()))


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: uuid.UUID, body: GoalPatch, user: CurrentUser, db: DbSession) -> GoalOut:
    changes = _changes(body, nullable={"target_date"})
    return _goal_out(service.update_goal(db, user, goal_id, changes))


@router.post("/goals/{goal_id}/contributions")
def contribute(
    goal_id: uuid.UUID, body: ContributionIn, user: CurrentUser, db: DbSession
) -> GoalOut:
    return _goal_out(service.contribute_to_goal(db, user, goal_id, body.amount))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_goal(db, user, goal_id)
