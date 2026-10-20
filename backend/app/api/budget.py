import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
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
    GoalSuggestion,
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
def get_current_month(user: CurrentUser) -> dict[str, str]:
    return {"month": format_month(current_month(user.month_start_day))}


@router.get("/months/{month}")
def get_month(month: str, user: CurrentUser, db: DbSession) -> MonthOut:
    from app.services import receipts

    data = service.get_month(db, user, parse_month(month))
    attached = receipts.ids_for(db, [e.id for e in data.expenses])
    expenses = []
    for e in data.expenses:
        out = ExpenseOut.model_validate(e)
        out.receipt_ids = attached.get(e.id, [])
        expenses.append(out)
    return MonthOut(
        month=format_month(data.month),
        incomes=[IncomeOut.model_validate(i) for i in data.incomes],
        expenses=expenses,
        summary=MonthSummary.model_validate(data.summary),
    )


# ---------------------------------------------------------------- comprovantes


class ReceiptsOut(BaseModel):
    receipt_ids: list[uuid.UUID]


@router.post("/expenses/{expense_id}/receipts", status_code=status.HTTP_201_CREATED)
def add_receipts(
    expense_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    images: Annotated[list[UploadFile], File(description="Até 3 imagens")],
) -> ReceiptsOut:
    from app.services import files, receipts

    limit = files.RULES["receipt"].max_bytes
    raws = []
    for upload in images:
        raw = upload.file.read(limit + 1)
        if len(raw) > limit:
            raise AppError(
                413, "file_too_large", f"Cada imagem pode ter até {limit // files.MB} MB."
            )
        raws.append(raw)
    return ReceiptsOut(receipt_ids=receipts.add(db, user, expense_id, raws))


@router.delete("/expenses/{expense_id}/receipts/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_receipt(
    expense_id: uuid.UUID, file_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    from app.services import receipts

    receipts.remove(db, user, expense_id, file_id)


@router.get("/history")
def get_history(
    user: CurrentUser,
    db: DbSession,
    until: str | None = None,
    months: Annotated[int, Query(ge=1, le=60)] = 12,
) -> list[HistoryPoint]:
    end = parse_month(until) if until else current_month(user.month_start_day)
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
    income_id: uuid.UUID, body: IncomePatch, user: CurrentUser, db: DbSession, scope: Scope = "one"
) -> IncomeOut:
    changes = _changes(body, nullable={"day", "notes", "account_id"})
    return IncomeOut.model_validate(service.update_income(db, user, income_id, changes, scope))


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
    expense_id: uuid.UUID,
    body: ExpensePatch,
    user: CurrentUser,
    db: DbSession,
    scope: Scope = "one",
) -> ExpenseOut:
    changes = _changes(
        body, nullable={"category_id", "due_date", "notes", "payment_method", "account_id"}
    )
    expense = service.update_expense(db, user, expense_id, changes, scope)
    return ExpenseOut.model_validate(expense)


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
    changes = _changes(
        body, nullable={"category_id", "due_day", "end_month", "payment_method", "notes"}
    )
    return RecurringOut.model_validate(service.update_recurring(db, user, item_id, changes))


@router.delete("/recurring/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_recurring(db, user, item_id)


# ---------------------------------------------------------------- metas


def _goal_out(goal: Any, db: Any = None, user: Any = None, image_id: Any = None) -> GoalOut:
    from app.services import goals as goal_service

    projection = goal_service.projection(db, user, goal) if db is not None else None
    if db is not None and image_id is None:
        image_id = goal_service.image_ids(db, [goal.id]).get(goal.id)
    return GoalOut.model_validate(
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "current_amount": goal.current_amount,
            "target_date": goal.target_date,
            "progress_pct": service.goal_progress(goal),
            "kind": goal.kind,
            "motivation": goal.motivation,
            "monthly_plan": goal.monthly_plan,
            "is_main": goal.is_main,
            "completed_at": goal.completed_at,
            "image_id": image_id,
            "projection": projection,
        }
    )


@router.get("/goals")
def list_goals(user: CurrentUser, db: DbSession) -> list[GoalOut]:
    from app.services import goals as goal_service

    items = service.list_goals(db, user)
    images = goal_service.image_ids(db, [g.id for g in items])
    return [_goal_out(g, db, user, images.get(g.id)) for g in items]


@router.get("/goals/suggestion")
def goal_suggestion(user: CurrentUser, db: DbSession) -> GoalSuggestion | None:
    """Sobra prevista no mês: sugere destinar parte à meta principal (nada é movido sozinho)."""
    from app.services import goals as goal_service

    found = goal_service.suggestion(db, user)
    return GoalSuggestion.model_validate(found) if found else None


@router.post("/goals", status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, user: CurrentUser, db: DbSession) -> GoalOut:
    from app.services import goals as goal_service

    return _goal_out(goal_service.create(db, user, body.model_dump()), db, user)


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: uuid.UUID, body: GoalPatch, user: CurrentUser, db: DbSession) -> GoalOut:
    from app.services import goals as goal_service

    changes = _changes(body, nullable={"target_date", "motivation", "monthly_plan"})
    return _goal_out(goal_service.update_goal(db, user, goal_id, changes), db, user)


@router.post("/goals/{goal_id}/contributions")
def contribute(
    goal_id: uuid.UUID, body: ContributionIn, user: CurrentUser, db: DbSession
) -> GoalOut:
    from app.services import goals as goal_service

    return _goal_out(goal_service.contribute(db, user, goal_id, body.amount), db, user)


@router.put("/goals/{goal_id}/image")
def set_goal_image(
    goal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    image: Annotated[UploadFile, File()],
) -> GoalOut:
    from app.services import files
    from app.services import goals as goal_service

    limit = files.RULES["goal"].max_bytes
    raw = image.file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(413, "file_too_large", f"A imagem pode ter até {limit // files.MB} MB.")
    return _goal_out(goal_service.set_image(db, user, goal_id, raw), db, user)


@router.delete("/goals/{goal_id}/image")
def remove_goal_image(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> GoalOut:
    from app.services import goals as goal_service

    return _goal_out(goal_service.remove_image(db, user, goal_id), db, user)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_goal(db, user, goal_id)
