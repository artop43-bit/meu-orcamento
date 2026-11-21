"""Painel admin: usuários, permissões de recursos, beta fechado e e-mails enviados."""

import json
import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import (
    DataSnapshot,
    DataSource,
    EmailLog,
    Expense,
    Income,
    MessagingConnectorKV,
    MessagingMedia,
    StoredFile,
    SupportThread,
    User,
    UserSession,
    VaultDocument,
)
from app.services import auth
from app.services.auth import Mailer

LINK_RE = re.compile(r"https?://\S+")
EMAIL_LOG_DAYS = 30
GLOBAL_BLOCKED_KV_KEY = "hub_global_blocked_resources"
MIN_STORAGE_QUOTA_MB = 5
MAX_STORAGE_QUOTA_MB = 2048
DEFAULT_STORAGE_QUOTA_MB = 100

CONTROLLABLE_SOLUTIONS: list[dict[str, str]] = [
    {
        "id": "meu-orcamento",
        "label": "Meu Orçamento",
        "description": "Orçamento mensal, contas, cartões, metas, investimentos e divisões.",
    },
    {
        "id": "mensageria",
        "label": "Mensageria (WhatsApp)",
        "description": "Conversas do WhatsApp por QR Code, envio de mídias e CRM 360° no chat.",
    },
    {
        "id": "dashboard-crm",
        "label": "Dashboard & CRM",
        "description": "Painéis personalizados, funil, contatos, PDF/CSV e conectores de API.",
    },
    {
        "id": "catalogo",
        "label": "Catálogo, Estoque & Pedidos",
        "description": "Cadastro de produtos e serviços, controle de estoque, margem e pedidos.",
    },
    {
        "id": "propostas",
        "label": "Propostas, Contratos & Recibos PDF",
        "description": "Geração de propostas comerciais, ordens de serviço e recibos em PDF.",
    },
    {
        "id": "projetos",
        "label": "Projetos & Tarefas",
        "description": "Quadros Kanban de entrega, checklists, horas trabalhadas e rentabilidade.",
    },
    {
        "id": "agenda",
        "label": "Agenda & Compromissos",
        "description": "Agenda unificada com compromissos, follow-ups, prazos e vencimentos.",
    },
    {
        "id": "cofre",
        "label": "Cofre de Documentos & Garantias",
        "description": "Arquivo permanente indexado com OCR local e controle de validade.",
    },
    {
        "id": "caderno",
        "label": "Caderno & Base de Conhecimento",
        "description": "Notas em Markdown, links entre notas, roteiros e busca BM25.",
    },
]

CONTROLLABLE_FEATURES: list[dict[str, str]] = [
    {
        "id": "feature:whatsapp_connect",
        "label": "Conexão de WhatsApp por QR Code",
        "description": "Permite parear um número de WhatsApp no conector da Mensageria.",
    },
    {
        "id": "feature:external_api",
        "label": "Conectores de API externa (HTTPS)",
        "description": "Permite cadastrar e consultar APIs REST/JSON externas no Dashboard & CRM.",
    },
    {
        "id": "feature:pdf_ocr_upload",
        "label": "Upload e leitura local de PDF/CSV/OCR",
        "description": "Permite enviar arquivos PDF/CSV para extração tabular e OCR no servidor.",
    },
    {
        "id": "feature:data_export",
        "label": "Exportação e backup de dados",
        "description": "Permite baixar backups completos e exportar planilhas da conta.",
    },
]

ALL_CONTROLLABLE_IDS: set[str] = {
    *(item["id"] for item in CONTROLLABLE_SOLUTIONS),
    *(item["id"] for item in CONTROLLABLE_FEATURES),
}


