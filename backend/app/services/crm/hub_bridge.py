"""Ponte nativa do Dashboard & CRM com Mensageria (/mensageria) e Meu Orçamento (/orcamento)."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.money import brl
from app.core.months import current_month, today_local
from app.db.types import utcnow
from app.models import (
    Category,
    CrmActivity,
    CrmContact,
    CrmDeal,
    CrmPipeline,
    CrmStage,
    Expense,
    Income,
    MessagingChat,
    MessagingMessage,
    User,
)
from app.services import budget as budget_service
from app.services.common import row_lock_guard
from app.services.crm.parsing import format_phone_display


def _local_date(moment: datetime) -> date:
    """Data no fuso do Hub (America/Sao_Paulo): 01:30 UTC ainda é o dia anterior aqui."""
    return moment.astimezone(ZoneInfo(get_settings().timezone)).date()


def list_messaging_chats_for_link(db: Session, user: User) -> list[dict[str, Any]]:
    chats = list(
        db.scalars(
            select(MessagingChat)
            .where(MessagingChat.user_id == user.id, MessagingChat.archived.is_(False))
            .order_by(MessagingChat.last_message_at.desc().nullslast(), MessagingChat.name.asc())
            .limit(100)
        ).all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "phone_display": format_phone_display(c.phone) if c.phone else "",
            "budget_person": c.budget_person,
        }
        for c in chats
    ]


def import_contact_from_messaging(
    db: Session, user: User, chat_id: uuid.UUID
) -> tuple[CrmContact, bool]:
    """Cria ou vincula um contato do CRM a partir de uma conversa real da Mensageria."""
    chat = db.scalar(
        select(MessagingChat).where(MessagingChat.id == chat_id, MessagingChat.user_id == user.id)
    )
    if chat is None:
        raise AppError(404, "chat_not_found", "Conversa da Mensageria não encontrada.")

    existing = db.scalar(
        select(CrmContact).where(
            CrmContact.user_id == user.id,
            CrmContact.messaging_chat_id == chat.id,
        )
    )
    if existing is None and chat.remote_jid:
        existing = db.scalar(
            select(CrmContact).where(
                CrmContact.user_id == user.id,
                CrmContact.remote_jid == chat.remote_jid,
            )
        )
    if existing is not None:
        changed = False
        if existing.messaging_chat_id != chat.id:
            existing.messaging_chat_id = chat.id
            changed = True
        if not existing.phone and chat.phone:
            existing.phone = chat.phone
            changed = True
        if not existing.budget_person and chat.budget_person:
            existing.budget_person = chat.budget_person
            changed = True
        if changed:
            existing.updated_at = utcnow()
            db.commit()
            db.refresh(existing)
        return existing, False

    contact = CrmContact(
        user_id=user.id,
        name=chat.name[:120],
        phone=chat.phone,
        remote_jid=chat.remote_jid,
        origin="Mensageria",
        tags=[],
        notes=chat.notes,
        messaging_chat_id=chat.id,
        budget_person=chat.budget_person,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact, True


def sync_won_deal_to_budget(
    db: Session,
    user: User,
    deal: CrmDeal,
) -> dict[str, Any]:
    """Lança de verdade a receita de um negócio ganho no Meu Orçamento (idempotente)."""
    with row_lock_guard(db):
        return _sync_won_deal_to_budget_locked(db, user, deal)


def _sync_won_deal_to_budget_locked(
    db: Session,
    user: User,
    deal: CrmDeal,
) -> dict[str, Any]:
    target_date = today_local()
    target_month = current_month(user.month_start_day)

    deal = db.scalar(
        select(CrmDeal)
        .where(CrmDeal.id == deal.id, CrmDeal.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if deal is None:
        raise AppError(404, "deal_not_found", "Negócio não encontrado.")
    if deal.status != "won":
        raise AppError(
            409, "deal_not_won", "Marque o negócio como Ganho antes de enviar a receita."
        )
    if deal.value is None or not deal.value.is_finite() or deal.value <= 0:
        raise AppError(
            400, "invalid_deal_value", "Informe um valor maior que zero para lançar no Orçamento."
        )

    if deal.budget_income_id is None:
        budget_service.ensure_month(db, user, target_month, commit=False)
        safe_day = min(
            target_date.day, calendar.monthrange(target_month.year, target_month.month)[1]
        )
        income = budget_service.create_income(
            db,
            user,
            target_month,
            {
                "description": f"CRM: {deal.title}"[:120],
                "amount": deal.value,
                "income_type": "variable",
                "day": safe_day,
                "notes": "Receita gerada pelo Dashboard & CRM.",
            },
            commit=False,
        )
        deal.budget_income_id = income.id
        deal.updated_at = utcnow()
        db.add(
            CrmActivity(
                user_id=user.id,
                contact_id=deal.contact_id,
                deal_id=deal.id,
                kind="budget",
                body=f"Receita de {brl(deal.value)} lançada no Meu Orçamento.",
            )
        )
        db.commit()
        db.refresh(deal)

    return {
        "deal_id": deal.id,
        "budget_income_id": deal.budget_income_id,
        "amount": deal.value,
        "description": f"CRM: {deal.title}"[:120],
    }


def native_crm_deals_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Conjunto tabular vivo dos negócios do CRM."""
    stages = {
        s.id: s
        for s in db.scalars(
            select(CrmStage).join(CrmPipeline).where(CrmPipeline.user_id == user_id)
        ).all()
    }
    contacts = {
        c.id: c for c in db.scalars(select(CrmContact).where(CrmContact.user_id == user_id)).all()
    }
    deals = list(
        db.scalars(
            select(CrmDeal).where(CrmDeal.user_id == user_id).order_by(CrmDeal.created_at.desc())
        ).all()
    )
    schema = [
        {"name": "titulo", "label": "Negócio", "type": "text"},
        {"name": "etapa", "label": "Etapa", "type": "text"},
        {"name": "status", "label": "Status", "type": "text"},
        {"name": "valor", "label": "Valor", "type": "currency"},
        {"name": "cliente", "label": "Cliente", "type": "text"},
        {"name": "origem", "label": "Origem", "type": "text"},
        {"name": "data", "label": "Data", "type": "date"},
    ]
    status_pt = {"open": "Em andamento", "won": "Ganho", "lost": "Perdido"}
    rows: list[dict[str, Any]] = []
    for deal in deals:
        stage = stages.get(deal.stage_id)
        contact = contacts.get(deal.contact_id) if deal.contact_id else None
        ref_date = (
            deal.expected_close_date.isoformat()
            if deal.expected_close_date
            else _local_date(deal.created_at).isoformat()
        )
        rows.append(
            {
                "titulo": deal.title,
                "etapa": stage.name if stage else "Sem etapa",
                "status": status_pt.get(deal.status, deal.status),
                "valor": float(deal.value or Decimal("0")),
                "cliente": contact.name if contact else "Sem contato",
                "origem": (contact.origin if contact and contact.origin else "Direto"),
                "data": ref_date,
            }
        )
    return schema, rows


