"""Testes de Projetos & Tarefas (Kanban, horas, rentabilidade), Agenda 360° e bridges."""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Expense,
    MessagingChat,
    MessagingMessage,
    MessagingSession,
    PlannedExpense,
    User,
)
from app.services.budget import ensure_month
from app.services.messaging import connector_client
from tests.conftest import create_verified_user, login


def _make_user(
    client: TestClient, db: Session, outbox: list, email: str, *, is_admin: bool = False
) -> User:
    create_verified_user(client, outbox, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    if is_admin:
        user.is_admin = True
    db.commit()
    db.refresh(user)
    return user


def test_projects_kanban_timesheet_and_real_budget_profitability(
    client: TestClient, db: Session, outbox: list
) -> None:
    user = _make_user(client, db, outbox, "projetos@example.com")
    assert login(client, user.email).status_code == 200

    contact = client.post(
        "/api/crm/contacts", json={"name": "Studio Alfa", "phone": "11991112222"}
    ).json()

    # Cria projeto vinculado automaticamente a uma etiqueta real no Meu Orçamento.
    p_resp = client.post(
        "/api/work/projects",
        json={
            "name": "Implantação ERP Studio",
            "status": "active",
            "contact_id": contact["id"],
            "budget_value": "2000.00",
            "hourly_rate": "150.00",
            "due_date": date.today().isoformat(),
            "link_budget_tag": True,
        },
    )
    assert p_resp.status_code == 201
    proj = p_resp.json()
    assert proj["budget_project_id"] is not None

    # Lança uma despesa real no Meu Orçamento marcada com a etiqueta do projeto.
    month = date.today().replace(day=1)
    ensure_month(db, user, month)
    db.add(
        Expense(
            user_id=user.id,
            month=month,
            description="Licença software terceiros",
            amount=500,
            due_date=date.today(),
            paid=True,
            project_id=uuid.UUID(proj["budget_project_id"]),
        )
    )
    db.commit()

    # Cria tarefas com checklist e alterna etapas do Kanban.
    t1 = client.post(
        f"/api/work/projects/{proj['id']}/tasks",
        json={
            "title": "Configurar servidor",
            "priority": "high",
            "due_date": date.today().isoformat(),
            "checklist": [{"text": "Subir banco", "done": False}],
        },
    )
    assert t1.status_code == 201
    task1 = t1.json()
    t2 = client.post(
        f"/api/work/projects/{proj['id']}/tasks",
        json={"title": "Treinar equipe", "status": "todo"},
    )
    assert t2.status_code == 201

    upd = client.patch(
        f"/api/work/projects/tasks/{task1['id']}",
        json={
            "status": "done",
            "checklist": [{"id": task1["checklist"][0]["id"], "text": "Subir banco", "done": True}],
        },
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "done"
    assert upd.json()["completed_at"] is not None

    # Aponta horas e valida cálculo real de margem e ganho por hora.
    assert (
        client.post(
            f"/api/work/projects/{proj['id']}/time-entries",
            json={"task_id": task1["id"], "hours": "3.50", "entry_date": date.today().isoformat()},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/work/projects/{proj['id']}/time-entries",
            json={"hours": "1.50", "entry_date": date.today().isoformat(), "notes": "Alinhamento"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/work/projects/{proj['id']}/time-entries",
            json={"hours": "0", "entry_date": date.today().isoformat()},
        ).status_code
        == 400
    )

    detail = client.get(f"/api/work/projects/{proj['id']}").json()
    p_data = detail["project"]
    assert p_data["expenses_total"] == "500.00"
    assert p_data["net_margin"] == "1500.00"
    assert p_data["total_hours"] == "5.00"
    assert p_data["effective_hourly_rate"] == "300.00"
    assert p_data["tasks_done"] == 1
    assert p_data["tasks_todo"] == 1
    assert len(detail["time_entries"]) == 2


def test_agenda_timeline_360_and_whatsapp_confirmation(
    client: TestClient, db: Session, outbox: list, monkeypatch
) -> None:
    monkeypatch.setattr(connector_client, "flush_session", lambda _sid: True)
    user = _make_user(client, db, outbox, "agenda@example.com")
    assert login(client, user.email).status_code == 200

    tz = ZoneInfo(get_settings().timezone)
    today = datetime.now(tz).date()
    start_dt = datetime(today.year, today.month, today.day, 14, 30, tzinfo=tz)

    # 1. Sessão e chat na Mensageria com follow-up agendado.
    db.add(MessagingSession(user_id=user.id, status="ready", wanted=True))
    chat = MessagingChat(
        user_id=user.id,
        remote_jid="5511955554444@s.whatsapp.net",
        phone="5511955554444",
        name="Construtora Ideal",
        followup_at=start_dt + timedelta(hours=2),
        followup_note="Enviar cronograma revisado",
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    contact = client.post(f"/api/crm/contacts/from-messaging/{chat.id}").json()["contact"]

    # 2. Negócio no CRM com previsão de fechamento na janela.
    deal = client.post(
        "/api/crm/deals",
        json={
            "title": "Reforma Galpão",
            "value": "4500.00",
            "contact_id": contact["id"],
            "expected_close_date": (today + timedelta(days=1)).isoformat(),
        },
    )
    assert deal.status_code == 201

    # 3. Projeto com prazo na janela.
    proj = client.post(
        "/api/work/projects",
        json={
            "name": "Projeto Executivo Galpão",
            "due_date": (today + timedelta(days=2)).isoformat(),
            "link_budget_tag": False,
        },
    ).json()
    assert (
        client.post(
            f"/api/work/projects/{proj['id']}/tasks",
            json={"title": "Aprovar planta", "due_date": today.isoformat()},
        ).status_code
        == 201
    )

    # 4. Vencimento real no Meu Orçamento (despesa + planejado).
    month = today.replace(day=1)
    ensure_month(db, user, month)
    db.add(
        Expense(
            user_id=user.id,
            month=month,
            description="Aluguel escritório",
            amount=1800,
            due_date=today,
            paid=False,
        )
    )
    db.add(
        PlannedExpense(
            user_id=user.id,
            date=today + timedelta(days=1),
            description="Seguro anual",
            amount=420,
        )
    )
    db.commit()

    # 5. Compromisso na própria Agenda vinculado ao contato e projeto.
    ev_resp = client.post(
        "/api/agenda/events",
        json={
            "title": "Reunião de alinhamento",
            "kind": "meeting",
            "start_at": start_dt.isoformat(),
            "location": "Google Meet",
            "contact_id": contact["id"],
            "project_id": proj["id"],
        },
    )
    assert ev_resp.status_code == 201
    event = ev_resp.json()
    assert event["messaging_chat_id"] == str(chat.id)

    # Timeline unificada traz as 5 camadas ordenadas e aceita filtro por camada.
    tl = client.get(
        f"/api/agenda/timeline?start={(today - timedelta(days=1)).isoformat()}"
        f"&end={(today + timedelta(days=5)).isoformat()}"
    )
    assert tl.status_code == 200
    body = tl.json()
    layers_present = {item["layer"] for item in body["items"]}
    assert layers_present == {"agenda", "messaging", "crm", "projects", "budget"}
    assert body["counts_by_layer"]["projects"] == 2  # projeto + tarefa
    assert body["counts_by_layer"]["budget"] == 2  # despesa + planejado

    only_crm_agenda = client.get(
        f"/api/agenda/timeline?start={today.isoformat()}"
        f"&end={(today + timedelta(days=3)).isoformat()}&layers=agenda,crm"
    ).json()
    assert {i["layer"] for i in only_crm_agenda["items"]} == {"agenda", "crm"}

    # Preparação + envio real de confirmação pelo WhatsApp da Mensageria.
    prep = client.post(
        f"/api/agenda/events/{event['id']}/confirm-whatsapp",
        json={"send_now": False},
    )
    assert prep.status_code == 200
    assert "Reunião de alinhamento" in prep.json()["text"]
    assert prep.json()["sent"] is False

    sent = client.post(
        f"/api/agenda/events/{event['id']}/confirm-whatsapp",
        json={"send_now": True},
    )
    assert sent.status_code == 200
    assert sent.json()["sent"] is True
    queued = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.user_id == user.id, MessagingMessage.chat_id == chat.id
        )
    )
    assert queued is not None
    assert "Reunião de alinhamento" in queued.body


def test_work_cross_solution_bridges_isolation_and_governance(
    client: TestClient, db: Session, outbox: list
) -> None:
    adm = _make_user(client, db, outbox, "adm-work@example.com", is_admin=True)
    dono = _make_user(client, db, outbox, "dono-work@example.com")
    outro = _make_user(client, db, outbox, "outro-work@example.com")

    assert login(client, dono.email).status_code == 200
    deal = client.post(
        "/api/crm/deals", json={"title": "Site Corporativo", "value": "3200.00"}
    ).json()
    doc = client.post(
        "/api/proposals",
        json={
            "doc_type": "service_order",
            "title": "OS Instalação Rede",
            "customer_name": "Mercado Bom",
            "items": [{"name": "Cabeamento", "qty": 1, "unit_price": "900.00"}],
        },
    ).json()

    # 1. CRM Deal -> Projeto em 1 clique (idempotente).
    p_deal = client.post(f"/api/crm/deals/{deal['id']}/create-project")
    assert p_deal.status_code == 201
    assert p_deal.json()["created"] is True
    proj_id = p_deal.json()["project"]["id"]
    assert client.post(f"/api/crm/deals/{deal['id']}/create-project").json()["created"] is False

    # 2. Proposta -> Projeto em 1 clique convertendo itens em tarefas.
    p_prop = client.post(f"/api/proposals/{doc['id']}/create-project")
    assert p_prop.status_code == 201
    assert p_prop.json()["created"] is True
    assert p_prop.json()["project"]["tasks_todo"] == 1

    # 3. Mensageria -> Tarefa + Compromisso.
    chat = client.post(
        "/api/messaging/chats", json={"phone": "5511944443333", "name": "Mercado Bom"}
    ).json()
    msg_task = client.post(
        f"/api/messaging/chats/{chat['id']}/work-task",
        json={"title": "Enviar fotos do quadro elétrico", "project_id": proj_id},
    )
    assert msg_task.status_code == 201
    assert msg_task.json()["task"]["source_chat_id"] == chat["id"]

    msg_ev = client.post(
        f"/api/messaging/chats/{chat['id']}/agenda-event",
        json={
            "title": "Visita técnica Mercado Bom",
            "kind": "visit",
            "start_at": datetime.now().isoformat(),
        },
    )
    assert msg_ev.status_code == 201
    assert msg_ev.json()["messaging_chat_id"] == chat["id"]

    # Isolamento entre usuários.
    assert login(client, outro.email).status_code == 200
    assert client.get(f"/api/work/projects/{proj_id}").status_code == 404
    assert client.delete(f"/api/agenda/events/{msg_ev.json()['id']}").status_code == 404

    # Governança: bloqueio por usuário em Projetos e bloqueio global em Agenda.
    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{dono.id}/permissions",
            json={"blocked_resources": ["projetos"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/admin/governance",
            json={"global_blocked_resources": ["agenda"]},
        ).status_code
        == 200
    )

    assert login(client, dono.email).status_code == 200
    assert client.get("/api/work/projects").status_code == 403
    assert client.post(f"/api/crm/deals/{deal['id']}/create-project").status_code == 403
    assert (
        client.post(
            f"/api/messaging/chats/{chat['id']}/work-task",
            json={"title": "Teste bloqueado"},
        ).status_code
        == 403
    )
    assert client.get("/api/agenda/timeline").status_code == 403

    assert login(client, adm.email).status_code == 200
    assert client.get("/api/work/projects").status_code == 200
    assert client.get("/api/agenda/timeline").status_code == 200


def test_agenda_range_cap_no_budget_month_creation_blocked_layers_and_idor_links(
    client: TestClient, db: Session, outbox: list
) -> None:
    from app.models import BudgetMonth

    adm = _make_user(client, db, outbox, "adm-agenda-c3@example.com", is_admin=True)
    dono = _make_user(client, db, outbox, "dono-agenda-c3@example.com")
    outro = _make_user(client, db, outbox, "outro-agenda-c3@example.com")

    # Dados privados do outro usuário para tentar vincular em C6.
    assert login(client, outro.email).status_code == 200
    outro_contact = client.post("/api/crm/contacts", json={"name": "Contato Alheio"}).json()
    outro_deal = client.post("/api/crm/deals", json={"title": "Deal Alheio", "value": "100"}).json()
    outro_doc = client.post(
        "/api/proposals",
        json={
            "customer_name": "Cli Alheio",
            "items": [{"name": "Item", "qty": 1, "unit_price": "10"}],
        },
    ).json()
    outro_proj = client.post(
        "/api/work/projects", json={"name": "Projeto Alheio", "link_budget_tag": False}
    ).json()
    outro_chat = client.post("/api/messaging/chats", json={"phone": "5511933332222"}).json()

    assert login(client, dono.email).status_code == 200
    # C3: período maior que 92 dias retorna 400 periodo_longo.
    long_res = client.get("/api/agenda/timeline?start=2026-01-01&end=2027-01-01")
    assert long_res.status_code == 400
    assert long_res.json()["error"] == "periodo_longo"

    # C3: abrir Agenda em meses futuros NÃO cria BudgetMonth no Meu Orçamento.
    future_tl = client.get("/api/agenda/timeline?start=2028-05-01&end=2028-06-01")
    assert future_tl.status_code == 200
    assert db.scalar(select(BudgetMonth).where(BudgetMonth.user_id == dono.id)) is None

    # C6: update_event e create_project rejeitam vínculos de outra conta (404).
    ev = client.post(
        "/api/agenda/events",
        json={"title": "Meu evento", "start_at": "2026-11-21T14:00:00"},
    ).json()
    assert (
        client.patch(
            f"/api/agenda/events/{ev['id']}", json={"contact_id": outro_contact["id"]}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/agenda/events/{ev['id']}", json={"project_id": outro_proj["id"]}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/agenda/events/{ev['id']}", json={"messaging_chat_id": outro_chat["id"]}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/work/projects",
            json={"name": "Tentativa", "crm_deal_id": outro_deal["id"]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/work/projects",
            json={"name": "Tentativa 2", "proposal_id": outro_doc["id"]},
        ).status_code
        == 404
    )

    # C4: camadas e bridges de soluções bloqueadas desaparecem da timeline e /hub/bridges.
    deal_dono = client.post(
        "/api/crm/deals",
        json={
            "title": "Fechamento Visível",
            "value": "500.00",
            "expected_close_date": "2026-11-21",
        },
    ).json()
    assert deal_dono["id"] is not None

    assert login(client, adm.email).status_code == 200
    assert (
        client.patch(
            f"/api/admin/users/{dono.id}/permissions",
            json={"blocked_resources": ["dashboard-crm", "projetos"], "storage_quota_mb": 50},
        ).status_code
        == 200
    )

    assert login(client, dono.email).status_code == 200
    tl_blocked = client.get("/api/agenda/timeline?start=2026-11-20&end=2026-11-22").json()
    assert tl_blocked["counts_by_layer"]["crm"] == 0
    assert tl_blocked["counts_by_layer"]["projects"] == 0
    bridges_blocked = client.get("/api/agenda/hub/bridges").json()
    assert bridges_blocked["contacts"] == []
    assert bridges_blocked["projects"] == []
