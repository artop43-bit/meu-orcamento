"""Pontes compartilhadas da Fase D respeitando isolamento `user_id` e bloqueios do `/admin`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CommercialDocument,
    CrmContact,
    CrmDeal,
    Goal,
    MessagingChat,
    User,
    VaultDocument,
    WorkProject,
)
from app.services import admin as admin_service
from app.services.common import get_owned

_LINK_CHECKS: tuple[tuple[str, type[Any], str, str], ...] = (
    ("contact_id", CrmContact, "contact_not_found", "Contato do CRM não encontrado."),
    ("deal_id", CrmDeal, "deal_not_found", "Negócio do CRM não encontrado."),
    ("project_id", WorkProject, "project_not_found", "Projeto não encontrado."),
    ("proposal_id", CommercialDocument, "document_not_found", "Proposta não encontrada."),
    ("messaging_chat_id", MessagingChat, "chat_not_found", "Conversa não encontrada."),
    ("goal_id", Goal, "goal_not_found", "Meta não encontrada."),
    ("vault_doc_id", VaultDocument, "vault_doc_not_found", "Documento do Cofre não encontrado."),
)


def validate_hub_links(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> None:
    """Confere propriedade de todos os vínculos opcionais com soluções do Hub."""
    for field, model, err_code, err_msg in _LINK_CHECKS:
        val = data.get(field)
        if val is not None:
            get_owned(db, model, user_id, val, error_code=err_code, error_msg=err_msg)


def list_memory_bridges(
    db: Session,
    user: User,
    *,
    include_proposals: bool = False,
    include_notebook_extras: bool = False,
) -> dict[str, Any]:
    """Lista contatos, negócios, projetos e itens ligados sem vazar módulos bloqueados."""
    blocked = admin_service.effective_blocked_resources(db, user)
    crm_ok = "dashboard-crm" not in blocked
    contacts = (
        [
            {"id": c.id, "name": c.name}
            for c in db.scalars(
                select(CrmContact)
                .where(CrmContact.user_id == user.id)
                .order_by(CrmContact.name.asc())
                .limit(100)
            ).all()
        ]
        if crm_ok
        else []
    )
    deals = (
        [
            {"id": d.id, "title": d.title, "status": d.status}
            for d in db.scalars(
                select(CrmDeal)
                .where(CrmDeal.user_id == user.id)
                .order_by(CrmDeal.updated_at.desc())
                .limit(60)
            ).all()
        ]
        if crm_ok
        else []
    )
    projects = (
        [
            {"id": p.id, "name": p.name, "status": p.status}
            for p in db.scalars(
                select(WorkProject)
                .where(WorkProject.user_id == user.id)
                .order_by(WorkProject.updated_at.desc())
                .limit(60)
            ).all()
        ]
        if "projetos" not in blocked
        else []
    )
    out: dict[str, Any] = {
        "contacts": contacts,
        "deals": deals,
        "projects": projects,
    }
    if include_proposals:
        out["proposals"] = (
            [
                {"id": doc.id, "title": doc.title, "number": doc.number}
                for doc in db.scalars(
                    select(CommercialDocument)
                    .where(CommercialDocument.user_id == user.id)
                    .order_by(CommercialDocument.number.desc())
                    .limit(60)
                ).all()
            ]
            if "propostas" not in blocked
            else []
        )
    if include_notebook_extras:
        out["chats"] = (
            [
                {"id": ch.id, "name": ch.name}
                for ch in db.scalars(
                    select(MessagingChat)
                    .where(
                        MessagingChat.user_id == user.id,
                        MessagingChat.archived.is_(False),
                    )
                    .order_by(MessagingChat.name.asc())
                    .limit(80)
                ).all()
            ]
            if "mensageria" not in blocked
            else []
        )
        out["goals"] = (
            [
                {"id": g.id, "name": g.name}
                for g in db.scalars(
                    select(Goal).where(Goal.user_id == user.id).order_by(Goal.name.asc()).limit(60)
                ).all()
            ]
            if "meu-orcamento" not in blocked
            else []
        )
        out["vault_docs"] = (
            [
                {"id": v.id, "title": v.title, "category": v.category}
                for v in db.scalars(
                    select(VaultDocument)
                    .where(VaultDocument.user_id == user.id)
                    .order_by(VaultDocument.created_at.desc())
                    .limit(60)
                ).all()
            ]
            if "cofre" not in blocked
            else []
        )
    return out
