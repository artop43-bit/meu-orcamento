"""Ponte 360° da Mensageria com o Dashboard & CRM (contatos e negócios no funil)."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrmActivity, CrmContact, CrmDeal, User
from app.services.crm import crm as crm_service
from app.services.crm import hub_bridge
from app.services.messaging.chats import get_chat


def chat_crm_context(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
) -> dict[str, Any]:
    """Lê o contato e os negócios vinculados no Dashboard & CRM para esta conversa."""
    chat = get_chat(db, user, chat_id)
    _, stages = crm_service.ensure_default_pipeline(db, user.id)
    stage_map = {s.id: s for s in stages}

    contact = db.scalar(
        select(CrmContact).where(
            CrmContact.user_id == user.id,
            CrmContact.messaging_chat_id == chat.id,
        )
    )
    if contact is None and chat.phone:
        contact = db.scalar(
            select(CrmContact).where(
                CrmContact.user_id == user.id,
                CrmContact.phone == chat.phone,
            )
        )

    deals: list[dict[str, Any]] = []
    if contact is not None:
        raw_deals = list(
            db.scalars(
                select(CrmDeal)
                .where(CrmDeal.user_id == user.id, CrmDeal.contact_id == contact.id)
                .order_by(CrmDeal.updated_at.desc())
            ).all()
        )
        for d in raw_deals:
            st = stage_map.get(d.stage_id)
            deals.append(
                {
                    "id": d.id,
                    "title": d.title,
                    "value": d.value,
                    "status": d.status,
                    "stage_id": d.stage_id,
                    "stage_name": st.name if st else "Etapa",
                    "budget_income_id": d.budget_income_id,
                }
            )

    return {
        "contact": crm_service.serialize_contact(contact) if contact else None,
        "deals": deals,
        "stages": [
            {
                "id": s.id,
                "name": s.name,
                "position": s.position,
                "is_won": s.is_won,
                "is_lost": s.is_lost,
            }
            for s in stages
        ],
    }


def create_chat_crm_deal(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    title: str,
    value: Decimal,
    stage_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Garante o contato da conversa no CRM e cria um negócio no Funil principal."""
    contact, _ = hub_bridge.import_contact_from_messaging(db, user, chat_id)
    deal = crm_service.create_deal(
        db,
        user.id,
        {
            "title": title,
            "value": value,
            "stage_id": stage_id,
            "contact_id": contact.id,
            "notes": notes,
        },
    )
    db.add(
        CrmActivity(
            user_id=user.id,
            deal_id=deal["id"],
            contact_id=contact.id,
            kind="whatsapp",
            body=f"Negócio criado diretamente pela conversa da Mensageria ({title}).",
        )
    )
    db.commit()
    ctx = chat_crm_context(db, user, chat_id)
    return {**ctx, "deal": deal}
