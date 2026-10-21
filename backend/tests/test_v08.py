"""v0.8: avisos por e-mail, novo acesso, metas com objetivo, comprovantes, importação única,
exportação filtrada, resumo anual e configuração inicial."""

import io
import json
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import OutgoingEmail
from app.models import Expense, Goal, GoalContribution, User
from app.services import budget as budget_service
from app.services import goals as goal_service
from app.services import notify
from tests.conftest import PASSWORD, create_verified_user, login

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def me(db: Session) -> User:
    return db.scalar(select(User).where(User.email == "ana@example.com"))  # type: ignore[return-value]


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (60, 40), "green").save(out, "PNG")
    return out.getvalue()


def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=TZ)


# ---------------------------------------------------------------- lembrete de vencimentos


def test_due_digest_once_a_day_with_everything_together(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    today = date.today()
    month = f"{today:%Y-%m}"
    for desc, offset in (("Aluguel", 3), ("Internet", 0), ("Academia", -1), ("Futuro", 10)):
        due = today + timedelta(days=offset)
        response = user.post(
            f"/api/months/{due:%Y-%m}/expenses",
            json={"description": desc, "amount": "100.00", "due_date": due.isoformat()},
        )
        assert response.status_code == 201, response.text
    user.post(
        f"/api/months/{month}/expenses",
        json={
            "description": "Já paga",
            "amount": "50.00",
            "due_date": today.isoformat(),
            "paid": True,
        },
    )
    outbox.clear()

    # Antes das 8h nada sai.
    assert notify.run_daily(db, at(today, 7)) == {"due": 0, "monthly": 0, "weekly": 0}
    sent = notify.run_daily(db, at(today, 8))
    assert sent["due"] == 1
    [mail] = [m for m in outbox if "conta" in m.subject.lower() or "atraso" in m.subject.lower()]
    assert "Aluguel" in mail.body and "Internet" in mail.body and "Academia" in mail.body
    assert "Futuro" not in mail.body and "Já paga" not in mail.body
    assert "R$ 100,00" in mail.body
    assert mail.html and "Abrir no app" in mail.html
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    # Rodar de novo no mesmo dia (ou reiniciar o servidor) não duplica.
    assert notify.run_daily(db, at(today, 9))["due"] == 0


def test_due_digest_preferences_and_unsubscribe(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    assert user.get("/api/notifications/prefs").json() == {
        "notify_due": True,
        "notify_due_days": 3,
        "notify_hide_values": False,
        "notify_monthly": True,
        "notify_messages": True,
        "notify_alerts": True,
        "notify_weekly": True,
    }
    assert user.patch("/api/notifications/prefs", json={"notify_due_days": 2}).status_code == 422
    user.patch("/api/notifications/prefs", json={"notify_due_days": 7, "notify_hide_values": True})
    today = date.today()
    due = today + timedelta(days=7)
    user.post(
        f"/api/months/{due:%Y-%m}/expenses",
        json={"description": "IPVA", "amount": "900.00", "due_date": due.isoformat()},
    )
    outbox.clear()
    notify.run_daily(db, at(today, 8))
    [mail] = outbox
    assert "IPVA" in mail.body and "900" not in mail.body  # valores ocultos

    token = re.search(r"descadastrar\?t=([\w.-]+)", mail.body).group(1)  # type: ignore[union-attr]
    # Descadastro com um clique: sem login e sem o cabeçalho anti-CSRF (provedor de e-mail).
    anonymous = TestClient(user.app)
    assert anonymous.post(f"/api/notifications/unsubscribe?t={token}").status_code == 200
    db.expire_all()
    assert me(db).notify_due is False
    assert anonymous.post("/api/notifications/unsubscribe?t=falso.due.x").status_code == 400


def test_card_purchases_come_through_the_invoice(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    today = date.today()
    card = user.post(
        "/api/cards",
        json={"name": "Roxo", "kind": "credit", "closing_day": 1, "due_day": today.day},
    ).json()
    purchase = today - timedelta(days=40)
    user.post(
        f"/api/months/{purchase:%Y-%m}/expenses",
        json={
            "description": "Tênis",
            "amount": "300.00",
            "card_id": card["id"],
            "purchase_date": purchase.isoformat(),
        },
    )
    outbox.clear()
    notify.run_daily(db, at(today, 8))
    bodies = " ".join(m.body for m in outbox)
    assert "Tênis" not in bodies  # a compra não aparece solta...
    if outbox:
        assert "Fatura Roxo" in bodies  # ...e sim a fatura


def test_monthly_summary_on_day_one(
    user: TestClient, db: Session, outbox: list[OutgoingEmail]
) -> None:
    today = date.today()
    first = today.replace(day=1)
    previous = (first - timedelta(days=1)).replace(day=1)
    user.post(
        f"/api/months/{previous:%Y-%m}/incomes",
        json={"description": "Salário", "amount": "5000.00"},
    )
    user.post(
        f"/api/months/{previous:%Y-%m}/expenses",
        json={"description": "Aluguel", "amount": "2000.00", "paid": True},
    )
    outbox.clear()
    notify.run_daily(db, at(first, 8))
    [mail] = [m for m in outbox if "resumo" in m.subject.lower()]
    assert "Taxa de poupança" in mail.body and "60,0%" in mail.body
    assert notify.run_daily(db, at(first, 10))["monthly"] == 0


# ---------------------------------------------------------------- novo acesso


def test_new_device_alert_and_not_me(client: TestClient, outbox: list[OutgoingEmail]) -> None:
    create_verified_user(client, outbox)
    windows = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"}
    iphone = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Version/17.0 Safari/604.1"}
    outbox.clear()
    client.post(
        "/api/auth/login", json={"email": "ana@example.com", "password": PASSWORD}, headers=windows
    )
    assert outbox == []  # primeiro aparelho: nada a avisar
    client.post(
        "/api/auth/login", json={"email": "ana@example.com", "password": PASSWORD}, headers=windows
    )
    assert outbox == []  # aparelho conhecido
    client.post(
        "/api/auth/login", json={"email": "ana@example.com", "password": PASSWORD}, headers=iphone
    )
    [alert] = outbox
    assert alert.subject == "Meu Orçamento: novo acesso à sua conta"
    assert "Safari no iPhone" in alert.body
    token = re.search(r"nao-fui-eu\?token=([\w-]+)", alert.body).group(1)  # type: ignore[union-attr]

    response = client.post("/api/auth/not-me", json={"token": token})
    assert response.status_code == 200
    # Todas as sessões foram encerradas.
    assert client.get("/api/auth/me").status_code == 401
    reset = response.json()["reset_token"]
    changed = client.post(
        "/api/auth/reset-password", json={"token": reset, "password": "nova-senha-forte-456"}
    )
    assert changed.status_code == 200, changed.text
    assert client.post("/api/auth/not-me", json={"token": token}).status_code == 400  # uso único


# ---------------------------------------------------------------- metas


def test_goal_objective_projection_and_main(user: TestClient, db: Session) -> None:
    today = date.today()
    goal = user.post(
        "/api/goals",
        json={
            "name": "Cirurgia ortopédica",
            "target_amount": "6000.00",
            "kind": "health",
            "motivation": "Voltar a correr sem dor",
            "monthly_plan": "1000.00",
        },
    ).json()
    assert goal["is_main"] is True  # primeira meta vira a principal
    assert goal["projection"]["status"] == "estimate"
    assert goal["projection"]["pace_source"] == "plan"
    assert goal["projection"]["months_needed"] == 6
    assert (
        user.post(
            "/api/goals", json={"name": "X", "target_amount": "1", "kind": "foguete"}
        ).status_code
        == 422
    )

    # Com prazo curto demais: abaixo do ritmo, com o valor mensal necessário.
    deadline = (today.replace(day=1) + timedelta(days=95)).replace(day=1)
    behind = user.patch(
        f"/api/goals/{goal['id']}", json={"target_date": deadline.isoformat()}
    ).json()
    assert behind["projection"]["status"] == "behind"
    assert Decimal(behind["projection"]["required_monthly"]) == Decimal("2000.00")

    # Aportes viram ritmo; ao chegar no valor, a meta é concluída.
    user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "6000.00"})
    done = next(g for g in user.get("/api/goals").json() if g["id"] == goal["id"])
    assert done["projection"]["status"] == "completed" and done["completed_at"]
    goal_id = uuid.UUID(goal["id"])
    assert db.scalar(select(GoalContribution).where(GoalContribution.goal_id == goal_id))

    second = user.post(
        "/api/goals", json={"name": "Viagem", "target_amount": "3000.00", "is_main": True}
    ).json()
    goals = {g["name"]: g["is_main"] for g in user.get("/api/goals").json()}
    assert goals == {"Cirurgia ortopédica": False, "Viagem": True}
    assert second["projection"]["status"] in ("no_pace", "estimate")


def test_goal_pace_from_contributions(user: TestClient, db: Session) -> None:
    goal = user.post("/api/goals", json={"name": "Notebook", "target_amount": "5000.00"}).json()
    row = db.get(Goal, uuid.UUID(goal["id"]))
    assert row is not None
    row.created_at = row.created_at - timedelta(days=120)
    db.commit()
    for _ in range(3):
        user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "500.00"})
    projected = goal_service.projection(db, me(db), db.get(Goal, row.id))  # type: ignore[arg-type]
    assert projected["pace_source"] == "contributions"
    assert projected["pace"] == Decimal("500.00")
    assert projected["months_needed"] == 7  # faltam 3.500


