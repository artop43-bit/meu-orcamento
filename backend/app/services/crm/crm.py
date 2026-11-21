"""Serviços de CRM: funis, etapas, contatos, negócios, atividades e importação direta."""

from __future__ import annotations

import threading
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.money import MONEY_RANGE_MESSAGE
from app.db.types import utcnow
from app.models import CrmActivity, CrmContact, CrmDeal, CrmPipeline, CrmStage, MessagingChat
from app.services.common import get_owned
from app.services.crm.parsing import (
    format_phone_display,
    normalize_phone,
    parse_date,
    parse_money,
)

DEFAULT_STAGES = [
    ("Novo lead", False, False),
    ("Contato feito", False, False),
    ("Proposta enviada", False, False),
    ("Negociação", False, False),
    ("Ganho", True, False),
    ("Perdido", False, True),
]


MAX_CONTACT_IMPORT_ROWS = 2000
MAX_DEAL_IMPORT_ROWS = 1000
_PIPELINE_LOCK = threading.Lock()


def ensure_default_pipeline(db: Session, user_id: uuid.UUID) -> tuple[CrmPipeline, list[CrmStage]]:
    with _PIPELINE_LOCK:
        pipeline = db.scalar(
            select(CrmPipeline).where(
                CrmPipeline.user_id == user_id, CrmPipeline.is_default.is_(True)
            )
        )
        if pipeline is None:
            pipeline = db.scalar(select(CrmPipeline).where(CrmPipeline.user_id == user_id))
        if pipeline is None:
            pipeline = CrmPipeline(user_id=user_id, name="Funil principal", is_default=True)
            db.add(pipeline)
            db.flush()
            stages: list[CrmStage] = []
            for idx, (name, is_won, is_lost) in enumerate(DEFAULT_STAGES):
                stage = CrmStage(
                    pipeline_id=pipeline.id,
                    name=name,
                    position=idx,
                    is_won=is_won,
                    is_lost=is_lost,
                )
                db.add(stage)
                stages.append(stage)
            db.commit()
            db.refresh(pipeline)
            for s in stages:
                db.refresh(s)
            return pipeline, stages

    stages = list(
        db.scalars(
            select(CrmStage)
            .where(CrmStage.pipeline_id == pipeline.id)
            .order_by(CrmStage.position.asc())
        ).all()
    )
    return pipeline, stages


