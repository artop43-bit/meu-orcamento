"""v0.9: caixa de mensagens, recados da administração, aparência na conta e começar do zero."""

import io
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.models import (
    BudgetMonth,
    Category,
    CategoryRule,
    CreditCard,
    Expense,
    Goal,
    InboxItem,
    Income,
    Investment,
    MoneyAccount,
    RecurringItem,
    SecurityEvent,
    StoredFile,
    SupportThread,
    User,
)
from app.services import budget as budget_service
from tests.conftest import PASSWORD, create_verified_user, login

MONTH = "2030-01"
INVESTMENT_KIND = "tesouro"
FIELD = "images"


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda *_: date(2030, 1, 1))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(out, "PNG")
    return out.getvalue()


def find(db: Session, email: str) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))  # type: ignore[return-value]


def as_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch, outbox, address: str) -> None:
    monkeypatch.setattr(get_settings(), "admin_emails", address)
    create_verified_user(client, outbox, address)
    client.post("/api/auth/logout")
    login(client, address)


def switch(client: TestClient, address: str) -> None:
    client.post("/api/auth/logout")
    login(client, address)


# ---------------------------------------------------------------- caixa de mensagens


def test_reply_lands_in_inbox_and_by_email(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    thread = client.post(
        "/api/support/threads",
        data={"title": "Exportar em PDF", "kind": "idea", "message": "Seria ótimo."},
    ).json()
    assert client.get("/api/inbox/unread").json() == {"unread": 0}

    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    sent = len(outbox)
    reply = client.post(
        f"/api/admin/support/threads/{thread['id']}/messages", data={"message": "Feito na 0.9!"}
    )
    assert reply.status_code == 200, reply.text
    copy = outbox[sent:]
    assert len(copy) == 1 and copy[0].to == "ana@example.com"
    assert "Exportar em PDF" in copy[0].subject and "Feito na 0.9!" in copy[0].body
    assert f"/mensagens/conversas/{thread['id']}" in copy[0].body
    assert copy[0].headers.get("List-Unsubscribe")

    switch(client, "ana@example.com")
    assert client.get("/api/inbox/unread").json() == {"unread": 1}
    [item] = client.get("/api/inbox").json()
    assert item["kind"] == "reply" and item["thread_id"] == thread["id"]
    assert item["read"] is False and item["body"] == "Feito na 0.9!"
    # Abrir a conversa marca a resposta como lida também na caixa.
    client.get(f"/api/support/threads/{thread['id']}")
    assert client.get("/api/inbox/unread").json() == {"unread": 0}
    # Marcar como não lida e depois "todas como lidas".
    assert client.patch(f"/api/inbox/{item['id']}", json={"read": False}).json()["read"] is False
    assert client.post("/api/inbox/read-all").json() == {"unread": 0}


def test_email_copy_can_be_turned_off(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    prefs = client.patch("/api/notifications/prefs", json={"notify_messages": False}).json()
    assert prefs["notify_messages"] is False
    thread = client.post(
        "/api/support/threads", data={"title": "Dúvida", "kind": "other", "message": "Olá"}
    ).json()
    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    sent = len(outbox)
    client.post(f"/api/admin/support/threads/{thread['id']}/messages", data={"message": "Oi!"})
    assert outbox[sent:] == []  # sem e-mail, mas a mensagem chega na caixa
    assert db.scalar(select(func.count()).select_from(InboxItem)) == 1


def test_inbox_is_private(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    thread = client.post(
        "/api/support/threads", data={"title": "Dúvida", "kind": "other", "message": "Olá"}
    ).json()
    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    client.post(f"/api/admin/support/threads/{thread['id']}/messages", data={"message": "Oi"})
    item_id = db.scalar(select(InboxItem.id))
    create_verified_user(client, outbox, "bia@example.com")
    switch(client, "bia@example.com")
    assert client.get("/api/inbox").json() == []
    assert client.patch(f"/api/inbox/{item_id}", json={"read": True}).status_code == 404


# ---------------------------------------------------------------- recados


def test_announcement_reaches_everyone_once(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for address in ("ana@example.com", "bia@example.com", "caio@example.com"):
        create_verified_user(client, outbox, address)
    with Session(db.get_bind()) as s:
        s.get(User, find(s, "caio@example.com").id).access_status = "pending"  # type: ignore[union-attr]
        s.commit()
    login(client, "ana@example.com")
    payload = {"title": "Manutenção", "body": "Sábado às 22h o app fica fora por 10 min."}
    assert client.post("/api/admin/announcements", json=payload).status_code == 403

    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    # Só contas aprovadas (ana, bia e o próprio admin); com a opção, também quem aguarda.
    assert client.get("/api/admin/announcements/audience").json() == {"recipients": 3}
    pending = client.get("/api/admin/announcements/audience?include_pending=true").json()
    assert pending == {"recipients": 4}
    blank = client.post("/api/admin/announcements", json={"title": "  ", "body": "x"})
    assert blank.status_code == 422

    sent = len(outbox)
    created = client.post("/api/admin/announcements", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["recipients"] == 3
    mails = outbox[sent:]
    expected = ["ana@example.com", "bia@example.com", "chefe@example.com"]
    assert sorted(m.to for m in mails) == expected
    assert all("/mensagens" in m.body and m.headers.get("List-Unsubscribe") for m in mails)

    switch(client, "bia@example.com")
    [item] = client.get("/api/inbox").json()
    assert item["kind"] == "announcement" and item["title"] == "Manutenção"
    client.patch(f"/api/inbox/{item['id']}", json={"read": True})

    switch(client, "chefe@example.com")
    [row] = client.get("/api/admin/announcements").json()
    assert row["recipients"] == 3 and row["read"] == 1


def test_important_announcement_is_pinned_and_always_emailed(
    client: TestClient,
    db: Session,
    outbox: list[OutgoingEmail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    client.patch("/api/notifications/prefs", json={"notify_messages": False})
    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    client.post("/api/admin/announcements", json={"title": "Comum", "body": "Recado comum."})
    sent = len(outbox)
    client.post(
        "/api/admin/announcements",
        json={"title": "Troca de senha", "body": "Atualize sua senha.", "important": True},
    )
    important = [m for m in outbox[sent:] if m.to == "ana@example.com"]
    assert len(important) == 1 and important[0].subject.startswith("Importante:")
    assert not important[0].headers.get("List-Unsubscribe")
    # Uma resposta mais nova não passa na frente do recado importante não lido.
    client.post("/api/admin/announcements", json={"title": "Mais novo", "body": "Depois."})
    switch(client, "ana@example.com")
    titles = [i["title"] for i in client.get("/api/inbox").json()]
    assert titles[0] == "Troca de senha"


def test_unsubscribe_messages_link(
    client: TestClient, db: Session, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    sent = len(outbox)
    client.post("/api/admin/announcements", json={"title": "Novidade", "body": "Versão nova."})
    mail = next(m for m in outbox[sent:] if m.to == "ana@example.com")
    token = mail.headers["List-Unsubscribe"].split("t=")[1].rstrip(">")
    out = client.post(f"/api/notifications/unsubscribe?t={token}")
    assert out.status_code == 200 and out.json()["kind"] == "messages"
    assert find(db, "ana@example.com").notify_messages is False


# ---------------------------------------------------------------- aparência


def test_appearance_is_saved_on_the_account(user: TestClient) -> None:
    assert user.get("/api/auth/me").json()["theme"] is None
    out = user.patch("/api/me/appearance", json={"theme": "dark", "accent": "roxo"})
    assert out.json() == {"theme": "dark", "accent": "roxo"}
    me = user.get("/api/auth/me").json()
    assert me["theme"] == "dark" and me["accent"] == "roxo"
    assert user.patch("/api/me/appearance", json={"theme": "neon"}).status_code == 422
    # Só o que foi enviado muda.
    assert user.patch("/api/me/appearance", json={"theme": "light"}).json()["accent"] == "roxo"


# ---------------------------------------------------------------- começar do zero


def fill(user: TestClient) -> dict[str, str]:
    account = user.post("/api/accounts", json={"name": "Nubank", "kind": "checking"}).json()
    card = user.post(
        "/api/cards",
        json={"name": "Roxinho", "kind": "credit", "closing_day": 5, "due_day": 12},
    ).json()
    cats = {c["name"]: c["id"] for c in user.get("/api/categories").json()}
    mine = user.post("/api/categories", json={"name": "Hobbies", "is_essential": False}).json()
    user.patch(f"/api/categories/{cats['Lazer']}", json={"monthly_limit": "300.00"})
    [expense] = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "Tinta acrílica", "amount": "40.00", "category_id": mine["id"]},
    ).json()
    receipt = user.post(
        f"/api/expenses/{expense['id']}/receipts", files=[(FIELD, ("n.png", png(), "image/png"))]
    )
    assert receipt.status_code == 201, receipt.text
    user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Cinema",
            "amount": "60.00",
            "category_id": cats["Lazer"],
            "account_id": account.get("id"),
        },
    )
    user.post(
        f"/api/months/{MONTH}/incomes",
        json={"description": "Salário", "amount": "3000.00", "repeat": "monthly"},
    )
    user.post("/api/goals", json={"name": "Viagem", "target_amount": "5000.00"})
    invest = user.post(
        "/api/investments",
        json={
            "name": "Tesouro Selic",
            "kind": INVESTMENT_KIND,
            "invested_amount": "1000.00",
            "current_value": "1010.00",
        },
    )
    assert invest.status_code == 201, invest.text
    assert account.get("id") and card.get("id"), (account, card)
    return {"account": account["id"], "card": card["id"], "custom": mine["id"]}


def count(db: Session, model, user_id) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) or 0


def test_reset_requires_password_and_confirmation(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    fill(user)
    base = {"areas": ["entries"], "password": PASSWORD, "confirmation": "COMEÇAR DO ZERO"}
    wrong = user.post("/api/account/reset", json={**base, "password": "errada123456"})
    assert wrong.status_code == 400 and wrong.json()["error"] == "wrong_password"
    typo = user.post("/api/account/reset", json={**base, "confirmation": "apagar"})
    assert typo.status_code == 400 and typo.json()["error"] == "wrong_confirmation"
    assert user.post("/api/account/reset", json={**base, "areas": []}).status_code == 422
    assert user.post("/api/account/reset", json={**base, "areas": ["tudo"]}).status_code == 422
    uid = find(db, "ana@example.com").id
    assert count(db, Expense, uid) == 2  # nada foi apagado


def test_reset_entries_only_keeps_the_rest(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    fill(user)
    preview = user.get("/api/account/reset").json()["counts"]
    assert preview["entries"] >= 3 and preview["goals"] == 1 and preview["categories"] == 1
    sent = len(outbox)
    out = user.post(
        "/api/account/reset",
        json={"areas": ["entries"], "password": PASSWORD, "confirmation": "começar do zero"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["removed"] == {"entries": preview["entries"]}
    uid = find(db, "ana@example.com").id
    assert count(db, Expense, uid) == 0 and count(db, Income, uid) == 0
    assert count(db, BudgetMonth, uid) == 0
    receipts = select(func.count()).select_from(StoredFile).where(StoredFile.purpose == "receipt")
    assert db.scalar(receipts) == 0
    # O resto continua: contas, cartões, metas, investimentos, recorrências e categorias.
    for model in (MoneyAccount, CreditCard, Goal, Investment, RecurringItem):
        assert count(db, model, uid) == 1, model
    assert db.scalar(select(Category).where(Category.name == "Hobbies")) is not None
    # Aviso por e-mail e registro de segurança.
    [mail] = outbox[sent:]
    assert mail.subject == "Dados apagados da sua conta" and "lançamentos" in mail.body
    assert db.scalar(select(SecurityEvent).where(SecurityEvent.event == "data_reset")) is not None
    # Recorrência continua: reabrir o mês lança o salário de novo.
    month = user.get(f"/api/months/{MONTH}").json()
    assert [i["description"] for i in month["incomes"]] == ["Salário"]


def test_reset_dependencies_are_resolved(user: TestClient, db: Session) -> None:
    ids = fill(user)
    out = user.post(
        "/api/account/reset",
        json={
            "areas": ["accounts", "cards", "categories", "recurring"],
            "password": PASSWORD,
            "confirmation": "COMEÇAR DO ZERO",
        },
    )
    assert out.status_code == 200, out.text
    uid = find(db, "ana@example.com").id
    db.expire_all()
    # Lançamentos ficam, sem conta/cartão; o que usava a categoria criada vira "Outros".
    expenses = {e.description: e for e in db.scalars(select(Expense).where(Expense.user_id == uid))}
    assert set(expenses) == {"Tinta acrílica", "Cinema"}
    assert all(e.account_id is None and e.card_id is None for e in expenses.values())
    other = db.scalar(select(Category).where(Category.user_id == uid, Category.name == "Outros"))
    assert expenses["Tinta acrílica"].category_id == other.id  # type: ignore[union-attr]
    assert db.scalar(select(Category).where(Category.id == uuid.UUID(ids["custom"]))) is None
    lazer = db.scalar(select(Category).where(Category.user_id == uid, Category.name == "Lazer"))
    assert lazer is not None and lazer.monthly_limit is None
    assert expenses["Cinema"].category_id == lazer.id
    assert count(db, Category, uid) == len(budget_service.DEFAULT_CATEGORIES)
    assert count(db, CategoryRule, uid) == 0
    assert count(db, RecurringItem, uid) == 0
    incomes = db.scalars(select(Income).where(Income.user_id == uid))
    assert all(i.recurring_id is None for i in incomes)
    assert count(db, MoneyAccount, uid) == 0 and count(db, CreditCard, uid) == 0
    assert count(db, Goal, uid) == 1  # não escolhido


def test_reset_everything_restarts_onboarding_and_keeps_account(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    fill(user)
    user.post("/api/support/threads", data={"title": "Dúvida", "kind": "other", "message": "Oi"})
    user.patch("/api/me/appearance", json={"theme": "dark"})
    user.post("/api/onboarding/done")
    areas = list(user.get("/api/account/reset").json()["counts"])
    out = user.post(
        "/api/account/reset",
        json={"areas": areas, "password": PASSWORD, "confirmation": "COMEÇAR DO ZERO"},
    )
    assert out.status_code == 200, out.text
    me = user.get("/api/auth/me").json()
    assert me["onboarded_at"] is None and me["theme"] == "dark"
    uid = find(db, "ana@example.com").id
    for model in (Expense, Income, MoneyAccount, CreditCard, Goal, Investment, RecurringItem):
        assert count(db, model, uid) == 0, model
    assert count(db, Category, uid) == len(budget_service.DEFAULT_CATEGORIES)
    assert count(db, SupportThread, uid) == 1  # solicitações nunca são apagadas
    # A sessão continua válida e o app abre um mês vazio normalmente.
    month = user.get(f"/api/months/{MONTH}")
    assert month.status_code == 200 and month.json()["expenses"] == []
