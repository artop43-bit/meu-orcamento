import json
from typing import Literal

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.months import current_month, format_month, parse_month
from app.schemas.data import (
    LegacyImport,
    LegacyPreviewIn,
    LegacyPreviewOut,
    LegacyResult,
    StatementImportIn,
    StatementPreviewIn,
    StatementPreviewOut,
    StatementResult,
)
from app.services import export, legacy_import, statement_import

router = APIRouter(tags=["importar e exportar"])

MAX_EXPORT_MONTHS = 120
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attachment(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------- importar


@router.post("/import/legacy/preview")
def legacy_preview(body: LegacyPreviewIn, user: CurrentUser, db: DbSession) -> LegacyPreviewOut:
    data = legacy_import.preview(db, user, body.data, parse_month(body.month))
    return LegacyPreviewOut.model_validate(data)


@router.post("/import/legacy")
def legacy_commit(body: LegacyImport, user: CurrentUser, db: DbSession) -> LegacyResult:
    return LegacyResult.model_validate(legacy_import.commit(db, user, body.model_dump()))


@router.post("/import/statement/preview")
def statement_preview(
    body: StatementPreviewIn, user: CurrentUser, db: DbSession
) -> StatementPreviewOut:
    data = statement_import.preview(db, user, body.filename, body.content, body.invert)
    return StatementPreviewOut.model_validate(data)


@router.post("/import/statement")
def statement_commit(body: StatementImportIn, user: CurrentUser, db: DbSession) -> StatementResult:
    items = [t.model_dump() for t in body.transactions]
    return StatementResult.model_validate(statement_import.commit(db, user, items))


# ---------------------------------------------------------------- exportar


@router.get("/export/transactions")
def export_transactions(
    user: CurrentUser,
    db: DbSession,
    start: str,
    end: str | None = None,
    format: Literal["csv", "xlsx"] = "csv",
) -> Response:
    first = parse_month(start)
    last = parse_month(end) if end else current_month()
    if last < first:
        raise AppError(400, "invalid_period", "O mês final não pode ser antes do inicial.")
    if export.months_between(first, last) > MAX_EXPORT_MONTHS:
        raise AppError(400, "invalid_period", "Exporte no máximo 10 anos por vez.")

    rows = export.transactions(db, user, first, last)
    name = f"meu-orcamento_{format_month(first)}_a_{format_month(last)}"
    if format == "csv":
        return _attachment(export.to_csv(rows), f"{name}.csv", "text/csv; charset=utf-8")
    summary = export.period_summary(db, user, first, last)
    return _attachment(export.to_xlsx(rows, summary), f"{name}.xlsx", XLSX)


@router.get("/export/backup")
def export_backup(user: CurrentUser, db: DbSession) -> Response:
    content = json.dumps(export.backup(db, user), ensure_ascii=False, indent=2).encode("utf-8")
    return _attachment(content, "meu-orcamento-backup.json", "application/json")