def test_goal_suggestion_needs_surplus(user: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    month = f"{date.today():%Y-%m}"
    assert user.get("/api/goals/suggestion").json() is None
    user.post(
        "/api/goals", json={"name": "Reserva", "target_amount": "10000.00", "kind": "emergency"}
    )
    user.post(f"/api/months/{month}/incomes", json={"description": "Salário", "amount": "5000.00"})
    user.post(f"/api/months/{month}/expenses", json={"description": "Contas", "amount": "4200.00"})
    suggestion = user.get("/api/goals/suggestion").json()
    assert suggestion["goal_name"] == "Reserva"
    assert Decimal(suggestion["surplus"]) == Decimal("800.00")
    assert Decimal(suggestion["amount"]) == Decimal("400")


def test_goal_image_is_private(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    goal = client.post(
        "/api/goals", json={"name": "Carro", "target_amount": "40000.00", "kind": "vehicle"}
    ).json()
    saved = client.put(
        f"/api/goals/{goal['id']}/image", files={"image": ("c.png", png(), "image/png")}
    ).json()
    assert saved["image_id"]
    assert client.get(f"/api/files/{saved['image_id']}").status_code == 200
    client.post("/api/auth/logout")
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    create_verified_user(client, outbox, "chefe@example.com")
    login(client, "chefe@example.com")
    assert client.get(f"/api/files/{saved['image_id']}").status_code == 404  # nem a administração


# ---------------------------------------------------------------- comprovantes


def test_receipts_on_expense(user: TestClient) -> None:
    month = f"{date.today():%Y-%m}"
    [expense] = user.post(
        f"/api/months/{month}/expenses", json={"description": "Farmácia", "amount": "35.00"}
    ).json()
    added = user.post(
        f"/api/expenses/{expense['id']}/receipts",
        files=[
            ("images", ("r.png", png(), "image/png")),
            ("images", ("r2.png", png(), "image/png")),
        ],
    )
    assert added.status_code == 201, added.text
    ids = added.json()["receipt_ids"]
    assert len(ids) == 2
    listed = next(
        e for e in user.get(f"/api/months/{month}").json()["expenses"] if e["id"] == expense["id"]
    )
    assert listed["receipt_ids"] == ids
    too_many = user.post(
        f"/api/expenses/{expense['id']}/receipts",
        files=[("images", (f"{i}.png", png(), "image/png")) for i in range(2)],
    )
    assert too_many.json()["error"] == "too_many_files"
    gif = io.BytesIO()
    Image.new("RGB", (5, 5)).save(gif, "GIF")
    assert (
        user.post(
            f"/api/expenses/{expense['id']}/receipts",
            files=[("images", ("a.gif", gif.getvalue(), "image/gif"))],
        ).json()["error"]
        == "invalid_image"
    )
    assert user.delete(f"/api/expenses/{expense['id']}/receipts/{ids[0]}").status_code == 204
    assert user.get(f"/api/files/{ids[0]}").status_code == 404


# ---------------------------------------------------------------- importação única


CSV_ODD_HEADER = (
    "Extrato da conta\n"
    "Período: 01/09/2026 a 30/09/2026\n"
    "Data Lançamento;Histórico;Valor (R$);Saldo\n"
    "02/09/2026;UBER *TRIP;-23,50;976,50\n"
    "05/09/2026;SALARIO EMPRESA;3.200,00;4.176,50\n"
    "06/09/2026;Saldo do dia;0,00;4.176,50\n"
    "08/09/2026;PAG*IFOOD;-58,90;4.117,60\n"
)


def upload(client: TestClient, path: str, name: str, raw: bytes, **data: Any):  # type: ignore[no-untyped-def]
    return client.post(
        path, files={"file": (name, raw, "application/octet-stream")}, data=data or None
    )


def test_import_detects_columns_previews_commits_and_undoes(user: TestClient) -> None:
    raw = CSV_ODD_HEADER.encode("cp1252")
    analysis = upload(user, "/api/import/analyze", "extrato.txt", raw).json()
    assert analysis["format"] == "csv" and analysis["kind"] == "account" and analysis["ready"]
    mapping = analysis["mapping"]
    assert analysis["columns"][mapping["date"]] == "Data Lançamento"
    assert analysis["columns"][mapping["description"]] == "Histórico"
    assert analysis["columns"][mapping["amount"]] == "Valor (R$)"

    preview = upload(
        user, "/api/import/preview", "extrato.txt", raw, mapping=json.dumps(mapping)
    ).json()
    items = preview["transactions"]
    assert [(i["description"], i["kind"]) for i in items] == [
        ("UBER *TRIP", "expense"),
        ("SALARIO EMPRESA", "income"),
        ("PAG*IFOOD", "expense"),
    ]
    account = user.post("/api/accounts", json={"name": "Conta corrente", "kind": "checking"}).json()
    payload = {
        "transactions": [
            {k: i[k] for k in ("ref", "date", "description", "amount", "kind", "category_id")}
            for i in items
        ],
        "filename": "extrato.txt",
        "file_format": "csv",
        "account_id": account["id"],
        "save_mapping": {"signature": analysis["signature"], "mapping": mapping},
    }
    result = user.post("/api/import/commit", json=payload).json()
    assert (result["created"], result["skipped"]) == (3, 0)
    again = user.post("/api/import/commit", json=payload).json()
    assert (again["created"], again["skipped"]) == (0, 3)  # repetidos não entram
    month = user.get("/api/months/2026-09").json()
    assert {e["account_id"] for e in month["expenses"]} == {account["id"]}
    # O mapeamento confirmado fica salvo para o mesmo modelo de arquivo.
    assert (
        upload(user, "/api/import/analyze", "extrato.txt", raw).json()["mapping_source"] == "saved"
    )

    [batch] = [b for b in user.get("/api/import/batches").json() if b["count"] == 3]
    assert user.post(f"/api/import/batches/{batch['id']}/undo").json() == {"removed": 3}
    assert user.get("/api/months/2026-09").json()["expenses"] == []
    assert user.post(f"/api/import/batches/{batch['id']}/undo").status_code == 400


def test_import_xlsx_without_known_headers_and_card_statement(user: TestClient) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Quando", "O que", "Quanto"])
    sheet.append([datetime(2026, 9, 3), "Mercado Pão de Açúcar", 182.4])
    sheet.append([datetime(2026, 9, 5), "Posto Shell", 150])
    sheet.append([datetime(2026, 9, 9), "Netflix", 55.9])
    sheet.append([datetime(2026, 9, 12), "Farmácia", 35])
    sheet.append([datetime(2026, 9, 15), "Pagamento recebido", -500])
    out = io.BytesIO()
    workbook.save(out)
    analysis = upload(user, "/api/import/analyze", "fatura-setembro.xlsx", out.getvalue()).json()
    assert analysis["format"] == "xlsx" and analysis["ready"]
    assert analysis["kind"] == "card" and analysis["invert"] is True
    assert analysis["sample"][0][0] == "03/09/2026"
    preview = upload(
        user,
        "/api/import/preview",
        "fatura-setembro.xlsx",
        out.getvalue(),
        mapping=json.dumps(analysis["mapping"]),
        invert="true",
    ).json()
    mercado = next(i for i in preview["transactions"] if i["description"].startswith("Mercado"))
    assert mercado["kind"] == "expense" and mercado["amount"] == "182.40"

    card = user.post("/api/cards", json={"name": "Azul", "closing_day": 1, "due_day": 10}).json()
    items = [
        {k: i[k] for k in ("ref", "date", "description", "amount", "kind", "category_id")}
        for i in preview["transactions"]
        if i["kind"] == "expense"
    ]
    result = user.post(
        "/api/import/commit",
        json={
            "transactions": items,
            "filename": "fatura.xlsx",
            "file_format": "xlsx",
            "card_id": card["id"],
        },
    ).json()
    assert result["created"] == 4
    invoice = {i["month"]: i for i in user.get(f"/api/cards/{card['id']}/invoices").json()}
    assert Decimal(invoice["2026-10"]["total"]) == Decimal("423.30")


def test_import_rejects_pdf_and_recognizes_json(user: TestClient) -> None:
    pdf = upload(user, "/api/import/analyze", "extrato.pdf", b"%PDF-1.4 ...")
    assert pdf.status_code == 400 and "OFX" in pdf.json()["message"]
    legacy = upload(
        user, "/api/import/analyze", "x.json", json.dumps({"bills": [], "incomes": []}).encode()
    )
    assert legacy.json()["kind"] == "legacy"
    other = upload(user, "/api/import/analyze", "x.json", b'{"a": 1}')
    assert other.status_code == 400
    ofx = (
        "OFXHEADER:100\n<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><BANKTRANLIST>"
        "<STMTTRN><DTPOSTED>20260910<TRNAMT>-80.00<FITID>1<MEMO>Restaurante</STMTTRN>"
        "</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>"
    )
    card = upload(user, "/api/import/analyze", "fatura.ofx", ofx.encode()).json()
    assert (card["format"], card["kind"], card["count"]) == ("ofx", "card", 1)


def test_backup_restore_into_new_account(client: TestClient, outbox: list[OutgoingEmail]) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    client.post("/api/months/2026-09/incomes", json={"description": "Salário", "amount": "4000.00"})
    client.post(
        "/api/months/2026-09/expenses",
        json={
            "description": "Aluguel",
            "amount": "1500.00",
            "category_id": next(
                c["id"] for c in client.get("/api/categories").json() if c["name"] == "Moradia"
            ),
        },
    )
    client.post("/api/goals", json={"name": "Viagem", "target_amount": "3000.00"})
    backup = client.get("/api/export/backup").content
    client.post("/api/auth/logout")

    create_verified_user(client, outbox, "bia@example.com")
    login(client, "bia@example.com")
    restored = client.post(
        "/api/import/restore", files={"file": ("backup.json", backup, "application/json")}
    )
    assert restored.status_code == 200, restored.text
    # A Bia é outra conta: os registros da Ana já existem (mesmos identificadores) e não vazam.
    assert restored.json()["incomes"] == 0

    client.post("/api/auth/logout")
    login(client, "ana@example.com")
    assert client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 204
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    restored = client.post(
        "/api/import/restore", files={"file": ("backup.json", backup, "application/json")}
    ).json()
    assert restored["incomes"] == 1 and restored["expenses"] == 1 and restored["goals"] == 1
    month = client.get("/api/months/2026-09").json()
    aluguel = next(e for e in month["expenses"] if e["description"] == "Aluguel")
    moradia = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Moradia")
    assert aluguel["category_id"] == moradia  # unificada com a categoria nova de mesmo nome
    again = client.post(
        "/api/import/restore", files={"file": ("backup.json", backup, "application/json")}
    ).json()
    assert again["incomes"] == 0  # restaurar de novo não duplica


# ---------------------------------------------------------------- exportação e boas-vindas


def test_annual_summary(user: TestClient) -> None:
    user.post("/api/months/2026-03/incomes", json={"description": "Salário", "amount": "5000.00"})
    user.post("/api/months/2026-03/expenses", json={"description": "Aluguel", "amount": "2000.00"})
    data = user.get("/api/export/annual?year=2026").json()
    assert Decimal(data["income"]) == Decimal("5000.00")
    assert data["savings_rate"] == 60.0
    assert data["by_category"][0]["name"] in ("Moradia", "Sem categoria")
    assert len(data["months"]) == 12
    assert user.get("/api/export/annual?year=1990").status_code == 422


def test_onboarding_flag(user: TestClient, db: Session) -> None:
    assert user.get("/api/auth/me").json()["onboarded_at"] is None
    assert user.post("/api/onboarding/done").json() == {"done": True}
    assert user.get("/api/auth/me").json()["onboarded_at"] is not None


def test_demo_and_expense_model_untouched(db: Session) -> None:
    # Sanidade: a coluna nova de lote não é obrigatória.
    assert Expense.__table__.columns["import_batch_id"].nullable
    assert budget_service.ZERO == Decimal("0.00")
