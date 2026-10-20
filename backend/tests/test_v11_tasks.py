"""v1.1: solicitações numeradas como tarefas e respostas aos recados da administração."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.models import InboxItem, SupportThread
from tests.conftest import create_verified_user, login


def new_thread(client: TestClient, title: str, kind: str = "idea") -> dict:
    response = client.post(
        "/api/support/threads", data={"title": title, "kind": kind, "message": "Detalhes."}
    )
    assert response.status_code == 201, response.text
    return response.json()


def switch(client: TestClient, address: str) -> None:
    client.post("/api/auth/logout")
    login(client, address)


@pytest.fixture
def people(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    for address in ("ana@example.com", "chefe@example.com"):
        create_verified_user(client, outbox, address)
    login(client, "ana@example.com")
    return client


def test_threads_are_numbered_in_order(people: TestClient) -> None:
    first = new_thread(people, "Exportar em PDF")
    second = new_thread(people, "Erro no gráfico", "bug")
    assert (first["number"], second["number"]) == (1, 2)
    mine = people.get("/api/support/threads").json()
    assert sorted(t["number"] for t in mine) == [1, 2]


def test_status_as_task_notifies_and_filters(
    people: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    idea = new_thread(people, "Modo escuro automático")
    bug = new_thread(people, "Botão cortado", "bug")
    switch(people, "chefe@example.com")
    sent = len(outbox)
    out = people.patch(
        f"/api/admin/support/threads/{idea['id']}",
        json={"status": "planned", "note": "Entra na versão 1.2.", "version": "1.2"},
    )
    assert out.status_code == 200, out.text
    data = out.json()
    assert data["status"] == "planned" and data["planned_version"] == "1.2"
    assert data["status_note"] == "Entra na versão 1.2."
    # A pessoa recebe na caixa e por e-mail, com o número da tarefa.
    [mail] = outbox[sent:]
    assert "#1" in mail.subject and "Planejada" in mail.subject
    item = db.scalar(select(InboxItem).where(InboxItem.title.like("Solicitação #1%")))
    assert item is not None and "versão 1.2" in item.title
    # Mudar só a versão de novo (mesmo status e nota) não repete o aviso.
    people.patch(
        f"/api/admin/support/threads/{idea['id']}",
        json={"status": "planned", "note": "Entra na versão 1.2.", "version": "1.2"},
    )
    assert len(outbox) == sent + 1
    people.patch(f"/api/admin/support/threads/{bug['id']}", json={"status": "in_progress"})
    # Filtros e busca pelo número.
    assert [t["number"] for t in people.get("/api/admin/support/threads?kind=bug").json()] == [2]
    assert [t["number"] for t in people.get("/api/admin/support/threads?version=1.2").json()] == [1]
    assert [t["number"] for t in people.get("/api/admin/support/threads?q=%232").json()] == [2]
    assert people.get("/api/admin/support/versions").json() == ["1.2"]
    counts = people.get("/api/admin/support/counts").json()
    assert counts["planned"] == 1 and counts["in_progress"] == 1
    bad = people.patch(f"/api/admin/support/threads/{bug['id']}", json={"status": "parada"})
    assert bad.status_code == 422


def test_reply_to_announcement_becomes_conversation(
    people: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    switch(people, "chefe@example.com")
    people.post("/api/admin/announcements", json={"title": "Bom dia amigos!", "body": "Novidades."})
    switch(people, "ana@example.com")
    [item] = [i for i in people.get("/api/inbox").json() if i["kind"] == "announcement"]
    reply = people.post(f"/api/inbox/{item['id']}/reply", data={"message": "Obrigada!"})
    assert reply.status_code == 200, reply.text
    thread = reply.json()
    assert thread["title"] == "Resposta ao recado: Bom dia amigos!"
    assert thread["announcement_id"] and thread["number"] == 1
    # Responder de novo continua a mesma conversa.
    again = people.post(f"/api/inbox/{item['id']}/reply", data={"message": "Mais uma coisa."})
    assert again.json()["id"] == thread["id"] and len(again.json()["messages"]) == 2
    # A administração vê a conversa e quantos responderam o recado.
    switch(people, "chefe@example.com")
    [row] = people.get("/api/admin/support/threads").json()
    assert row["announcement_id"] == thread["announcement_id"] and row["unread"] is True
    [announcement] = people.get("/api/admin/announcements").json()
    assert announcement["replies"] == 1
    # Ninguém responde em nome de outra pessoa nem a itens que não são recados.
    assert people.post(f"/api/inbox/{item['id']}/reply", data={"message": "x"}).status_code == 404


def test_numbers_survive_alongside_existing_threads(people: TestClient, db: Session) -> None:
    new_thread(people, "Primeira")
    db.expire_all()
    thread = db.scalar(select(SupportThread))
    assert thread is not None and thread.number == 1