def get_pipeline_board(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    pipeline, stages = ensure_default_pipeline(db, user_id)
    deals = list(
        db.scalars(
            select(CrmDeal)
            .where(CrmDeal.user_id == user_id, CrmDeal.pipeline_id == pipeline.id)
            .order_by(CrmDeal.position.asc(), CrmDeal.created_at.desc())
        ).all()
    )
    contact_ids = {d.contact_id for d in deals if d.contact_id}
    contacts_map: dict[uuid.UUID, CrmContact] = {}
    if contact_ids:
        for c in db.scalars(
            select(CrmContact).where(CrmContact.id.in_(contact_ids), CrmContact.user_id == user_id)
        ).all():
            contacts_map[c.id] = c

    deals_by_stage: dict[uuid.UUID, list[dict[str, Any]]] = {s.id: [] for s in stages}
    for d in deals:
        contact = contacts_map.get(d.contact_id) if d.contact_id else None
        deals_by_stage.setdefault(d.stage_id, []).append(serialize_deal(d, contact=contact))

    stage_list = []
    open_total = Decimal("0")
    won_total = Decimal("0")
    for s in stages:
        items = deals_by_stage.get(s.id, [])
        stage_total = sum((Decimal(str(i["value"])) for i in items), Decimal("0"))
        if s.is_won:
            won_total += stage_total
        elif not s.is_lost:
            open_total += stage_total
        stage_list.append(
            {
                "id": s.id,
                "name": s.name,
                "position": s.position,
                "is_won": s.is_won,
                "is_lost": s.is_lost,
                "total_value": stage_total,
                "deals": items,
            }
        )

    return {
        "pipeline": {"id": pipeline.id, "name": pipeline.name},
        "stages": stage_list,
        "summary": {
            "total_deals": len(deals),
            "open_value": open_total,
            "won_value": won_total,
        },
    }


def serialize_contact(c: CrmContact) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "phone_display": format_phone_display(c.phone) if c.phone else None,
        "remote_jid": c.remote_jid,
        "email": c.email,
        "company": c.company,
        "origin": c.origin,
        "tags": list(c.tags or []),
        "notes": c.notes,
        "messaging_chat_id": c.messaging_chat_id,
        "budget_person": c.budget_person,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def serialize_deal(d: CrmDeal, *, contact: CrmContact | None = None) -> dict[str, Any]:
    return {
        "id": d.id,
        "pipeline_id": d.pipeline_id,
        "stage_id": d.stage_id,
        "contact_id": d.contact_id,
        "contact_name": contact.name if contact else None,
        "contact_phone": format_phone_display(contact.phone) if contact and contact.phone else None,
        "contact_messaging_chat_id": contact.messaging_chat_id if contact else None,
        "title": d.title,
        "value": d.value,
        "status": d.status,
        "expected_close_date": d.expected_close_date,
        "budget_income_id": d.budget_income_id,
        "notes": d.notes,
        "position": d.position,
        "closed_at": d.closed_at,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


# ---------------------------------------------------------------- contatos


def _validate_messaging_chat(
    db: Session, user_id: uuid.UUID, chat_id: uuid.UUID | None
) -> uuid.UUID | None:
    if chat_id is None:
        return None
    exists = db.scalar(
        select(MessagingChat.id).where(
            MessagingChat.id == chat_id, MessagingChat.user_id == user_id
        )
    )
    if exists is None:
        raise AppError(404, "chat_not_found", "Conversa da Mensageria não encontrada.")
    return exists


def list_contacts(db: Session, user_id: uuid.UUID, q: str | None = None) -> list[dict[str, Any]]:
    stmt = select(CrmContact).where(CrmContact.user_id == user_id)
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                CrmContact.name.ilike(like),
                CrmContact.company.ilike(like),
                CrmContact.email.ilike(like),
                CrmContact.phone.ilike(like),
                CrmContact.budget_person.ilike(like),
            )
        )
    stmt = stmt.order_by(CrmContact.updated_at.desc(), CrmContact.name.asc())
    return [serialize_contact(c) for c in db.scalars(stmt).all()]


def get_contact(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID) -> CrmContact:
    return get_owned(
        db,
        CrmContact,
        user_id,
        contact_id,
        error_code="contact_not_found",
        error_msg="Contato não encontrado.",
    )


