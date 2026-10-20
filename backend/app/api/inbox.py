"""v0.9: caixa de mensagens, recados da administração, aparência na conta e começar do zero."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from app.api.deps import AdminUser, CurrentUser, DbSession, MailerDep
from app.services import inbox, reset

router = APIRouter(tags=["mensagens e conta"])


# ---------------------------------------------------------------- caixa de mensagens


class InboxItemOut(BaseModel):
    id: uuid.UUID
    kind: Literal["reply", "announcement", "alert"]
    title: str
    body: str
    important: bool
    thread_id: uuid.UUID | None
    read: bool
    created_at: datetime


def _item(item) -> InboxItemOut:  # type: ignore[no-untyped-def]
    return InboxItemOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        body=item.body,
        important=item.important,
        thread_id=item.thread_id,
        read=item.read_at is not None,
        created_at=item.created_at,
    )


class UnreadOut(BaseModel):
    unread: int


class ReadIn(BaseModel):
    read: bool = True


@router.get("/inbox")
def list_inbox(user: CurrentUser, db: DbSession) -> list[InboxItemOut]:
    return [_item(i) for i in inbox.list_items(db, user)]


@router.get("/inbox/unread")
def inbox_unread(user: CurrentUser, db: DbSession) -> UnreadOut:
    return UnreadOut(unread=inbox.unread_count(db, user))


@router.patch("/inbox/{item_id}")
def mark_item(item_id: uuid.UUID, body: ReadIn, user: CurrentUser, db: DbSession) -> InboxItemOut:
    return _item(inbox.mark_read(db, user, item_id, body.read))


@router.post("/inbox/read-all")
def read_all(user: CurrentUser, db: DbSession) -> UnreadOut:
    inbox.mark_all_read(db, user)
    return UnreadOut(unread=0)


# ---------------------------------------------------------------- recados (administração)


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=3, max_length=5000)
    important: bool = False
    include_pending: bool = False

    @field_validator("title", "body")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Escreva pelo menos 3 caracteres.")
        return value


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    important: bool
    include_pending: bool
    recipients: int
    read: int
    created_at: datetime


class AudienceOut(BaseModel):
    recipients: int


@router.get("/admin/announcements")
def announcements(_: AdminUser, db: DbSession) -> list[AnnouncementOut]:
    return [
        AnnouncementOut(
            id=row["announcement"].id,
            title=row["announcement"].title,
            body=row["announcement"].body,
            important=row["announcement"].important,
            include_pending=row["announcement"].include_pending,
            recipients=row["announcement"].recipients,
            read=row["read"],
            created_at=row["announcement"].created_at,
        )
        for row in inbox.list_announcements(db)
    ]


@router.get("/admin/announcements/audience")
def audience(
    _: AdminUser, db: DbSession, include_pending: Annotated[bool, Query()] = False
) -> AudienceOut:
    return AudienceOut(recipients=inbox.audience_count(db, include_pending))


@router.post("/admin/announcements", status_code=201)
def create_announcement(
    body: AnnouncementIn, admin: AdminUser, db: DbSession, mail: MailerDep
) -> AnnouncementOut:
    item = inbox.announce(
        db, admin, body.title, body.body, body.important, body.include_pending, mail
    )
    return AnnouncementOut(
        id=item.id,
        title=item.title,
        body=item.body,
        important=item.important,
        include_pending=item.include_pending,
        recipients=item.recipients,
        read=0,
        created_at=item.created_at,
    )


# ---------------------------------------------------------------- aparência na conta


class AppearanceIn(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    accent: Literal["verde", "azul", "roxo", "laranja"] | None = None


class AppearanceOut(BaseModel):
    theme: str | None
    accent: str | None


@router.patch("/me/appearance")
def appearance(body: AppearanceIn, user: CurrentUser, db: DbSession) -> AppearanceOut:
    if body.theme is not None:
        user.theme = body.theme
    if body.accent is not None:
        user.accent = body.accent
    db.commit()
    return AppearanceOut(theme=user.theme, accent=user.accent)


# ---------------------------------------------------------------- mês financeiro


class CycleIn(BaseModel):
    month_start_day: int = Field(ge=1, le=28)


class CycleOut(BaseModel):
    month_start_day: int


@router.patch("/me/cycle")
def cycle(body: CycleIn, user: CurrentUser, db: DbSession) -> CycleOut:
    """Dia em que o mês financeiro começa (1 = mês do calendário; até 28 para valer todo mês)."""
    user.month_start_day = body.month_start_day
    db.commit()
    return CycleOut(month_start_day=user.month_start_day)


# ---------------------------------------------------------------- começar do zero


class ResetPreviewOut(BaseModel):
    counts: dict[str, int]


class ResetIn(BaseModel):
    areas: list[Literal[tuple(reset.AREAS)]] = Field(min_length=1)  # type: ignore[valid-type]
    password: str = Field(min_length=1, max_length=200)
    confirmation: str = Field(max_length=40)
    code: str | None = Field(default=None, max_length=20)


class ResetOut(BaseModel):
    removed: dict[str, int]


@router.get("/account/reset")
def reset_preview(user: CurrentUser, db: DbSession) -> ResetPreviewOut:
    return ResetPreviewOut(counts=reset.preview(db, user))


@router.post("/account/reset")
def reset_account(body: ResetIn, user: CurrentUser, db: DbSession, mail: MailerDep) -> ResetOut:
    removed = reset.reset(
        db, user, list(body.areas), body.password, body.confirmation, body.code, mail
    )
    return ResetOut(removed=removed)
