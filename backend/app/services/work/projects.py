"""Serviços de Projetos & Tarefas: Kanban, checklists, horas e rentabilidade com o Orçamento."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.money import Q2, ZERO, to_dec
from app.db.types import utcnow
from app.models import (
    CommercialDocument,
    CrmActivity,
    CrmContact,
    CrmDeal,
    Expense,
    MessagingChat,
    MessagingMessage,
    Project,
    ProjectTask,
    ProjectTimeEntry,
    User,
    WorkProject,
)
from app.services import admin as admin_service
from app.services.common import get_owned

PROJECT_STATUSES = ("planning", "active", "review", "done", "paused")
TASK_STATUSES = ("todo", "doing", "done")
TASK_PRIORITIES = ("low", "medium", "high", "urgent")


def _normalize_checklist(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw[:40]:
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()[:160]
            if not text:
                continue
            item_id = str(entry.get("id") or uuid.uuid4())
            out.append({"id": item_id, "text": text, "done": bool(entry.get("done", False))})
    return out


def ensure_budget_project_tag(
    db: Session, user_id: uuid.UUID, name: str, budget_value: Decimal
) -> Project:
    """Cria uma etiqueta exclusiva no Meu Orçamento para isolar custos do projeto."""
    base = (name.strip()[:40] or "Projeto").strip()
    used_names = {
        row_name
        for row_name in db.scalars(select(Project.name).where(Project.user_id == user_id)).all()
    }
    tag_name = base
    if tag_name in used_names:
        candidate = f"{base[:33]} (Proj)"
        if candidate not in used_names:
            tag_name = candidate
        else:
            idx = 2
            while True:
                suffix = f" #{idx}"
                attempt = f"{base[: 40 - len(suffix)]}{suffix}"
                if attempt not in used_names:
                    tag_name = attempt
                    break
                idx += 1
    tag = Project(
        user_id=user_id,
        name=tag_name,
        budget=budget_value if budget_value > ZERO else None,
        created_at=utcnow(),
    )
    db.add(tag)
    db.flush()
    return tag


def _project_metrics_map(
    db: Session, user_id: uuid.UUID, projects: list[WorkProject]
) -> dict[uuid.UUID, dict[str, Any]]:
    if not projects:
        return {}

    project_ids = [p.id for p in projects]
    budget_ids = [p.budget_project_id for p in projects if p.budget_project_id is not None]

    # Horas apontadas por projeto
    hours_by_proj: dict[uuid.UUID, Decimal] = {}
    for pid, total_h in db.execute(
        select(ProjectTimeEntry.project_id, func.coalesce(func.sum(ProjectTimeEntry.hours), 0))
        .where(
            ProjectTimeEntry.user_id == user_id,
            ProjectTimeEntry.project_id.in_(project_ids),
        )
        .group_by(ProjectTimeEntry.project_id)
    ).all():
        hours_by_proj[pid] = Decimal(total_h or ZERO).quantize(Q2)

    # Despesas reais vinculadas no Meu Orçamento
    exp_by_budget_tag: dict[uuid.UUID, Decimal] = {}
    if budget_ids:
        for bpid, total_e in db.execute(
            select(Expense.project_id, func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.user_id == user_id, Expense.project_id.in_(budget_ids))
            .group_by(Expense.project_id)
        ).all():
            if bpid is not None:
                exp_by_budget_tag[bpid] = Decimal(total_e or ZERO).quantize(Q2)

    # Contagem de tarefas por status
    task_counts: dict[uuid.UUID, dict[str, int]] = {
        p.id: {"todo": 0, "doing": 0, "done": 0} for p in projects
    }
    for pid, st, cnt in db.execute(
        select(ProjectTask.project_id, ProjectTask.status, func.count(ProjectTask.id))
        .where(ProjectTask.user_id == user_id, ProjectTask.project_id.in_(project_ids))
        .group_by(ProjectTask.project_id, ProjectTask.status)
    ).all():
        bucket = task_counts.get(pid)
        if bucket and st in bucket:
            bucket[st] = int(cnt or 0)

    out: dict[uuid.UUID, dict[str, Any]] = {}
    for p in projects:
        hours = hours_by_proj.get(p.id, ZERO)
        expenses_total = (
            exp_by_budget_tag.get(p.budget_project_id, ZERO) if p.budget_project_id else ZERO
        )
        budget_val = Decimal(p.budget_value or ZERO).quantize(Q2)
        net_margin = (budget_val - expenses_total).quantize(Q2)
        effective_hourly = (
            (net_margin / hours).quantize(Q2, rounding=ROUND_HALF_UP) if hours > ZERO else ZERO
        )
        counts = task_counts[p.id]
        total_tasks = counts["todo"] + counts["doing"] + counts["done"]
        out[p.id] = {
            "total_hours": str(hours),
            "expenses_total": str(expenses_total),
            "net_margin": str(net_margin),
            "effective_hourly_rate": str(effective_hourly),
            "tasks_todo": counts["todo"],
            "tasks_doing": counts["doing"],
            "tasks_done": counts["done"],
            "tasks_total": total_tasks,
        }
    return out


def serialize_project(
    project: WorkProject,
    metrics: dict[str, Any],
    *,
    contact_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "contact_id": project.contact_id,
        "contact_name": contact_name,
        "crm_deal_id": project.crm_deal_id,
        "proposal_id": project.proposal_id,
        "budget_project_id": project.budget_project_id,
        "budget_value": str(Decimal(project.budget_value or ZERO).quantize(Q2)),
        "hourly_rate": str(Decimal(project.hourly_rate or ZERO).quantize(Q2)),
        "start_date": project.start_date,
        "due_date": project.due_date,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        **metrics,
    }


def serialize_task(task: ProjectTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date,
        "checklist": list(task.checklist_json or []),
        "position": task.position,
        "source_chat_id": task.source_chat_id,
        "source_message_id": task.source_message_id,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def serialize_time_entry(entry: ProjectTimeEntry, task_title: str | None = None) -> dict[str, Any]:
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "task_id": entry.task_id,
        "task_title": task_title,
        "hours": str(Decimal(entry.hours or ZERO).quantize(Q2)),
        "entry_date": entry.entry_date,
        "notes": entry.notes,
        "created_at": entry.created_at,
    }


def list_projects(
    db: Session, user_id: uuid.UUID, *, status_filter: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(WorkProject).where(WorkProject.user_id == user_id)
    if status_filter in PROJECT_STATUSES:
        stmt = stmt.where(WorkProject.status == status_filter)
    rows = list(db.scalars(stmt.order_by(WorkProject.updated_at.desc())).all())
    metrics_map = _project_metrics_map(db, user_id, rows)
    contact_ids = [r.contact_id for r in rows if r.contact_id is not None]
    contacts: dict[uuid.UUID, str] = {}
    if contact_ids:
        for c in db.scalars(
            select(CrmContact).where(CrmContact.user_id == user_id, CrmContact.id.in_(contact_ids))
        ).all():
            contacts[c.id] = c.name
    return [
        serialize_project(
            p,
            metrics_map[p.id],
            contact_name=contacts.get(p.contact_id) if p.contact_id else None,
        )
        for p in rows
    ]


def get_project(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> WorkProject:
    return get_owned(
        db,
        WorkProject,
        user_id,
        project_id,
        error_code="project_not_found",
        error_msg="Projeto não encontrado.",
    )


def get_project_detail(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, Any]:
    project = get_project(db, user_id, project_id)
    metrics = _project_metrics_map(db, user_id, [project])[project.id]
    contact_name = None
    if project.contact_id is not None:
        contact = db.scalar(
            select(CrmContact).where(
                CrmContact.id == project.contact_id, CrmContact.user_id == user_id
            )
        )
        contact_name = contact.name if contact else None
    tasks = list(
        db.scalars(
            select(ProjectTask)
            .where(ProjectTask.project_id == project.id, ProjectTask.user_id == user_id)
            .order_by(ProjectTask.position.asc(), ProjectTask.created_at.asc())
        ).all()
    )
    task_titles = {t.id: t.title for t in tasks}
    entries = list(
        db.scalars(
            select(ProjectTimeEntry)
            .where(
                ProjectTimeEntry.project_id == project.id,
                ProjectTimeEntry.user_id == user_id,
            )
            .order_by(ProjectTimeEntry.entry_date.desc(), ProjectTimeEntry.created_at.desc())
        ).all()
    )
    return {
        "project": serialize_project(project, metrics, contact_name=contact_name),
        "tasks": [serialize_task(t) for t in tasks],
        "time_entries": [
            serialize_time_entry(e, task_title=task_titles.get(e.task_id) if e.task_id else None)
            for e in entries
        ],
    }


def create_project(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()[:140]
    if not name:
        raise AppError(400, "invalid_project_name", "Informe o nome do projeto.")

    status_val = str(data.get("status") or "planning")
    if status_val not in PROJECT_STATUSES:
        raise AppError(400, "invalid_project_status", "Status de projeto inválido.")

    contact_id = data.get("contact_id")
    contact_name = None
    if contact_id is not None:
        contact = get_owned(
            db,
            CrmContact,
            user_id,
            contact_id,
            error_code="contact_not_found",
            error_msg="Contato do CRM não encontrado.",
        )
        contact_name = contact.name

    budget_value = to_dec(data.get("budget_value", 0), field="valor orçado")
    hourly_rate = to_dec(data.get("hourly_rate", 0), field="valor hora")

    crm_deal_id = data.get("crm_deal_id")
    if crm_deal_id is not None:
        get_owned(
            db,
            CrmDeal,
            user_id,
            crm_deal_id,
            error_code="deal_not_found",
            error_msg="Negócio do CRM não encontrado.",
        )

    proposal_id = data.get("proposal_id")
    if proposal_id is not None:
        get_owned(
            db,
            CommercialDocument,
            user_id,
            proposal_id,
            error_code="document_not_found",
            error_msg="Documento comercial não encontrado.",
        )

    budget_project_id = data.get("budget_project_id")
    if budget_project_id is not None:
        get_owned(
            db,
            Project,
            user_id,
            budget_project_id,
            error_code="budget_project_not_found",
            error_msg="Projeto/etiqueta do Orçamento não encontrado.",
        )
    elif data.get("link_budget_tag", True):
        tag = ensure_budget_project_tag(db, user_id, name, budget_value)
        budget_project_id = tag.id

    now = utcnow()
    project = WorkProject(
        user_id=user_id,
        name=name,
        description=(str(data.get("description") or "").strip() or None),
        status=status_val,
        contact_id=contact_id,
        crm_deal_id=crm_deal_id,
        proposal_id=proposal_id,
        budget_project_id=budget_project_id,
        budget_value=budget_value,
        hourly_rate=hourly_rate,
        start_date=data.get("start_date"),
        due_date=data.get("due_date"),
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    metrics = _project_metrics_map(db, user_id, [project])[project.id]
    return serialize_project(project, metrics, contact_name=contact_name)


def update_project(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    project = get_project(db, user_id, project_id)
    if "name" in changes and changes["name"] is not None:
        clean = str(changes["name"]).strip()[:140]
        if not clean:
            raise AppError(400, "invalid_project_name", "Informe o nome do projeto.")
        project.name = clean
    if "description" in changes:
        project.description = str(changes["description"] or "").strip() or None
    if "status" in changes and changes["status"] in PROJECT_STATUSES:
        project.status = str(changes["status"])
    if "contact_id" in changes:
        cid = changes["contact_id"]
        if cid is not None:
            get_owned(
                db,
                CrmContact,
                user_id,
                cid,
                error_code="contact_not_found",
                error_msg="Contato do CRM não encontrado.",
            )
        project.contact_id = cid
    if "budget_value" in changes and changes["budget_value"] is not None:
        project.budget_value = to_dec(changes["budget_value"], field="valor orçado")
    if "hourly_rate" in changes and changes["hourly_rate"] is not None:
        project.hourly_rate = to_dec(changes["hourly_rate"], field="valor hora")
    if "start_date" in changes:
        project.start_date = changes["start_date"]
    if "due_date" in changes:
        project.due_date = changes["due_date"]

    project.updated_at = utcnow()
    db.commit()
    db.refresh(project)
    return get_project_detail(db, user_id, project.id)["project"]


def delete_project(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
    project = get_project(db, user_id, project_id)
    db.delete(project)
    db.commit()


# ---------------------------------------------------------------- tarefas e apontamento de horas


def create_task(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    project = get_project(db, user_id, project_id)
    title = str(data.get("title") or "").strip()[:160]
    if not title:
        raise AppError(400, "invalid_task_title", "Informe o título da tarefa.")
    status_val = str(data.get("status") or "todo")
    if status_val not in TASK_STATUSES:
        raise AppError(400, "invalid_task_status", "Status de tarefa inválido.")
    priority_val = str(data.get("priority") or "medium")
    if priority_val not in TASK_PRIORITIES:
        raise AppError(400, "invalid_task_priority", "Prioridade inválida.")

    max_pos = (
        db.scalar(
            select(func.coalesce(func.max(ProjectTask.position), 0)).where(
                ProjectTask.project_id == project.id
            )
        )
        or 0
    )
    now = utcnow()
    task = ProjectTask(
        user_id=user_id,
        project_id=project.id,
        title=title,
        description=(str(data.get("description") or "").strip() or None),
        status=status_val,
        priority=priority_val,
        due_date=data.get("due_date"),
        checklist_json=_normalize_checklist(data.get("checklist")),
        position=int(max_pos) + 1,
        source_chat_id=data.get("source_chat_id"),
        source_message_id=data.get("source_message_id"),
        completed_at=now if status_val == "done" else None,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    project.updated_at = now
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def update_task(
    db: Session, user_id: uuid.UUID, task_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    task = get_owned(
        db,
        ProjectTask,
        user_id,
        task_id,
        error_code="task_not_found",
        error_msg="Tarefa não encontrada.",
    )
    now = utcnow()
    if "title" in changes and changes["title"] is not None:
        clean = str(changes["title"]).strip()[:160]
        if not clean:
            raise AppError(400, "invalid_task_title", "Informe o título da tarefa.")
        task.title = clean
    if "description" in changes:
        task.description = str(changes["description"] or "").strip() or None
    if "status" in changes and changes["status"] in TASK_STATUSES:
        new_st = str(changes["status"])
        task.status = new_st
        task.completed_at = now if new_st == "done" else None
    if "priority" in changes and changes["priority"] in TASK_PRIORITIES:
        task.priority = str(changes["priority"])
    if "due_date" in changes:
        task.due_date = changes["due_date"]
    if "checklist" in changes:
        task.checklist_json = _normalize_checklist(changes["checklist"])
    if "position" in changes and changes["position"] is not None:
        task.position = int(changes["position"])

    task.updated_at = now
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def delete_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = get_owned(
        db,
        ProjectTask,
        user_id,
        task_id,
        error_code="task_not_found",
        error_msg="Tarefa não encontrada.",
    )
    db.delete(task)
    db.commit()


def create_time_entry(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    project = get_project(db, user_id, project_id)
    hours = to_dec(data.get("hours"), field="horas")
    if hours <= ZERO or hours > Decimal("1000"):
        raise AppError(400, "invalid_hours", "Informe uma quantidade de horas maior que zero.")

    task_id = data.get("task_id")
    task_title = None
    if task_id is not None:
        task = db.scalar(
            select(ProjectTask).where(
                ProjectTask.id == task_id,
                ProjectTask.project_id == project.id,
                ProjectTask.user_id == user_id,
            )
        )
        if task is None:
            raise AppError(404, "task_not_found", "Tarefa não encontrada neste projeto.")
        task_title = task.title

    now = utcnow()
    entry = ProjectTimeEntry(
        user_id=user_id,
        project_id=project.id,
        task_id=task_id,
        hours=hours,
        entry_date=data["entry_date"],
        notes=(str(data.get("notes") or "").strip()[:240] or None),
        created_at=now,
    )
    db.add(entry)
    project.updated_at = now
    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry, task_title=task_title)


def delete_time_entry(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = get_owned(
        db,
        ProjectTimeEntry,
        user_id,
        entry_id,
        error_code="time_entry_not_found",
        error_msg="Apontamento de horas não encontrado.",
    )
    db.delete(entry)
    db.commit()


# ---------------------------------------------------------------- pontes com soluções do Hub


def create_project_from_crm_deal(db: Session, user: User, deal_id: uuid.UUID) -> dict[str, Any]:
    """Cria um projeto operacional a partir de um negócio do CRM (idempotente)."""
    admin_service.assert_resource_allowed(db, user, "projetos")
    deal = get_owned(
        db,
        CrmDeal,
        user.id,
        deal_id,
        error_code="deal_not_found",
        error_msg="Negócio do CRM não encontrado.",
    )

    existing = db.scalar(
        select(WorkProject).where(
            WorkProject.user_id == user.id, WorkProject.crm_deal_id == deal.id
        )
    )
    if existing is not None:
        return {
            "created": False,
            "project": get_project_detail(db, user.id, existing.id)["project"],
        }

    try:
        created = create_project(
            db,
            user.id,
            {
                "name": deal.title[:140],
                "description": deal.notes or f"Projeto originado do negócio CRM '{deal.title}'.",
                "status": "active",
                "contact_id": deal.contact_id,
                "crm_deal_id": deal.id,
                "budget_value": deal.value or ZERO,
                "due_date": deal.expected_close_date,
                "link_budget_tag": True,
            },
        )
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WorkProject).where(
                WorkProject.user_id == user.id, WorkProject.crm_deal_id == deal.id
            )
        )
        if existing is None:
            raise
        return {
            "created": False,
            "project": get_project_detail(db, user.id, existing.id)["project"],
        }
    create_task(
        db,
        user.id,
        created["id"],
        {
            "title": f"Iniciar entrega: {deal.title}"[:160],
            "priority": "high",
            "due_date": deal.expected_close_date,
        },
    )
    db.add(
        CrmActivity(
            user_id=user.id,
            contact_id=deal.contact_id,
            deal_id=deal.id,
            kind="note",
            body=f"Projeto '{created['name']}' aberto em Projetos & Tarefas.",
        )
    )
    db.commit()
    return {
        "created": True,
        "project": get_project_detail(db, user.id, created["id"])["project"],
    }


def create_project_from_proposal(db: Session, user: User, doc_id: uuid.UUID) -> dict[str, Any]:
    """Cria um projeto com tarefas a partir de uma proposta/OS/contrato em PDF (idempotente)."""
    admin_service.assert_resource_allowed(db, user, "projetos")
    doc = get_owned(
        db,
        CommercialDocument,
        user.id,
        doc_id,
        error_code="document_not_found",
        error_msg="Documento comercial não encontrado.",
    )

    existing = db.scalar(
        select(WorkProject).where(WorkProject.user_id == user.id, WorkProject.proposal_id == doc.id)
    )
    if existing is not None:
        return {
            "created": False,
            "project": get_project_detail(db, user.id, existing.id)["project"],
        }

    try:
        created = create_project(
            db,
            user.id,
            {
                "name": doc.title[:140],
                "description": (
                    f"Entrega do documento #{doc.number:04d} · Cliente {doc.customer_name}."
                ),
                "status": "active",
                "contact_id": doc.contact_id,
                "crm_deal_id": doc.crm_deal_id,
                "proposal_id": doc.id,
                "budget_value": doc.total_amount or ZERO,
                "due_date": doc.valid_until,
                "link_budget_tag": True,
            },
        )
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WorkProject).where(
                WorkProject.user_id == user.id, WorkProject.proposal_id == doc.id
            )
        )
        if existing is None:
            raise
        return {
            "created": False,
            "project": get_project_detail(db, user.id, existing.id)["project"],
        }
    for item in (doc.items_json or [])[:12]:
        item_name = str(item.get("name") or "").strip()
        if item_name:
            create_task(
                db,
                user.id,
                created["id"],
                {
                    "title": f"Entregar: {item_name}"[:160],
                    "priority": "medium",
                    "due_date": doc.valid_until,
                },
            )
    if doc.contact_id is not None:
        db.add(
            CrmActivity(
                user_id=user.id,
                contact_id=doc.contact_id,
                deal_id=doc.crm_deal_id,
                kind="note",
                body=f"Projeto '{created['name']}' criado a partir do documento #{doc.number:04d}.",
            )
        )
        db.commit()
    return {
        "created": True,
        "project": get_project_detail(db, user.id, created["id"])["project"],
    }


def create_task_from_messaging(
    db: Session,
    user: User,
    chat_id: uuid.UUID,
    *,
    title: str,
    project_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    due_date: Any = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """Transforma uma mensagem/conversa do WhatsApp em tarefa dentro de um projeto."""
    admin_service.assert_resource_allowed(db, user, "projetos")
    chat = get_owned(
        db,
        MessagingChat,
        user.id,
        chat_id,
        error_code="chat_not_found",
        error_msg="Conversa não encontrada.",
    )

    if message_id is not None:
        msg = db.scalar(
            select(MessagingMessage).where(
                MessagingMessage.id == message_id,
                MessagingMessage.chat_id == chat.id,
                MessagingMessage.user_id == user.id,
            )
        )
        if msg is None:
            raise AppError(404, "message_not_found", "Mensagem não encontrada.")

    if project_id is not None:
        target = get_project(db, user.id, project_id)
    else:
        default_name = f"Atendimento · {chat.name}"[:140]
        target = db.scalar(
            select(WorkProject).where(
                WorkProject.user_id == user.id, WorkProject.name == default_name
            )
        )
        if target is None:
            contact = db.scalar(
                select(CrmContact).where(
                    CrmContact.user_id == user.id, CrmContact.messaging_chat_id == chat.id
                )
            )
            created_proj = create_project(
                db,
                user.id,
                {
                    "name": default_name,
                    "description": f"Demandas recebidas pelo WhatsApp de {chat.name}.",
                    "status": "active",
                    "contact_id": contact.id if contact else None,
                    "link_budget_tag": False,
                },
            )
            target = get_project(db, user.id, created_proj["id"])

    task = create_task(
        db,
        user.id,
        target.id,
        {
            "title": title,
            "description": f"Origem WhatsApp ({chat.name}).",
            "priority": priority,
            "due_date": due_date,
            "source_chat_id": chat.id,
            "source_message_id": message_id,
        },
    )
    return {"project_id": target.id, "project_name": target.name, "task": task}


def list_projects_hub_bridges(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    from app.services.commerce.shared import list_hub_bridges

    base = list_hub_bridges(db, user_id)
    proposals = [
        {
            "id": d.id,
            "title": d.title,
            "number": d.number,
            "total_amount": str(Decimal(d.total_amount or ZERO).quantize(Q2)),
            "customer_name": d.customer_name,
            "status": d.status,
        }
        for d in db.scalars(
            select(CommercialDocument)
            .where(CommercialDocument.user_id == user_id)
            .order_by(CommercialDocument.created_at.desc())
            .limit(60)
        ).all()
    ]
    budget_tags = [
        {"id": p.id, "name": p.name, "budget": str(Decimal(p.budget or ZERO).quantize(Q2))}
        for p in db.scalars(
            select(Project).where(Project.user_id == user_id).order_by(Project.name.asc())
        ).all()
    ]
    return {**base, "proposals": proposals, "budget_tags": budget_tags}
