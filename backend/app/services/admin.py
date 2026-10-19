"""Painel de administração: usuários, liberação do beta fechado, e-mails enviados e uso."""

import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import EmailLog, Expense, Feedback, Income, User, UserSession
from app.services import auth
from app.services.auth import Mailer

LINK_RE = re.compile(r"https?://\S+")
EMAIL_LOG_DAYS = 30


def overview(db: Session) -> dict[str, Any]:
    now = utcnow()
    week = now - timedelta(days=7)
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    return {
        "users": count(select(func.count()).select_from(User)),
        "pending": count(select(func.count()).where(User.access_status == "pending")),
        "blocked": count(select(func.count()).where(User.access_status == "blocked")),
        "unverified": count(select(func.count()).where(User.email_verified_at.is_(None))),
        "active_7d": count(
            select(func.count(func.distinct(UserSession.user_id)))
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.last_seen_at >= week)
        ),
        "new_7d": count(select(func.count()).where(User.created_at >= week)),
        "feedback_new": count(select(func.count()).where(Feedback.status == "new")),
        "signup_approval": get_settings().signup_approval,
    }


def list_users(db: Session) -> list[dict[str, Any]]:
    now = utcnow()
    last_seen = dict(
        db.execute(
            select(UserSession.user_id, func.max(UserSession.last_seen_at)).group_by(
                UserSession.user_id
            )
        ).all()
    )
    sessions = dict(
        db.execute(
            select(UserSession.user_id, func.count())
            .where(UserSession.expires_at > now)
            .group_by(UserSession.user_id)
        ).all()
    )
    expenses = dict(
        db.execute(select(Expense.user_id, func.count()).group_by(Expense.user_id)).all()
    )
    incomes = dict(db.execute(select(Income.user_id, func.count()).group_by(Income.user_id)).all())
    users = db.scalars(select(User).order_by(User.created_at.desc()))
    return [
        {
            "id": u.id,
            "email": u.email,
            "created_at": u.created_at,
            "email_verified": u.email_verified,
            "access_status": u.access_status,
            "approved_at": u.approved_at,
            "is_admin": auth.is_admin(u),
            "totp_enabled": u.totp_enabled,
            "last_seen_at": last_seen.get(u.id),
            "active_sessions": sessions.get(u.id, 0),
            "entries": expenses.get(u.id, 0) + incomes.get(u.id, 0),
        }
        for u in users
    ]


def user_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    _get(db, user_id)
    return list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.expires_at > utcnow())
            .order_by(UserSession.last_seen_at.desc())
        )
    )


def _get(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "Usuário não encontrado.")
    return user


def act(db: Session, admin: User, user_id: uuid.UUID, action: str, mail: Mailer) -> User | None:
    """Ações do painel sobre uma conta. Ações destrutivas não valem para a própria conta."""
    user = _get(db, user_id)
    if user.id == admin.id and action in ("block", "delete", "revoke_admin"):
        raise AppError(400, "self_action", "Esta ação não pode ser feita na sua própria conta.")
    url = get_settings().frontend_url.rstrip("/")
    if action == "approve":
        user.access_status = "approved"
        user.approved_at = utcnow()
        mail(
            user.email,
            "Acesso liberado ao Meu Orçamento",
            "Seu acesso ao Meu Orçamento foi liberado.\n\n"
            + (
                ""
                if user.email_verified
                else "Antes, confirme seu e-mail pelo link enviado no cadastro.\n\n"
            )
            + f"Para entrar: {url}/entrar",
        )
    elif action == "block":
        user.access_status = "blocked"
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    elif action == "unblock":
        user.access_status = "approved"
        user.approved_at = user.approved_at or utcnow()
    elif action == "revoke_sessions":
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    elif action == "verify_email":
        user.email_verified_at = user.email_verified_at or utcnow()
    elif action == "resend_verification":
        if user.email_verified:
            raise AppError(400, "already_verified", "Este e-mail já está confirmado.")
        auth._send_verification(db, user, mail)
    elif action == "make_admin":
        user.is_admin = True
    elif action == "revoke_admin":
        user.is_admin = False
    elif action == "delete":
        db.delete(user)
        db.commit()
        return None
    else:
        raise AppError(400, "invalid_action", "Ação desconhecida.")
    auth._record(db, user, f"admin_{action}")
    db.commit()
    return user


def email_log(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.scalars(select(EmailLog).order_by(EmailLog.created_at.desc()).limit(limit))
    return [
        {
            "id": e.id,
            "to": e.to,
            "subject": e.subject,
            "created_at": e.created_at,
            "link": (LINK_RE.search(e.body) or [None])[0],
            "body": e.body,
        }
        for e in rows
    ]


def cleanup_email_log(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=EMAIL_LOG_DAYS)
    result = db.execute(delete(EmailLog).where(EmailLog.created_at < cutoff))
    db.commit()
    return result.rowcount or 0


def cli_action(db: Session, command: str, email: str) -> str:
    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None:
        return f"Conta {email} não encontrada."
    if command == "make-admin":
        user.is_admin = True
        user.access_status = "approved"
        user.approved_at = user.approved_at or utcnow()
    elif command == "approve":
        user.access_status = "approved"
        user.approved_at = utcnow()
    elif command == "block":
        user.access_status = "blocked"
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return f"{user.email}: {command} ok (status {user.access_status}, admin {user.is_admin})."
