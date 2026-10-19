"""Painel de administração (só para administradores)."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AdminUser, DbSession, MailerDep
from app.services import admin

router = APIRouter(prefix="/admin", tags=["administração"])


class Overview(BaseModel):
    users: int
    pending: int
    blocked: int
    unverified: int
    active_7d: int
    new_7d: int
    feedback_new: int
    signup_approval: bool


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_id: uuid.UUID | None
    created_at: datetime
    email_verified: bool
    access_status: str
    approved_at: datetime | None
    is_admin: bool
    totp_enabled: bool
    last_seen_at: datetime | None
    active_sessions: int
    entries: int


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime


class EmailOut(BaseModel):
    id: uuid.UUID
    to: str
    subject: str
    created_at: datetime
    link: str | None
    body: str


class ActionIn(BaseModel):
    action: Literal[
        "approve",
        "block",
        "unblock",
        "revoke_sessions",
        "verify_email",
        "resend_verification",
        "make_admin",
        "revoke_admin",
        "delete",
    ]


@router.get("/overview")
def overview(_: AdminUser, db: DbSession) -> Overview:
    return Overview.model_validate(admin.overview(db))


@router.get("/users")
def users(_: AdminUser, db: DbSession) -> list[AdminUserOut]:
    return [AdminUserOut.model_validate(u) for u in admin.list_users(db)]


@router.get("/users/{user_id}/sessions")
def sessions(user_id: uuid.UUID, _: AdminUser, db: DbSession) -> list[SessionOut]:
    return [
        SessionOut(
            id=s.id,
            user_agent=s.user_agent,
            ip=s.ip,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
        )
        for s in admin.user_sessions(db, user_id)
    ]


@router.post("/users/{user_id}/action")
def action(
    user_id: uuid.UUID, body: ActionIn, me: AdminUser, db: DbSession, mail: MailerDep
) -> dict[str, str]:
    user = admin.act(db, me, user_id, body.action, mail)
    return {"status": user.access_status if user else "deleted"}


@router.get("/emails")
def emails(_: AdminUser, db: DbSession) -> list[EmailOut]:
    return [EmailOut.model_validate(e) for e in admin.email_log(db)]
