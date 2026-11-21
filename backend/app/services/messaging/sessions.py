"""Sessão do WhatsApp da pessoa: resumo, conectar (QR Code) e desconectar."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import MessagingChat, MessagingMessage, MessagingSession, User
from app.services.messaging import connector_client
from app.services.messaging.phones import format_phone_display

SESSION_STATUSES = ("disconnected", "connecting", "qr", "ready", "error")
CONNECTOR_FAILED = "Não foi possível falar com o conector do WhatsApp."


def connector_unavailable() -> AppError:
    return AppError(
        503,
        "connector_unavailable",
        "A conexão com o WhatsApp não está disponível neste servidor.",
    )


def get_or_create_session(db: Session, user: User) -> MessagingSession:
    session = db.scalar(select(MessagingSession).where(MessagingSession.user_id == user.id))
    if session is None:
        session = MessagingSession(user_id=user.id, status="disconnected", wanted=False)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def session_summary(db: Session, user: User) -> dict[str, Any]:
    session = get_or_create_session(db, user)
    pending_outbox = int(
        db.scalar(
            select(func.count(MessagingMessage.id)).where(
                MessagingMessage.user_id == user.id,
                MessagingMessage.direction == "out",
                MessagingMessage.status == "pending",
            )
        )
        or 0
    )
    chats_count = int(
        db.scalar(
            select(func.count(MessagingChat.id)).where(
                MessagingChat.user_id == user.id,
                MessagingChat.archived.is_(False),
            )
        )
        or 0
    )
    unread_chats = int(
        db.scalar(
            select(func.count(MessagingChat.id)).where(
                MessagingChat.user_id == user.id,
                MessagingChat.archived.is_(False),
                MessagingChat.unread_count > 0,
            )
        )
        or 0
    )
    status = session.status if session.status in SESSION_STATUSES else "disconnected"
    return {
        "status": status,
        "connected": status == "ready",
        "available": connector_client.is_configured(),
        "phone": session.phone,
        "phone_display": format_phone_display(session.phone),
        "display_name": session.display_name,
        "qr_code": session.qr_code if status == "qr" else None,
        "pending_outbox": pending_outbox,
        "chats_count": chats_count,
        "unread_chats": unread_chats,
        "last_seen_at": session.last_seen_at,
        "last_error": session.last_error,
        "updated_at": session.updated_at,
    }


def connect_session(db: Session, user: User) -> dict[str, Any]:
    """Pede a conexão: o conector gera o QR Code (ou reconecta, se já pareado)."""
    if not connector_client.is_configured():
        raise connector_unavailable()
    session = get_or_create_session(db, user)
    others = int(
        db.scalar(
            select(func.count(MessagingSession.id)).where(
                MessagingSession.wanted.is_(True),
                MessagingSession.id != session.id,
            )
        )
        or 0
    )
    if others >= get_settings().messaging_max_sessions:
        raise AppError(
            409,
            "sessions_full",
            "O servidor atingiu o limite de números conectados. Tente de novo mais tarde.",
        )

    session.wanted = True
    session.status = "connecting"
    session.qr_code = None
    session.last_error = None
    session.updated_at = utcnow()
    # Grava antes de chamar: o conector manda o QR para a API logo em seguida.
    db.commit()
    try:
        connector_client.start_session(session.id)
    except connector_client.ConnectorError:
        session.status = "error"
        session.last_error = CONNECTOR_FAILED
        session.updated_at = utcnow()
        db.commit()
    return session_summary(db, user)


def disconnect_session(db: Session, user: User) -> dict[str, Any]:
    """Desconecta o número (logout no WhatsApp) e esquece os dados da conexão."""
    session = get_or_create_session(db, user)
    session.wanted = False
    session.status = "disconnected"
    session.qr_code = None
    session.phone = None
    session.display_name = None
    session.wa_jid = None
    session.last_error = None
    session.updated_at = utcnow()
    db.commit()
    # Melhor esforço: se o conector estiver fora do ar, ele não restaura a sessão (wanted=false).
    connector_client.stop_session(session.id, logout=True)
    return session_summary(db, user)
