import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, StringConstraints

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


def _period(start: str, end: str | None, start_day: int = 1) -> tuple[Any, Any]:
    first = parse_month(start)
    last = parse_month(end) if end else current_month(start_day)
    if last < first:
        raise AppError(400, "invalid_period", "O mês final não pode ser antes do inicial.")
    if export.months_between(first, last) > MAX_EXPORT_MONTHS:
        raise AppError(400, "invalid_period", "Exporte no máximo 10 anos por vez.")
    return first, last


def _filters(
    kind: str, categories: list[uuid.UUID], accounts: list[uuid.UUID], cards: list[uuid.UUID]
) -> export.Filters:
    return export.Filters(
        kind=kind, category_ids=set(categories), account_ids=set(accounts), card_ids=set(cards)
    )


ExportKind = Literal["all", "expense", "income"]
IdList = Annotated[list[uuid.UUID], Query()]


@router.get("/export/count")
def export_count(
    user: CurrentUser,
    db: DbSession,
    start: str,
    end: str | None = None,
    kind: ExportKind = "all",
    category: IdList = [],  # noqa: B006 (padrão do FastAPI para listas na query)
    account: IdList = [],  # noqa: B006
    card: IdList = [],  # noqa: B006
) -> dict[str, Any]:
    first, last = _period(start, end, user.month_start_day)
    rows = export.transactions(db, user, first, last, _filters(kind, category, account, card))
    # v1.7.6.1: o resumo do recorte na tela (receitas, despesas e saldo).
    income = sum((r["amount"] for r in rows if r["type"] == "Receita"), Decimal(0))
    expenses = sum((-r["amount"] for r in rows if r["type"] == "Despesa"), Decimal(0))
    return {
        "count": len(rows),
        "income": str(income),
        "expenses": str(expenses),
        "balance": str(income - expenses),
    }


@router.get("/export/annual")
def export_annual(
    user: CurrentUser, db: DbSession, year: Annotated[int, Query(ge=2000, le=2100)]
) -> dict[str, Any]:
    return export.annual(db, user, year)


@router.get("/export/annual.pdf")
def export_annual_pdf(
    user: CurrentUser, db: DbSession, year: Annotated[int, Query(ge=2000, le=2100)]
) -> Response:
    """Resumo anual em PDF (v1.7.6.1), com a parte para o Imposto de Renda."""
    from datetime import date

    from app.services import pdf_export

    rows = export.transactions(db, user, date(year, 1, 1), date(year, 12, 1))
    content = pdf_export.annual_pdf(
        export.annual(db, user, year), rows, user.display_name or user.email
    )
    return _attachment(content, f"meu-orcamento_resumo-anual_{year}.pdf", "application/pdf")


@router.get("/export/transactions")
def export_transactions(
    user: CurrentUser,
    db: DbSession,
    start: str,
    end: str | None = None,
    format: Literal["csv", "xlsx", "pdf"] = "csv",
    kind: ExportKind = "all",
    category: IdList = [],  # noqa: B006
    account: IdList = [],  # noqa: B006
    card: IdList = [],  # noqa: B006
) -> Response:
    first, last = _period(start, end, user.month_start_day)
    rows = export.transactions(db, user, first, last, _filters(kind, category, account, card))
    name = f"meu-orcamento_{format_month(first)}_a_{format_month(last)}"
    if format == "csv":
        return _attachment(export.to_csv(rows), f"{name}.csv", "text/csv; charset=utf-8")
    if format == "pdf":
        from app.services import pdf_export

        content = pdf_export.transactions_pdf(
            rows,
            export.by_category(rows),
            start=first,
            end=last,
            kind=kind,
            filters=export.describe_filters(
                db, user, first, last, _filters(kind, category, account, card)
            ),
            owner=user.display_name or user.email,
        )
        return _attachment(content, f"{name}.pdf", "application/pdf")
    summary = export.period_summary(db, user, first, last)
    return _attachment(export.to_xlsx(rows, summary), f"{name}.xlsx", XLSX)


@router.get("/export/backup")
def export_backup(user: CurrentUser, db: DbSession) -> Response:
    content = json.dumps(export.backup(db, user), ensure_ascii=False, indent=2).encode("utf-8")
    return _attachment(content, "meu-orcamento-backup.json", "application/json")


# ---------------------------------------------------------------- importação única (v0.8)


def _read_upload(upload: UploadFile) -> bytes:
    from app.services import importer

    raw = upload.file.read(importer.MAX_BYTES + 1)
    if len(raw) > importer.MAX_BYTES:
        raise AppError(413, "file_too_large", "O arquivo passa de 5 MB. Divida-o por período.")
    return raw


@router.post("/import/analyze")
def import_analyze(
    user: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Passo 1: identifica o formato, o tipo (conta ou cartão) e as colunas do arquivo."""
    from app.services import importer

    return importer.analyze(db, user, _read_upload(file), file.filename or "arquivo")


@router.post("/import/preview")
def import_preview(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
    invert: Annotated[bool, Form()] = False,
) -> StatementPreviewOut:
    """Passo 3: lançamentos com categoria sugerida e repetidos marcados."""
    from app.services import importer

    parsed = None
    if mapping:
        try:
            parsed = json.loads(mapping)
        except ValueError as exc:
            raise AppError(400, "invalid_mapping", "Mapeamento de colunas inválido.") from exc
    data = importer.preview(
        db, user, _read_upload(file), file.filename or "arquivo", parsed, invert
    )
    return StatementPreviewOut.model_validate(data)


class ImportCommitIn(StatementImportIn):
    filename: Annotated[str, StringConstraints(max_length=160)] = "arquivo"
    file_format: Literal["ofx", "csv", "xlsx"] = "csv"
    account_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    save_mapping: dict[str, Any] | None = None


@router.post("/import/commit")
def import_commit(body: ImportCommitIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    from app.services import importer

    items = [t.model_dump() for t in body.transactions]
    return importer.commit(
        db,
        user,
        items,
        filename=body.filename,
        file_format=body.file_format,
        account_id=body.account_id,
        card_id=body.card_id,
        save_mapping=body.save_mapping,
    )


@router.post("/import/restore")
def import_restore(
    user: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()]
) -> dict[str, int]:
    """Backup do Meu Orçamento: recria o que não existe, sem duplicar."""
    from app.services import importer

    fmt, content = importer.detect_format(_read_upload(file), file.filename or "backup.json")
    if fmt != "backup":
        raise AppError(400, "invalid_file", "Este arquivo não é um backup do Meu Orçamento.")
    return importer.restore_backup(db, user, content)


class BatchOut(BaseModel):
    id: uuid.UUID
    filename: str
    file_format: str
    count: int
    created_at: datetime
    undone_at: datetime | None


@router.get("/import/batches")
def import_batches(user: CurrentUser, db: DbSession) -> list[BatchOut]:
    from app.services import importer

    return [
        BatchOut.model_validate(b, from_attributes=True) for b in importer.list_batches(db, user)
    ]


@router.post("/import/batches/{batch_id}/undo")
def import_undo(batch_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, int]:
    from app.services import importer

    return {"removed": importer.undo(db, user, batch_id)}
