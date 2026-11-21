"""Rotas da API da Fase D: Cofre de Documentos (`/api/cofre`) e Caderno (`/api/caderno`)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require_solution
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.services.memory import notebook as notebook_service
from app.services.memory import vault as vault_service

vault_router = APIRouter(
    prefix="/cofre",
    tags=["cofre"],
    dependencies=[Depends(require_solution("cofre"))],
)

notebook_router = APIRouter(
    prefix="/caderno",
    tags=["caderno"],
    dependencies=[Depends(require_solution("caderno"))],
)

VaultCategory = Literal[
    "warranty",
    "contract",
    "fiscal",
    "receipt",
    "certificate",
    "identity",
    "other",
]
TemplateKind = Literal["blank", "meeting", "sales_script", "sop", "planning"]


class VaultPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    category: VaultCategory | None = None
    issuer: str | None = Field(default=None, max_length=140)
    document_number: str | None = Field(default=None, max_length=80)
    issue_date: date | None = None
    expires_at: date | None = None
    notify_days_before: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = Field(default=None, max_length=4000)
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None


class ArchiveFromMessagingIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    category: VaultCategory = "other"
    expires_at: date | None = None


class ArchiveFromProposalIn(BaseModel):
    category: VaultCategory | None = None
    expires_at: date | None = None


class NoteIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    folder: str | None = Field(default=None, max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=12)
    pinned: bool = False
    template_kind: TemplateKind = "blank"
    content: str | None = Field(default=None, max_length=60000)
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    messaging_chat_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    vault_doc_id: uuid.UUID | None = None


class NotePatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    folder: str | None = Field(default=None, min_length=1, max_length=60)
    tags: list[str] | None = Field(default=None, max_length=12)
    pinned: bool | None = None
    content: str | None = Field(default=None, max_length=60000)
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    messaging_chat_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    vault_doc_id: uuid.UUID | None = None


# ---------------------------------------------------------------- Cofre de Documentos & Garantias


def _limit_vault_upload(user: CurrentUser) -> None:
    if limiter.hit(f"cofre-upload:{user.id}", 5, 60) is not None:
        raise AppError(
            429,
            "rate_limited",
            "Muitos envios seguidos no Cofre. Tente novamente em um minuto.",
        )


@vault_router.get("/hub/bridges")
def get_vault_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return vault_service.list_hub_bridges(db, user)


@vault_router.get("/documents")
def list_vault_documents(
    user: CurrentUser,
    db: DbSession,
    category: Annotated[str | None, Query()] = None,
    expiry_status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, Any]:
    return vault_service.list_documents(
        db, user, category=category, expiry_status=expiry_status, q=q
    )


@vault_router.post("/documents", status_code=status.HTTP_201_CREATED)
def upload_vault_document(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
    category: Annotated[VaultCategory, Form()] = "other",
    issuer: Annotated[str | None, Form()] = None,
    document_number: Annotated[str | None, Form()] = None,
    issue_date: Annotated[date | None, Form()] = None,
    expires_at: Annotated[date | None, Form()] = None,
    notify_days_before: Annotated[int, Form()] = 30,
    notes: Annotated[str | None, Form()] = None,
    contact_id: Annotated[uuid.UUID | None, Form()] = None,
    deal_id: Annotated[uuid.UUID | None, Form()] = None,
    project_id: Annotated[uuid.UUID | None, Form()] = None,
    proposal_id: Annotated[uuid.UUID | None, Form()] = None,
) -> dict[str, Any]:
    _limit_vault_upload(user)
    # Leitura síncrona para execução segura fora do event loop (regra E5).
    if file.size is not None and file.size > vault_service.MAX_VAULT_BYTES:
        raise AppError(413, "file_too_large", "O documento ultrapassa o limite de 15 MB.")
    raw = file.file.read(vault_service.MAX_VAULT_BYTES + 1)
    if len(raw) > vault_service.MAX_VAULT_BYTES:
        raise AppError(413, "file_too_large", "O documento ultrapassa o limite de 15 MB.")
    return vault_service.create_document(
        db,
        user,
        raw=raw,
        filename=file.filename,
        meta={
            "title": title,
            "category": category,
            "issuer": issuer,
            "document_number": document_number,
            "issue_date": issue_date,
            "expires_at": expires_at,
            "notify_days_before": notify_days_before,
            "notes": notes,
            "contact_id": contact_id,
            "deal_id": deal_id,
            "project_id": project_id,
            "proposal_id": proposal_id,
        },
    )


@vault_router.patch("/documents/{doc_id}")
def patch_vault_document(
    doc_id: uuid.UUID, body: VaultPatchIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return vault_service.update_document(db, user, doc_id, body.model_dump(exclude_unset=True))


@vault_router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vault_document(doc_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    vault_service.delete_document(db, user.id, doc_id)


@vault_router.get("/documents/{doc_id}/file")
def download_vault_file(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    inline: Annotated[bool, Query()] = False,
) -> Response:
    doc, safe_name = vault_service.get_document_file(db, user.id, doc_id)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=doc.data,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@vault_router.post("/from-messaging/{media_id}", status_code=status.HTTP_201_CREATED)
def archive_messaging_media(
    media_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    body: ArchiveFromMessagingIn | None = None,
) -> dict[str, Any]:
    payload = body or ArchiveFromMessagingIn()
    return vault_service.archive_from_messaging_media(
        db,
        user,
        media_id,
        title=payload.title,
        category=payload.category,
        expires_at=payload.expires_at,
    )


@vault_router.post("/from-proposal/{doc_id}", status_code=status.HTTP_201_CREATED)
def archive_proposal_pdf(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    body: ArchiveFromProposalIn | None = None,
) -> dict[str, Any]:
    payload = body or ArchiveFromProposalIn()
    return vault_service.archive_from_proposal(
        db,
        user,
        doc_id,
        category=payload.category,
        expires_at=payload.expires_at,
    )


# ---------------------------------------------------------------- Caderno & Base de Conhecimento


@notebook_router.get("/templates")
def get_notebook_templates() -> list[dict[str, str]]:
    return notebook_service.list_templates()


@notebook_router.get("/hub/bridges")
def get_notebook_bridges(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return notebook_service.list_hub_bridges(db, user)


@notebook_router.get("/notes")
def list_notebook_notes(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    folder: Annotated[str | None, Query(max_length=60)] = None,
    pinned_only: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    return notebook_service.list_notes(db, user.id, q=q, folder=folder, pinned_only=pinned_only)


@notebook_router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_notebook_note(body: NoteIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return notebook_service.create_note(db, user.id, body.model_dump())


@notebook_router.patch("/notes/{note_id}")
def patch_notebook_note(
    note_id: uuid.UUID, body: NotePatchIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    return notebook_service.update_note(db, user.id, note_id, body.model_dump(exclude_unset=True))


@notebook_router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_notebook_note(note_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    notebook_service.delete_note(db, user.id, note_id)
