"""Serviços da Agenda Unificada 360°: eventos próprios + Mensageria + CRM + Projetos + Orçamento."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import (
    AgendaEvent,
    CrmContact,
    CrmDeal,
    MessagingChat,
    ProjectTask,
    User,
    WorkProject,
)
from app.services import admin as admin_service
from app.services import planned as planned_service
from app.services.memory import vault as vault_service
from app.services.messaging import messages as messaging_messages
from app.services.notify import brl

EVENT_KINDS = ("meeting", "delivery", "visit", "reminder", "personal")
EVENT_STATUSES = ("scheduled", "confirmed", "done", "cancelled")
ALL_LAYERS = ("agenda", "messaging", "crm", "projects", "budget", "cofre")


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def _to_local_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_tz())


def serialize_event(
    event: AgendaEvent,
    *,
    contact_name: str | None = None,
    project_name: str | None = None,
    chat_name: str | None = None,
) -> dict[str, Any]:
    local_start = _to_local_dt(event.start_at)
    return {
        "id": event.id,
        "title": event.title,
        "kind": event.kind,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "local_date": local_start.date().isoformat(),
        "local_time": None if event.all_day else local_start.strftime("%H:%M"),
        "all_day": bool(event.all_day),
        "location": event.location,
        "status": event.status,
        "contact_id": event.contact_id,
        "contact_name": contact_name,
        "project_id": event.project_id,
        "project_name": project_name,
        "messaging_chat_id": event.messaging_chat_id,
        "chat_name": chat_name,
        "notes": event.notes,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


def get_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> AgendaEvent:
    event = db.scalar(
        select(AgendaEvent).where(AgendaEvent.id == event_id, AgendaEvent.user_id == user_id)
    )
    if event is None:
        raise AppError(404, "event_not_found", "Compromisso não encontrado.")
    return event


def _enrich_event(db: Session, user_id: uuid.UUID, event: AgendaEvent) -> dict[str, Any]:
    contact_name = None
    if event.contact_id:
        c = db.scalar(
            select(CrmContact).where(
                CrmContact.id == event.contact_id, CrmContact.user_id == user_id
            )
        )
        contact_name = c.name if c else None
    project_name = None
    if event.project_id:
        p = db.scalar(
            select(WorkProject).where(
                WorkProject.id == event.project_id, WorkProject.user_id == user_id
            )
        )
        project_name = p.name if p else None
    chat_name = None
    if event.messaging_chat_id:
        ch = db.scalar(
            select(MessagingChat).where(
                MessagingChat.id == event.messaging_chat_id, MessagingChat.user_id == user_id
            )
        )
        chat_name = ch.name if ch else None
    return serialize_event(
        event, contact_name=contact_name, project_name=project_name, chat_name=chat_name
    )


def _validate_event_links(
    db: Session,
    user_id: uuid.UUID,
    *,
    contact_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    chat_id: uuid.UUID | None = None,
    inherit_contact_chat: bool = False,
) -> uuid.UUID | None:
    resolved_chat_id = chat_id
    if contact_id is not None:
        contact = db.scalar(
            select(CrmContact).where(CrmContact.id == contact_id, CrmContact.user_id == user_id)
        )
        if contact is None:
            raise AppError(404, "contact_not_found", "Contato do CRM não encontrado.")
        if inherit_contact_chat and resolved_chat_id is None:
            resolved_chat_id = contact.messaging_chat_id

    if project_id is not None:
        proj = db.scalar(
            select(WorkProject).where(WorkProject.id == project_id, WorkProject.user_id == user_id)
        )
        if proj is None:
            raise AppError(404, "project_not_found", "Projeto não encontrado.")

    if resolved_chat_id is not None:
        chat = db.scalar(
            select(MessagingChat).where(
                MessagingChat.id == resolved_chat_id, MessagingChat.user_id == user_id
            )
        )
        if chat is None:
            raise AppError(404, "chat_not_found", "Conversa da Mensageria não encontrada.")
    return resolved_chat_id


def create_event(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()[:160]
    if not title:
        raise AppError(400, "invalid_event_title", "Informe o título do compromisso.")

    kind = str(data.get("kind") or "meeting")
    if kind not in EVENT_KINDS:
        raise AppError(400, "invalid_event_kind", "Tipo de compromisso inválido.")

    status_val = str(data.get("status") or "scheduled")
    if status_val not in EVENT_STATUSES:
        raise AppError(400, "invalid_event_status", "Status do compromisso inválido.")

    start_at = data["start_at"]
    if isinstance(start_at, datetime) and start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=_tz()).astimezone(UTC)
    end_at = data.get("end_at")
    if isinstance(end_at, datetime) and end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=_tz()).astimezone(UTC)

    contact_id = data.get("contact_id")
    project_id = data.get("project_id")
    chat_id = _validate_event_links(
        db,
        user_id,
        contact_id=contact_id,
        project_id=project_id,
        chat_id=data.get("messaging_chat_id"),
        inherit_contact_chat=True,
    )

    now = utcnow()
    event = AgendaEvent(
        user_id=user_id,
        title=title,
        kind=kind,
        start_at=start_at,
        end_at=end_at,
        all_day=bool(data.get("all_day", False)),
        location=(str(data.get("location") or "").strip()[:180] or None),
        status=status_val,
        contact_id=contact_id,
        project_id=project_id,
        messaging_chat_id=chat_id,
        notes=(str(data.get("notes") or "").strip() or None),
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _enrich_event(db, user_id, event)


def update_event(
    db: Session, user_id: uuid.UUID, event_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    event = get_event(db, user_id, event_id)
    if "title" in changes and changes["title"] is not None:
        clean = str(changes["title"]).strip()[:160]
        if not clean:
            raise AppError(400, "invalid_event_title", "Informe o título do compromisso.")
        event.title = clean
    if "kind" in changes and changes["kind"] in EVENT_KINDS:
        event.kind = str(changes["kind"])
    if "status" in changes and changes["status"] in EVENT_STATUSES:
        event.status = str(changes["status"])
    if "start_at" in changes and changes["start_at"] is not None:
        sa_dt = changes["start_at"]
        event.start_at = (
            sa_dt.replace(tzinfo=_tz()).astimezone(UTC) if sa_dt.tzinfo is None else sa_dt
        )
    if "end_at" in changes:
        ea_dt = changes["end_at"]
        event.end_at = (
            ea_dt.replace(tzinfo=_tz()).astimezone(UTC)
            if ea_dt is not None and ea_dt.tzinfo is None
            else ea_dt
        )
    if "all_day" in changes and changes["all_day"] is not None:
        event.all_day = bool(changes["all_day"])
    if "location" in changes:
        event.location = str(changes["location"] or "").strip()[:180] or None
    if "notes" in changes:
        event.notes = str(changes["notes"] or "").strip() or None
    if "contact_id" in changes:
        _validate_event_links(db, user_id, contact_id=changes["contact_id"])
        event.contact_id = changes["contact_id"]
    if "project_id" in changes:
        _validate_event_links(db, user_id, project_id=changes["project_id"])
        event.project_id = changes["project_id"]
    if "messaging_chat_id" in changes:
        _validate_event_links(db, user_id, chat_id=changes["messaging_chat_id"])
        event.messaging_chat_id = changes["messaging_chat_id"]

    event.updated_at = utcnow()
    db.commit()
    db.refresh(event)
    return _enrich_event(db, user_id, event)


def delete_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
    event = get_event(db, user_id, event_id)
    db.delete(event)
    db.commit()


def _months_in_range(start_d: date, end_d: date) -> list[date]:
    months: list[date] = []
    cur = start_d.replace(day=1)
    limit = end_d.replace(day=1)
    while cur <= limit:
        months.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


_LAYER_RESOURCE_MAP: dict[str, str] = {
    "messaging": "mensageria",
    "crm": "dashboard-crm",
    "projects": "projetos",
    "budget": "meu-orcamento",
    "cofre": "cofre",
}


def _collect_agenda_layer(
    db: Session, user: User, start_utc: datetime, end_utc: datetime
) -> list[dict[str, Any]]:
    events = list(
        db.scalars(
            select(AgendaEvent)
            .where(
                AgendaEvent.user_id == user.id,
                AgendaEvent.start_at >= start_utc,
                AgendaEvent.start_at <= end_utc,
            )
            .order_by(AgendaEvent.start_at.asc())
        ).all()
    )
    cids = [e.contact_id for e in events if e.contact_id]
    pids = [e.project_id for e in events if e.project_id]
    chids = [e.messaging_chat_id for e in events if e.messaging_chat_id]
    cmap = (
        {
            c.id: c.name
            for c in db.scalars(
                select(CrmContact).where(CrmContact.user_id == user.id, CrmContact.id.in_(cids))
            ).all()
        }
        if cids
        else {}
    )
    pmap = (
        {
            p.id: p.name
            for p in db.scalars(
                select(WorkProject).where(WorkProject.user_id == user.id, WorkProject.id.in_(pids))
            ).all()
        }
        if pids
        else {}
    )
    chmap = (
        {
            ch.id: ch.name
            for ch in db.scalars(
                select(MessagingChat).where(
                    MessagingChat.user_id == user.id, MessagingChat.id.in_(chids)
                )
            ).all()
        }
        if chids
        else {}
    )
    out: list[dict[str, Any]] = []
    for ev in events:
        local_dt = _to_local_dt(ev.start_at)
        out.append(
            {
                "uid": f"agenda:{ev.id}",
                "id": ev.id,
                "layer": "agenda",
                "kind": ev.kind,
                "title": ev.title,
                "subtitle": cmap.get(ev.contact_id) if ev.contact_id else None,
                "date": local_dt.date().isoformat(),
                "time": None if ev.all_day else local_dt.strftime("%H:%M"),
                "status": ev.status,
                "location": ev.location,
                "contact_id": ev.contact_id,
                "project_id": ev.project_id,
                "project_name": pmap.get(ev.project_id) if ev.project_id else None,
                "messaging_chat_id": ev.messaging_chat_id,
                "chat_name": chmap.get(ev.messaging_chat_id) if ev.messaging_chat_id else None,
                "notes": ev.notes,
            }
        )
    return out


def _collect_messaging_layer(
    db: Session,
    user: User,
    start_date: date,
    start_utc: datetime,
    end_utc: datetime,
) -> list[dict[str, Any]]:
    chats = list(
        db.scalars(
            select(MessagingChat).where(
                MessagingChat.user_id == user.id,
                MessagingChat.archived.is_(False),
                MessagingChat.followup_at.is_not(None),
                MessagingChat.followup_at >= start_utc - timedelta(days=30),
                MessagingChat.followup_at <= end_utc,
            )
        ).all()
    )
    out: list[dict[str, Any]] = []
    for ch in chats:
        assert ch.followup_at is not None
        f_local = _to_local_dt(ch.followup_at)
        if f_local.date() < start_date and ch.service_status == "resolved":
            continue
        out.append(
            {
                "uid": f"messaging:{ch.id}",
                "id": ch.id,
                "layer": "messaging",
                "kind": "followup",
                "title": f"Follow-up WhatsApp: {ch.name}",
                "subtitle": ch.followup_note or "Retorno agendado na Mensageria",
                "date": f_local.date().isoformat(),
                "time": f_local.strftime("%H:%M"),
                "status": ch.service_status or "open",
                "messaging_chat_id": ch.id,
                "chat_name": ch.name,
            }
        )
    return out


def _collect_crm_layer(
    db: Session, user: User, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    deals = list(
        db.scalars(
            select(CrmDeal).where(
                CrmDeal.user_id == user.id,
                CrmDeal.status == "open",
                CrmDeal.expected_close_date.is_not(None),
                CrmDeal.expected_close_date >= start_date,
                CrmDeal.expected_close_date <= end_date,
            )
        ).all()
    )
    out: list[dict[str, Any]] = []
    for d in deals:
        assert d.expected_close_date is not None
        out.append(
            {
                "uid": f"crm:{d.id}",
                "id": d.id,
                "layer": "crm",
                "kind": "deal_close",
                "title": f"Fechamento CRM: {d.title}",
                "subtitle": f"Valor previsto: {brl(d.value)}",
                "date": d.expected_close_date.isoformat(),
                "time": None,
                "status": d.status,
                "contact_id": d.contact_id,
            }
        )
    return out


def _collect_projects_layer(
    db: Session, user: User, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    proj_map = {
        p.id: p for p in db.scalars(select(WorkProject).where(WorkProject.user_id == user.id)).all()
    }
    out: list[dict[str, Any]] = []
    for p in proj_map.values():
        if p.due_date and start_date <= p.due_date <= end_date and p.status != "done":
            out.append(
                {
                    "uid": f"project:{p.id}",
                    "id": p.id,
                    "layer": "projects",
                    "kind": "project_due",
                    "title": f"Entrega do projeto: {p.name}",
                    "subtitle": p.status,
                    "date": p.due_date.isoformat(),
                    "time": None,
                    "status": p.status,
                    "project_id": p.id,
                    "project_name": p.name,
                }
            )
    tasks = list(
        db.scalars(
            select(ProjectTask).where(
                ProjectTask.user_id == user.id,
                ProjectTask.status != "done",
                ProjectTask.due_date.is_not(None),
                ProjectTask.due_date >= start_date,
                ProjectTask.due_date <= end_date,
            )
        ).all()
    )
    for t in tasks:
        assert t.due_date is not None
        proj = proj_map.get(t.project_id)
        out.append(
            {
                "uid": f"task:{t.id}",
                "id": t.id,
                "layer": "projects",
                "kind": "task_due",
                "title": f"Tarefa: {t.title}",
                "subtitle": proj.name if proj else "Projeto",
                "date": t.due_date.isoformat(),
                "time": None,
                "status": t.status,
                "project_id": t.project_id,
                "project_name": proj.name if proj else None,
            }
        )
    return out


def _collect_budget_layer(
    db: Session, user: User, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for month_start in _months_in_range(start_date, end_date):
        cal_items = planned_service.month_calendar(db, user, month_start, ensure=False)
        for ev in cal_items:
            ev_date: date | None = ev.get("date")
            if ev_date is None or not (start_date <= ev_date <= end_date):
                continue
            if ev.get("kind") == "income":
                continue
            paid = bool(ev.get("paid"))
            amount = ev.get("amount")
            desc = str(ev.get("description") or "Conta")
            cat = ev.get("category")
            amt_txt = brl(amount) if amount is not None else ""
            sub_parts = [p for p in (cat, amt_txt, "Pago" if paid else "Em aberto") if p]
            out.append(
                {
                    "uid": f"budget:{ev.get('kind')}:{ev.get('id')}:{ev_date.isoformat()}",
                    "id": ev.get("id"),
                    "layer": "budget",
                    "kind": str(ev.get("kind") or "expense"),
                    "title": desc,
                    "subtitle": " · ".join(sub_parts),
                    "date": ev_date.isoformat(),
                    "time": None,
                    "status": "done" if paid else "open",
                }
            )
    return out


def timeline_360(
    db: Session,
    user: User,
    *,
    start_date: date,
    end_date: date,
    layers: set[str] | None = None,
) -> dict[str, Any]:
    """Agrega Agenda própria, WhatsApp follow-ups, CRM, Projetos e Meu Orçamento."""
    if end_date < start_date:
        raise AppError(400, "invalid_date_range", "Data final deve ser maior ou igual à inicial.")
    if (end_date - start_date).days > 92:
        raise AppError(
            400,
            "periodo_longo",
            "Escolha um período de até 92 dias para consultar a Agenda.",
        )
    blocked = admin_service.effective_blocked_resources(db, user)
    allowed_layers = {"agenda"} | {
        layer for layer, res_id in _LAYER_RESOURCE_MAP.items() if res_id not in blocked
    }
    active_layers = (layers & allowed_layers) if layers else allowed_layers

    tz = _tz()
    start_utc = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(end_date, time.max, tzinfo=tz).astimezone(UTC)

    collectors = {
        "agenda": lambda: _collect_agenda_layer(db, user, start_utc, end_utc),
        "messaging": lambda: _collect_messaging_layer(db, user, start_date, start_utc, end_utc),
        "crm": lambda: _collect_crm_layer(db, user, start_date, end_date),
        "projects": lambda: _collect_projects_layer(db, user, start_date, end_date),
        "budget": lambda: _collect_budget_layer(db, user, start_date, end_date),
        "cofre": lambda: vault_service.collect_agenda_expiries(db, user, start_date, end_date),
    }

    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {k: 0 for k in ALL_LAYERS}
    for layer, collect in collectors.items():
        if layer not in active_layers:
            continue
        layer_items = collect()
        items.extend(layer_items)
        counts[layer] = len(layer_items)

    items.sort(key=lambda r: (r["date"], r["time"] or "99:99", r["layer"], r["title"]))
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "items": items,
        "counts_by_layer": counts,
    }


def prepare_whatsapp_confirmation(
    db: Session,
    user: User,
    event_id: uuid.UUID,
    *,
    send_now: bool = False,
    custom_text: str | None = None,
) -> dict[str, Any]:
    """Gera (e opcionalmente envia pela Mensageria) mensagem de confirmação de compromisso."""
    event = get_event(db, user.id, event_id)
    chat: MessagingChat | None = None
    if event.messaging_chat_id is not None:
        chat = db.scalar(
            select(MessagingChat).where(
                MessagingChat.id == event.messaging_chat_id,
                MessagingChat.user_id == user.id,
            )
        )
    elif event.contact_id is not None:
        contact = db.scalar(
            select(CrmContact).where(
                CrmContact.id == event.contact_id, CrmContact.user_id == user.id
            )
        )
        if contact and contact.messaging_chat_id:
            chat = db.scalar(
                select(MessagingChat).where(
                    MessagingChat.id == contact.messaging_chat_id,
                    MessagingChat.user_id == user.id,
                )
            )

    local_dt = _to_local_dt(event.start_at)
    when = (
        local_dt.strftime("%d/%m/%Y") if event.all_day else local_dt.strftime("%d/%m/%Y às %H:%M")
    )
    recipient = chat.name if chat else "tudo bem"
    where = f" Local: {event.location}." if event.location else ""
    text = (custom_text or "").strip() or (
        f'Olá, {recipient}! Passando para confirmar nosso compromisso "{event.title}" '
        f"marcado para {when}.{where} Até lá!"
    )

    sent_message = None
    if send_now:
        admin_service.assert_resource_allowed(db, user, "mensageria")
        if chat is None:
            raise AppError(
                409,
                "missing_whatsapp_chat",
                "Vincule uma conversa da Mensageria ao compromisso antes de enviar.",
            )
        sent_message = messaging_messages.send_message(db, user, chat.id, body=text)

    return {
        "event_id": event.id,
        "chat_id": chat.id if chat else None,
        "chat_name": chat.name if chat else None,
        "text": text,
        "sent": sent_message is not None,
        "message": sent_message,
    }


def create_event_from_messaging(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    title: str,
    start_at: datetime,
    kind: str = "meeting",
    location: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Cria compromisso na Agenda diretamente a partir de uma conversa da Mensageria."""
    admin_service.assert_resource_allowed(db, user, "agenda")
    chat = db.scalar(
        select(MessagingChat).where(MessagingChat.id == chat_id, MessagingChat.user_id == user.id)
    )
    if chat is None:
        raise AppError(404, "chat_not_found", "Conversa não encontrada.")
    contact = db.scalar(
        select(CrmContact).where(
            CrmContact.user_id == user.id, CrmContact.messaging_chat_id == chat.id
        )
    )
    return create_event(
        db,
        user.id,
        {
            "title": title,
            "kind": kind,
            "start_at": start_at,
            "location": location,
            "notes": notes or f"Agendado pela conversa com {chat.name}.",
            "messaging_chat_id": chat.id,
            "contact_id": contact.id if contact else None,
        },
    )