def parse_blocked_resources(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
        if not isinstance(loaded, list):
            return []
        out: list[str] = []
        for item in loaded:
            key = str(item).strip()
            if key in ALL_CONTROLLABLE_IDS and key not in out:
                out.append(key)
        return out
    except Exception:
        return []


def format_blocked_resources(items: list[str] | None) -> str | None:
    if not items:
        return None
    cleaned: list[str] = []
    for item in items:
        key = str(item).strip()
        if key in ALL_CONTROLLABLE_IDS and key not in cleaned:
            cleaned.append(key)
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def get_global_blocked_resources(db: Session) -> list[str]:
    row = db.get(MessagingConnectorKV, GLOBAL_BLOCKED_KV_KEY)
    if row is None:
        return []
    return parse_blocked_resources(row.value)


def set_global_blocked_resources(db: Session, admin_user: User, resources: list[str]) -> list[str]:
    serialized = format_blocked_resources(resources) or "[]"
    row = db.get(MessagingConnectorKV, GLOBAL_BLOCKED_KV_KEY)
    if row is None:
        row = MessagingConnectorKV(key=GLOBAL_BLOCKED_KV_KEY, value=serialized)
        db.add(row)
    else:
        row.value = serialized
        row.updated_at = utcnow()
    auth._record(db, admin_user, "admin_global_governance")
    db.commit()
    return parse_blocked_resources(serialized)


def effective_blocked_resources(db: Session, user: User) -> list[str]:
    """Admins nunca têm bloqueios; usuários comuns somam conta + regras globais."""
    if auth.is_admin(user):
        return []
    user_blocked = parse_blocked_resources(getattr(user, "blocked_resources", None))
    global_blocked = get_global_blocked_resources(db)
    out = list(user_blocked)
    for item in global_blocked:
        if item not in out:
            out.append(item)
    return out


def assert_resource_allowed(db: Session, user: User, resource_id: str) -> None:
    """Lança 403 se a solução ou funcionalidade estiver bloqueada para o usuário atual."""
    blocked = effective_blocked_resources(db, user)
    if resource_id in blocked:
        label = next(
            (
                item["label"]
                for item in (*CONTROLLABLE_SOLUTIONS, *CONTROLLABLE_FEATURES)
                if item["id"] == resource_id
            ),
            resource_id,
        )
        raise AppError(
            403,
            "resource_blocked",
            f"O acesso a '{label}' está bloqueado pelo administrador para a sua conta.",
        )


def governance_summary(db: Session) -> dict[str, Any]:
    return {
        "solutions": CONTROLLABLE_SOLUTIONS,
        "features": CONTROLLABLE_FEATURES,
        "global_blocked_resources": get_global_blocked_resources(db),
    }


def _snapshot_size_bytes(rows_json: Any) -> int:
    return len(json.dumps(rows_json or [], ensure_ascii=False, default=str).encode("utf-8"))


def user_storage_map(db: Session) -> dict[uuid.UUID, int]:
    """Soma o uso em bytes (arquivos, Cofre, mídias WhatsApp e snapshots CRM)."""
    stored = dict(
        db.execute(
            select(StoredFile.owner_id, func.coalesce(func.sum(StoredFile.size), 0)).group_by(
                StoredFile.owner_id
            )
        ).all()
    )
    vault = dict(
        db.execute(
            select(
                VaultDocument.user_id, func.coalesce(func.sum(VaultDocument.size_bytes), 0)
            ).group_by(VaultDocument.user_id)
        ).all()
    )
    totals: dict[uuid.UUID, int] = {}
    for uid, size in stored.items():
        totals[uid] = totals.get(uid, 0) + int(size or 0)
    for uid, size in vault.items():
        totals[uid] = totals.get(uid, 0) + int(size or 0)
    for uid, rows_json in db.execute(
        select(DataSource.user_id, DataSnapshot.rows_json).join(
            DataSnapshot, DataSnapshot.source_id == DataSource.id
        )
    ).all():
        totals[uid] = totals.get(uid, 0) + _snapshot_size_bytes(rows_json)
    return totals


def messaging_media_map(db: Session) -> dict[uuid.UUID, int]:
    """Espaço das mídias da Mensageria por conta (temporárias, fora da cota de arquivos)."""
    rows = db.execute(
        select(
            MessagingMedia.user_id, func.coalesce(func.sum(MessagingMedia.size_bytes), 0)
        ).group_by(MessagingMedia.user_id)
    ).all()
    return {uid: int(size or 0) for uid, size in rows}


def user_storage_bytes(db: Session, user_id: uuid.UUID) -> int:
    """Arquivos permanentes da conta (comprovantes, anexos, Cofre e dados do CRM).

    As mídias da Mensageria ficam de fora: são temporárias e têm teto próprio.
    """
    stored = int(
        db.scalar(
            select(func.coalesce(func.sum(StoredFile.size), 0)).where(
                StoredFile.owner_id == user_id
            )
        )
        or 0
    )
    vault = int(
        db.scalar(
            select(func.coalesce(func.sum(VaultDocument.size_bytes), 0)).where(
                VaultDocument.user_id == user_id
            )
        )
        or 0
    )
    snaps = db.scalars(
        select(DataSnapshot.rows_json)
        .join(DataSource, DataSnapshot.source_id == DataSource.id)
        .where(DataSource.user_id == user_id)
    ).all()
    snapshots = sum(_snapshot_size_bytes(r) for r in snaps)
    return stored + vault + snapshots


def assert_storage_quota(db: Session, user: User, incoming_bytes: int) -> None:
    """Impede que usuários comuns ultrapassem a cota de armazenamento definida pelo admin."""
    if auth.is_admin(user):
        return
    quota_mb = int(
        getattr(user, "storage_quota_mb", DEFAULT_STORAGE_QUOTA_MB) or DEFAULT_STORAGE_QUOTA_MB
    )
    quota_bytes = quota_mb * 1024 * 1024
    used = user_storage_bytes(db, user.id)
    if used + max(0, int(incoming_bytes)) > quota_bytes:
        raise AppError(
            413,
            "quota_exceeded",
            f"Sua conta atingiu a cota de {quota_mb} MB definida pelo administrador.",
        )


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
        "feedback_new": count(
            select(func.count())
            .select_from(SupportThread)
            .join(User, User.id == SupportThread.user_id)
            .where(SupportThread.admin_unread.is_(True))
        ),
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
    users = list(db.scalars(select(User).order_by(User.created_at.desc())))
    from app.services import files

    avatars = files.latest_ids(db, [u.id for u in users], "avatar")
    storage_map = user_storage_map(db)
    media_map = messaging_media_map(db)
    return [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "avatar_id": avatars.get(u.id),
            "created_at": u.created_at,
            "email_verified": u.email_verified,
            "access_status": u.access_status,
            "approved_at": u.approved_at,
            "is_admin": auth.is_admin(u),
            "totp_enabled": u.totp_enabled,
            "last_seen_at": last_seen.get(u.id),
            "active_sessions": sessions.get(u.id, 0),
            "entries": expenses.get(u.id, 0) + incomes.get(u.id, 0),
            "blocked_resources": parse_blocked_resources(getattr(u, "blocked_resources", None)),
            "storage_quota_mb": getattr(u, "storage_quota_mb", DEFAULT_STORAGE_QUOTA_MB)
            or DEFAULT_STORAGE_QUOTA_MB,
            "storage_used_bytes": storage_map.get(u.id, 0),
            "messaging_used_bytes": media_map.get(u.id, 0),
        }
        for u in users
    ]


def update_user_permissions(
    db: Session,
    admin_user: User,
    user_id: uuid.UUID,
    *,
    blocked_resources: list[str] | None = None,
    storage_quota_mb: int | None = None,
) -> dict[str, Any]:
    user = _get(db, user_id)
    if user.id == admin_user.id and blocked_resources:
        raise AppError(
            400,
            "self_action",
            "Não é permitido bloquear soluções ou recursos na sua própria conta de administrador.",
        )
    if blocked_resources is not None:
        user.blocked_resources = format_blocked_resources(blocked_resources)
    if storage_quota_mb is not None:
        clamped = max(MIN_STORAGE_QUOTA_MB, min(MAX_STORAGE_QUOTA_MB, int(storage_quota_mb)))
        user.storage_quota_mb = clamped
    auth._record(db, user, "admin_permissions")
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.id,
        "blocked_resources": parse_blocked_resources(user.blocked_resources),
        "storage_quota_mb": user.storage_quota_mb or DEFAULT_STORAGE_QUOTA_MB,
    }


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