def native_crm_contacts_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    contacts = list(
        db.scalars(
            select(CrmContact)
            .where(CrmContact.user_id == user_id)
            .order_by(CrmContact.created_at.desc())
        ).all()
    )
    schema = [
        {"name": "nome", "label": "Nome", "type": "text"},
        {"name": "empresa", "label": "Empresa", "type": "text"},
        {"name": "origem", "label": "Origem", "type": "text"},
        {"name": "whatsapp", "label": "WhatsApp", "type": "boolean"},
        {"name": "orcamento", "label": "No Orçamento", "type": "boolean"},
        {"name": "data", "label": "Cadastro", "type": "date"},
    ]
    rows = [
        {
            "nome": c.name,
            "empresa": c.company or "Pessoa física",
            "origem": c.origin or "Direto",
            "whatsapp": bool(c.phone or c.messaging_chat_id),
            "orcamento": bool(c.budget_person),
            "data": _local_date(c.created_at).isoformat(),
        }
        for c in contacts
    ]
    return schema, rows


def native_messaging_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Conjunto tabular vivo das mensagens da Mensageria (sem copiar dados)."""
    chats = {
        c.id: c
        for c in db.scalars(select(MessagingChat).where(MessagingChat.user_id == user_id)).all()
    }
    messages = list(
        db.scalars(
            select(MessagingMessage)
            .where(MessagingMessage.user_id == user_id)
            .order_by(MessagingMessage.created_at.desc())
        ).all()
    )
    schema = [
        {"name": "contato", "label": "Contato", "type": "text"},
        {"name": "direcao", "label": "Direção", "type": "text"},
        {"name": "tipo", "label": "Tipo", "type": "text"},
        {"name": "status", "label": "Status", "type": "text"},
        {"name": "data", "label": "Data", "type": "date"},
    ]
    type_pt = {
        "chat": "Texto",
        "image": "Foto",
        "audio": "Áudio",
        "video": "Vídeo",
        "document": "Documento",
        "sticker": "Figurinha",
        "other": "Outro",
    }
    rows = [
        {
            "contato": chats[m.chat_id].name if m.chat_id in chats else "Contato",
            "direcao": "Enviada" if m.direction == "out" else "Recebida",
            "tipo": type_pt.get(m.message_type, m.message_type),
            "status": m.status,
            "data": _local_date(m.created_at).isoformat(),
        }
        for m in messages
    ]
    return schema, rows


def native_budget_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Conjunto tabular vivo de receitas e despesas do Meu Orçamento."""
    cats = {
        c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user_id)).all()
    }
    incomes = list(
        db.scalars(
            select(Income)
            .where(Income.user_id == user_id)
            .order_by(Income.month.desc(), Income.created_at.desc())
        ).all()
    )
    expenses = list(
        db.scalars(
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(Expense.month.desc(), Expense.created_at.desc())
        ).all()
    )
    schema = [
        {"name": "tipo", "label": "Tipo", "type": "text"},
        {"name": "descricao", "label": "Descrição", "type": "text"},
        {"name": "categoria", "label": "Categoria", "type": "text"},
        {"name": "valor", "label": "Valor", "type": "currency"},
        {"name": "pago", "label": "Pago", "type": "boolean"},
        {"name": "data", "label": "Data", "type": "date"},
    ]
    rows: list[dict[str, Any]] = []
    for inc in incomes:
        day = min(max(inc.day or 1, 1), 28)
        ref = date(inc.month.year, inc.month.month, day).isoformat()
        rows.append(
            {
                "tipo": "Receita",
                "descricao": inc.description,
                "categoria": "Receitas",
                "valor": float(inc.amount or Decimal("0")),
                "pago": True,
                "data": ref,
            }
        )
    for exp in expenses:
        ref = (exp.due_date or exp.purchase_date or exp.month).isoformat()
        rows.append(
            {
                "tipo": "Despesa",
                "descricao": exp.description,
                "categoria": cats.get(exp.category_id, "Sem categoria")
                if exp.category_id
                else "Sem categoria",
                "valor": float(exp.amount or Decimal("0")),
                "pago": bool(exp.paid),
                "data": ref,
            }
        )
    rows.sort(key=lambda r: r["data"], reverse=True)
    return schema, rows


def native_catalog_dataset(
    db: Session, user_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Conjunto tabular vivo do Catálogo & Estoque para painéis do CRM."""
    from app.services.commerce.catalog import native_catalog_dataset as load_catalog_dataset

    return load_catalog_dataset(db, user_id)