def create_contact(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()[:120]
    if not name:
        raise AppError(400, "invalid_name", "Informe o nome do contato.")
    phone_raw = data.get("phone")
    phone_norm = normalize_phone(str(phone_raw)) if phone_raw else None
    chat_id = _validate_messaging_chat(db, user_id, data.get("messaging_chat_id"))
    contact = CrmContact(
        user_id=user_id,
        name=name,
        phone=phone_norm[0] if phone_norm else None,
        remote_jid=phone_norm[1] if phone_norm else None,
        email=(str(data.get("email") or "").strip().lower()[:160] or None),
        company=(str(data.get("company") or "").strip()[:120] or None),
        origin=(str(data.get("origin") or "").strip()[:60] or "Manual"),
        tags=[str(t).strip()[:30] for t in (data.get("tags") or []) if str(t).strip()][:10],
        notes=(str(data.get("notes") or "").strip() or None),
        messaging_chat_id=chat_id,
        budget_person=(str(data.get("budget_person") or "").strip()[:80] or None),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return serialize_contact(contact)


def update_contact(
    db: Session, user_id: uuid.UUID, contact_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    contact = get_contact(db, user_id, contact_id)
    if "name" in changes and changes["name"] is not None:
        clean = str(changes["name"]).strip()[:120]
        if not clean:
            raise AppError(400, "invalid_name", "Informe o nome do contato.")
        contact.name = clean
    if "phone" in changes:
        norm = normalize_phone(str(changes["phone"])) if changes["phone"] else None
        contact.phone = norm[0] if norm else None
        contact.remote_jid = norm[1] if norm else None
    for field_name, limit in (
        ("email", 160),
        ("company", 120),
        ("origin", 60),
        ("budget_person", 80),
    ):
        if field_name in changes:
            val = changes[field_name]
            setattr(contact, field_name, (str(val).strip()[:limit] or None) if val else None)
    if "notes" in changes:
        contact.notes = (str(changes["notes"]).strip() or None) if changes["notes"] else None
    if "tags" in changes and changes["tags"] is not None:
        contact.tags = [str(t).strip()[:30] for t in changes["tags"] if str(t).strip()][:10]
    if "messaging_chat_id" in changes:
        contact.messaging_chat_id = _validate_messaging_chat(
            db, user_id, changes["messaging_chat_id"]
        )
    contact.updated_at = utcnow()
    db.commit()
    db.refresh(contact)
    return serialize_contact(contact)


def delete_contact(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    contact = get_contact(db, user_id, contact_id)
    db.execute(update(CrmDeal).where(CrmDeal.contact_id == contact.id).values(contact_id=None))
    db.execute(delete(CrmActivity).where(CrmActivity.contact_id == contact.id))
    db.delete(contact)
    db.commit()


# ---------------------------------------------------------------- negócios


def get_deal(db: Session, user_id: uuid.UUID, deal_id: uuid.UUID) -> CrmDeal:
    return get_owned(
        db,
        CrmDeal,
        user_id,
        deal_id,
        error_code="deal_not_found",
        error_msg="Negócio não encontrado.",
    )


def create_deal(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    pipeline, stages = ensure_default_pipeline(db, user_id)
    title = str(data.get("title") or "").strip()[:140]
    if not title:
        raise AppError(400, "invalid_title", "Informe o título do negócio.")

    stage_id = data.get("stage_id") or stages[0].id
    stage = db.scalar(
        select(CrmStage).where(CrmStage.id == stage_id, CrmStage.pipeline_id == pipeline.id)
    )
    if stage is None:
        raise AppError(404, "stage_not_found", "Etapa do funil não encontrada.")

    contact: CrmContact | None = None
    if data.get("contact_id"):
        contact = get_contact(db, user_id, data["contact_id"])

    status = "won" if stage.is_won else ("lost" if stage.is_lost else "open")
    raw_value = data.get("value", Decimal("0"))
    val = parse_money(raw_value)
    if val is None:
        raise AppError(400, "invalid_value", MONEY_RANGE_MESSAGE)
    deal = CrmDeal(
        user_id=user_id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        contact_id=contact.id if contact else None,
        title=title,
        value=val,
        status=status,
        expected_close_date=data.get("expected_close_date"),
        notes=(str(data.get("notes") or "").strip() or None),
        closed_at=utcnow() if status in {"won", "lost"} else None,
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return serialize_deal(deal, contact=contact)


def update_deal(
    db: Session, user_id: uuid.UUID, deal_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    deal = get_deal(db, user_id, deal_id)
    if "title" in changes and changes["title"] is not None:
        clean = str(changes["title"]).strip()[:140]
        if not clean:
            raise AppError(400, "invalid_title", "Informe o título do negócio.")
        deal.title = clean
    if "value" in changes and changes["value"] is not None:
        num = parse_money(changes["value"])
        if num is None:
            raise AppError(400, "invalid_value", MONEY_RANGE_MESSAGE)
        deal.value = num
    if "stage_id" in changes and changes["stage_id"] is not None:
        stage = db.scalar(
            select(CrmStage).where(
                CrmStage.id == changes["stage_id"], CrmStage.pipeline_id == deal.pipeline_id
            )
        )
        if stage is None:
            raise AppError(404, "stage_not_found", "Etapa do funil não encontrada.")
        deal.stage_id = stage.id
        deal.status = "won" if stage.is_won else ("lost" if stage.is_lost else "open")
        deal.closed_at = utcnow() if deal.status in {"won", "lost"} else None
    if "contact_id" in changes:
        if changes["contact_id"] is None:
            deal.contact_id = None
        else:
            contact = get_contact(db, user_id, changes["contact_id"])
            deal.contact_id = contact.id
    if "expected_close_date" in changes:
        deal.expected_close_date = changes["expected_close_date"]
    if "notes" in changes:
        deal.notes = (str(changes["notes"]).strip() or None) if changes["notes"] else None

    deal.updated_at = utcnow()
    db.commit()
    db.refresh(deal)
    contact = get_contact(db, user_id, deal.contact_id) if deal.contact_id else None
    return serialize_deal(deal, contact=contact)


def delete_deal(db: Session, user_id: uuid.UUID, deal_id: uuid.UUID) -> None:
    deal = get_deal(db, user_id, deal_id)
    db.execute(delete(CrmActivity).where(CrmActivity.deal_id == deal.id))
    db.delete(deal)
    db.commit()


# ---------------------------------------------------------------- atividades


def list_activities(
    db: Session,
    user_id: uuid.UUID,
    *,
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
) -> list[CrmActivity]:
    stmt = select(CrmActivity).where(CrmActivity.user_id == user_id)
    if contact_id is not None:
        stmt = stmt.where(CrmActivity.contact_id == contact_id)
    if deal_id is not None:
        stmt = stmt.where(CrmActivity.deal_id == deal_id)
    stmt = stmt.order_by(CrmActivity.created_at.desc()).limit(100)
    return list(db.scalars(stmt).all())


def create_activity(
    db: Session,
    user_id: uuid.UUID,
    *,
    body: str,
    kind: str = "note",
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    due_at: datetime | None = None,
) -> CrmActivity:
    text = (body or "").strip()
    if not text:
        raise AppError(400, "empty_activity", "Escreva os detalhes da atividade.")
    if contact_id is not None:
        get_contact(db, user_id, contact_id)
    if deal_id is not None:
        deal = get_deal(db, user_id, deal_id)
        if contact_id is None:
            contact_id = deal.contact_id
    act = CrmActivity(
        user_id=user_id,
        contact_id=contact_id,
        deal_id=deal_id,
        kind=kind,
        body=text,
        due_at=due_at,
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def toggle_activity_done(
    db: Session, user_id: uuid.UUID, activity_id: uuid.UUID, done: bool
) -> CrmActivity:
    act = db.scalar(
        select(CrmActivity).where(CrmActivity.id == activity_id, CrmActivity.user_id == user_id)
    )
    if act is None:
        raise AppError(404, "activity_not_found", "Atividade não encontrada.")
    act.done_at = utcnow() if done else None
    db.commit()
    db.refresh(act)
    return act


# ---------------------------------------------------------------- importação de PDF/CSV para CRM


def import_rows_to_contacts(
    db: Session,
    user_id: uuid.UUID,
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    origin: str = "Importação",
) -> dict[str, int]:
    name_col = mapping.get("name")
    if not name_col:
        raise AppError(
            400, "missing_mapping", "Selecione qual coluna representa o nome do contato."
        )

    existing_by_jid = {
        c.remote_jid: c
        for c in db.scalars(
            select(CrmContact).where(
                CrmContact.user_id == user_id, CrmContact.remote_jid.is_not(None)
            )
        ).all()
        if c.remote_jid
    }
    existing_by_email = {
        c.email.lower(): c
        for c in db.scalars(
            select(CrmContact).where(CrmContact.user_id == user_id, CrmContact.email.is_not(None))
        ).all()
        if c.email
    }

    created = 0
    updated = 0
    skipped = max(0, len(rows) - MAX_CONTACT_IMPORT_ROWS)

    for row in rows[:MAX_CONTACT_IMPORT_ROWS]:
        raw_name = str(row.get(name_col) or "").strip()
        if not raw_name:
            skipped += 1
            continue
        phone_norm = (
            normalize_phone(str(row.get(mapping["phone"]) or "")) if mapping.get("phone") else None
        )
        email = (
            str(row.get(mapping["email"]) or "").strip().lower()[:160] or None
            if mapping.get("email")
            else None
        )
        company = (
            str(row.get(mapping["company"]) or "").strip()[:120] or None
            if mapping.get("company")
            else None
        )
        notes = (
            str(row.get(mapping["notes"]) or "").strip() or None if mapping.get("notes") else None
        )

        match = None
        if phone_norm and phone_norm[1] in existing_by_jid:
            match = existing_by_jid[phone_norm[1]]
        elif email and email in existing_by_email:
            match = existing_by_email[email]

        if match is not None:
            match.name = raw_name[:120]
            if company:
                match.company = company
            if notes:
                match.notes = notes
            match.updated_at = utcnow()
            updated += 1
        else:
            c = CrmContact(
                user_id=user_id,
                name=raw_name[:120],
                phone=phone_norm[0] if phone_norm else None,
                remote_jid=phone_norm[1] if phone_norm else None,
                email=email,
                company=company,
                origin=origin[:60],
                notes=notes,
            )
            db.add(c)
            if phone_norm:
                existing_by_jid[phone_norm[1]] = c
            if email:
                existing_by_email[email] = c
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def import_rows_to_deals(
    db: Session,
    user_id: uuid.UUID,
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    origin: str = "Importação",
) -> dict[str, int]:
    title_col = mapping.get("title")
    if not title_col:
        raise AppError(
            400, "missing_mapping", "Selecione qual coluna representa o título do negócio."
        )

    pipeline, stages = ensure_default_pipeline(db, user_id)
    first_stage = stages[0]
    contacts_by_name = {
        c.name.strip().lower(): c
        for c in db.scalars(select(CrmContact).where(CrmContact.user_id == user_id)).all()
    }

    created = 0
    skipped = max(0, len(rows) - MAX_DEAL_IMPORT_ROWS)
    for row in rows[:MAX_DEAL_IMPORT_ROWS]:
        title = str(row.get(title_col) or "").strip()
        if not title:
            skipped += 1
            continue
        val_raw = row.get(mapping["value"]) if mapping.get("value") else 0
        val = parse_money(val_raw)
        if val is None:
            skipped += 1
            continue
        close_iso = (
            parse_date(row.get(mapping["expected_close_date"]))
            if mapping.get("expected_close_date")
            else None
        )
        close_date = date.fromisoformat(close_iso) if close_iso else None
        notes = (
            str(row.get(mapping["notes"]) or "").strip() or None if mapping.get("notes") else None
        )

        contact_id = None
        if mapping.get("contact_name"):
            cname = str(row.get(mapping["contact_name"]) or "").strip()
            if cname:
                existing = contacts_by_name.get(cname.lower())
                if existing is None:
                    existing = CrmContact(
                        user_id=user_id,
                        name=cname[:120],
                        origin=origin[:60],
                    )
                    db.add(existing)
                    db.flush()
                    contacts_by_name[cname.lower()] = existing
                contact_id = existing.id

        db.add(
            CrmDeal(
                user_id=user_id,
                pipeline_id=pipeline.id,
                stage_id=first_stage.id,
                contact_id=contact_id,
                title=title[:140],
                value=val,
                status="open",
                expected_close_date=close_date,
                notes=notes,
            )
        )
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped}
