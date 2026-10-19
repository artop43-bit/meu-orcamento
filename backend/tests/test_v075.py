"""v0.7.5: solicitações em conversa com imagens, perfil, cartão de débito e dia válido no mês."""

import io
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.services import budget as budget_service
from app.services import profile as profile_service
from tests.conftest import create_verified_user, login

MONTH = "2030-01"


@pytest.fixture(autouse=True)
def fixed_current_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_service, "current_month", lambda: date(2030, 1, 1))
    monkeypatch.setattr(profile_service, "current_month", lambda: date(2030, 1, 1))


@pytest.fixture
def user(client: TestClient, outbox: list[OutgoingEmail]) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def png(size: tuple[int, int] = (40, 30), color: str = "red") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (64, 48), "blue")
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (19.0, 55.0, 0.0)}  # GPSInfo
    exif[0x010F] = "Câmera do celular"
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def animated_gif() -> bytes:
    frames = [Image.new("RGB", (20, 20), color) for color in ("red", "green", "blue")]
    out = io.BytesIO()
    frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return out.getvalue()


def new_thread(client: TestClient, files: list[tuple[str, bytes]] | None = None, **data: Any):
    form = {
        "title": "Gráfico não carrega",
        "kind": "bug",
        "message": "Na tela de Insights.",
        **data,
    }
    uploads = [("images", (name, raw, "application/octet-stream")) for name, raw in files or []]
    return client.post("/api/support/threads", data=form, files=uploads or None)


def as_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch, outbox, address: str) -> None:
    monkeypatch.setattr(get_settings(), "admin_emails", address)
    create_verified_user(client, outbox, address)
    client.post("/api/auth/logout")
    login(client, address)


# ---------------------------------------------------------------- imagens


def test_images_are_validated_and_cleaned(user: TestClient) -> None:
    # Texto com extensão de imagem não passa: o tipo é conferido abrindo o arquivo.
    fake = new_thread(user, [("foto.png", b"isto nao e uma imagem")])
    assert fake.status_code == 400 and fake.json()["error"] == "invalid_image"
    # Mais de 3 imagens por mensagem.
    many = new_thread(user, [(f"{i}.png", png()) for i in range(4)])
    assert many.status_code == 400 and many.json()["error"] == "too_many_files"
    # Acima de 5 MB.
    big = new_thread(user, [("big.png", b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10))])
    assert big.status_code == 413
    # Nada foi criado com os envios recusados.
    assert user.get("/api/support/threads").json() == []

    ok = new_thread(user, [("gps.jpg", jpeg_with_gps()), ("print.png", png())])
    assert ok.status_code == 201, ok.text
    detail = user.get(f"/api/support/threads/{ok.json()['id']}").json()
    [photo, shot] = detail["messages"][0]["attachments"]
    raw = user.get(f"/api/files/{photo['id']}")
    assert raw.status_code == 200 and raw.headers["content-type"] == "image/jpeg"
    assert raw.headers["x-content-type-options"] == "nosniff"
    # O EXIF (com a localização GPS) foi removido.
    with Image.open(io.BytesIO(raw.content)) as image:
        assert not image.getexif()
    assert user.get(f"/api/files/{shot['id']}").headers["content-type"] == "image/png"


def test_files_are_private(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    create_verified_user(client, outbox, "bia@example.com")
    login(client, "ana@example.com")
    thread = new_thread(client, [("a.png", png())]).json()
    file_id = client.get(f"/api/support/threads/{thread['id']}").json()["messages"][0][
        "attachments"
    ][0]["id"]
    client.post("/api/auth/logout")
    login(client, "bia@example.com")
    # Outra pessoa não vê a conversa nem a imagem (e não descobre que existem).
    assert client.get(f"/api/support/threads/{thread['id']}").status_code == 404
    assert client.get(f"/api/files/{file_id}").status_code == 404
    client.post("/api/auth/logout")
    assert client.get(f"/api/files/{file_id}").status_code == 401
    # A administração vê.
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    assert client.get(f"/api/files/{file_id}").status_code == 200


# ---------------------------------------------------------------- solicitações


def test_thread_conversation_flow(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    create_verified_user(client, outbox, "ana@example.com")
    login(client, "ana@example.com")
    assert client.get("/api/admin/support/threads").status_code == 403
    thread = new_thread(client).json()
    assert thread["status"] == "open" and thread["unread"] is False

    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    assert client.get("/api/admin/overview").json()["feedback_new"] == 1
    [row] = client.get("/api/admin/support/threads").json()
    assert row["unread"] is True and row["user"]["email"] == "ana@example.com"
    assert row["messages_count"] == 1
    # Responder com imagem: vira "respondida" e o usuário tem algo não lido.
    reply = client.post(
        f"/api/admin/support/threads/{row['id']}/messages",
        data={"message": "Corrigido na próxima versão. Veja o print."},
        files=[("images", ("r.png", png(), "image/png"))],
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "answered"
    assert client.get("/api/admin/support/counts").json() == {
        "open": 0,
        "answered": 1,
        "resolved": 0,
        "unread": 0,
    }

    client.post("/api/auth/logout")
    login(client, "ana@example.com")
    assert client.get("/api/support/unread").json() == {"unread": 1}
    [mine] = client.get("/api/support/threads").json()
    assert mine["unread"] is True and mine["status"] == "answered"
    detail = client.get(f"/api/support/threads/{mine['id']}").json()
    assert [m["from_admin"] for m in detail["messages"]] == [False, True]
    # A imagem da resposta da administração abre para o dono da conversa.
    admin_file = detail["messages"][1]["attachments"][0]["id"]
    assert client.get(f"/api/files/{admin_file}").status_code == 200
    assert client.get("/api/support/unread").json() == {"unread": 0}
    # Encerrar e reabrir com nova mensagem.
    assert client.post(f"/api/support/threads/{mine['id']}/resolve").json()["status"] == "resolved"
    again = client.post(
        f"/api/support/threads/{mine['id']}/messages", data={"message": "Voltou a acontecer."}
    ).json()
    assert again["status"] == "open" and len(again["messages"]) == 3

    client.post("/api/auth/logout")
    login(client, "chefe@example.com")
    changed = client.patch(f"/api/admin/support/threads/{mine['id']}", json={"status": "resolved"})
    assert changed.json()["status"] == "resolved"


def test_admin_views_and_search(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> None:
    for address, title, message in (
        ("ana@example.com", "Exportar em PDF", "Seria ótimo ter o relatório anual."),
        ("bia@example.com", "Erro no cartão", "A fatura não fecha no dia certo."),
        ("ana@example.com", "Tema escuro", "As cores do gráfico ficam apagadas."),
    ):
        if address == "ana@example.com" and title != "Exportar em PDF":
            client.post("/api/auth/logout")
            login(client, address)
        else:
            create_verified_user(client, outbox, address)
            client.post("/api/auth/logout")
            login(client, address)
        assert new_thread(client, title=title, message=message, kind="idea").status_code == 201

    client.post("/api/auth/logout")
    as_admin(client, monkeypatch, outbox, "chefe@example.com")
    threads = client.get("/api/admin/support/threads").json()
    # Recentes: a última mensagem primeiro.
    assert [t["title"] for t in threads] == ["Tema escuro", "Erro no cartão", "Exportar em PDF"]
    # Busca no texto da mensagem, no título e no e-mail.
    assert [t["title"] for t in client.get("/api/admin/support/threads?q=fatura").json()] == [
        "Erro no cartão"
    ]
    assert len(client.get("/api/admin/support/threads?q=ANA@").json()) == 2
    # Por usuário.
    people = client.get("/api/admin/support/people").json()
    assert [(p["user"]["email"], p["total"], p["open"]) for p in people] == [
        ("ana@example.com", 2, 2),
        ("bia@example.com", 1, 1),
    ]
    bia = people[1]["user"]["id"]
    assert len(client.get(f"/api/admin/support/threads?user_id={bia}").json()) == 1
    # Por status.
    first = threads[0]["id"]
    client.patch(f"/api/admin/support/threads/{first}", json={"status": "resolved"})
    assert [
        t["title"] for t in client.get("/api/admin/support/threads?status=resolved").json()
    ] == ["Tema escuro"]
    assert client.get("/api/admin/support/threads?status=errado").status_code == 422


def test_thread_validation_and_legacy_feedback(user: TestClient) -> None:
    assert new_thread(user, title="ab").status_code == 422
    assert new_thread(user, kind="spam").status_code == 422
    assert new_thread(user, message="   ").status_code == 422
    # O botão antigo (abas abertas antes do update) continua funcionando.
    legacy = user.post("/api/feedback", json={"kind": "idea", "message": "Gostei muito\nDetalhes"})
    assert legacy.status_code == 201
    [thread] = user.get("/api/support/threads").json()
    assert thread["title"] == "Gostei muito" and thread["kind"] == "idea"


# ---------------------------------------------------------------- perfil


def test_profile_fields_images_and_prefs(user: TestClient) -> None:
    profile = user.get("/api/profile").json()
    assert profile["display_name"] is None and profile["avatar_id"] is None
    assert all(profile["prefs"]["stats"].values())
    assert profile["prefs"]["show_values_in_recap"] is False

    changed = user.patch(
        "/api/profile",
        json={
            "display_name": "  Ana Souza ",
            "city": "Belo Horizonte",
            "bio": "",
            "prefs": {
                "stats": {"avg_income": False, "inventado": True},
                "show_values_in_recap": True,
            },
        },
    ).json()
    assert changed["display_name"] == "Ana Souza" and changed["bio"] is None
    assert changed["prefs"]["stats"]["avg_income"] is False
    assert "inventado" not in changed["prefs"]["stats"]
    assert changed["prefs"]["show_values_in_recap"] is True
    assert user.patch("/api/profile", json={"display_name": "x" * 61}).status_code == 422

    first = user.put(
        "/api/profile/avatar", files={"image": ("a.png", png((900, 900)), "image/png")}
    )
    assert first.status_code == 200, first.text
    avatar = user.get(f"/api/files/{first.json()['avatar_id']}")
    with Image.open(io.BytesIO(avatar.content)) as image:
        assert max(image.size) <= 512  # reduzida
    # Trocar a foto apaga a anterior.
    second = user.put(
        "/api/profile/avatar", files={"image": ("b.gif", animated_gif(), "image/gif")}
    )
    assert second.json()["avatar_id"] != first.json()["avatar_id"]
    assert user.get(f"/api/files/{first.json()['avatar_id']}").status_code == 404
    gif = user.get(f"/api/files/{second.json()['avatar_id']}")
    assert gif.headers["content-type"] == "image/gif"
    with Image.open(io.BytesIO(gif.content)) as image:
        assert image.n_frames == 3  # a animação foi mantida

    banner = user.put(
        "/api/profile/banner", files={"image": ("c.jpg", jpeg_with_gps(), "image/jpeg")}
    )
    assert banner.json()["banner_id"] is not None
    assert (
        user.put("/api/profile/outro", files={"image": ("c.png", png(), "image/png")}).status_code
        == 422
    )
    assert user.delete("/api/profile/banner").json()["banner_id"] is None


def test_profile_summary_and_retrospective(user: TestClient) -> None:
    for month, income, rent in (
        ("2029-11", "5000.00", "2000.00"),
        ("2029-12", "5000.00", "6000.00"),
    ):
        user.post(f"/api/months/{month}/incomes", json={"description": "Salário", "amount": income})
        user.post(
            f"/api/months/{month}/expenses",
            json={"description": "Aluguel", "amount": rent, "category_id": None},
        )
    goal = user.post("/api/goals", json={"name": "Viagem", "target_amount": "1000.00"}).json()
    user.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "1000.00"})

    summary = user.get("/api/profile/summary").json()
    assert summary["months"] == 2
    assert summary["avg_income"] == "5000.00" and summary["avg_expenses"] == "4000.00"
    assert summary["savings_rate"] == 20.0
    assert summary["positive_months"] == 1 and summary["best_streak"] == 1
    assert summary["goals_completed"] == 1 and summary["goals_total"] == 1

    month = user.get("/api/profile/retrospective?period=month&month=2029-12").json()
    assert month["has_data"] is True and month["balance"] == "-1000.00"
    assert month["expenses_change_pct"] == 200.0
    assert month["top_category"]["share_pct"] == 100.0
    year = user.get("/api/profile/retrospective?period=year&year=2029").json()
    assert year["months_with_data"] == 2 and year["positive_months"] == 1
    assert year["best_month"]["month"] == "2029-11-01"
    assert year["show_values"] is False
    assert user.get("/api/profile/retrospective?period=year&year=1999").status_code == 422
    assert user.get("/api/profile/retrospective?period=month&month=2029-13").status_code in (
        400,
        422,
    )


# ---------------------------------------------------------------- cartões


def test_debit_card_never_uses_limit_or_invoice(user: TestClient) -> None:
    account = user.post(
        "/api/accounts",
        json={"name": "Conta corrente", "kind": "checking", "initial_balance": "1000.00"},
    ).json()
    # Crédito exige fechamento e vencimento.
    missing = user.post("/api/cards", json={"name": "Roxo", "kind": "credit"})
    assert missing.status_code == 400 and missing.json()["error"] == "card_days_required"
    credit = user.post(
        "/api/cards",
        json={
            "name": "Roxo",
            "kind": "credit",
            "limit_amount": "2000.00",
            "closing_day": 3,
            "due_day": 10,
        },
    ).json()
    debit = user.post(
        "/api/cards",
        json={
            "name": "Débito Inter",
            "kind": "debit",
            "closing_day": 5,
            "account_id": account["id"],
        },
    ).json()
    assert (debit["kind"], debit["closing_day"], debit["due_day"]) == ("debit", None, None)

    bought = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Mercado",
            "amount": "150.00",
            "debit_card_id": debit["id"],
            "purchase_date": "2030-01-08",
        },
    )
    assert bought.status_code == 201, bought.text
    [expense] = bought.json()
    assert expense["paid"] is True and expense["payment_method"] == "debit"
    assert expense["card_id"] is None and expense["debit_card_id"] == debit["id"]
    assert expense["account_id"] == account["id"] and expense["due_date"] == "2030-01-08"

    summary = {s["card"]["name"]: s for s in user.get("/api/cards").json()}
    assert summary["Roxo"]["used"] == "0.00"
    assert summary["Débito Inter"]["open_invoice"] is None
    assert user.get(f"/api/cards/{debit['id']}/invoices").status_code == 400
    # Débito no cartão só de crédito (e o contrário) é recusado.
    wrong = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "10.00", "debit_card_id": credit["id"]},
    )
    assert wrong.json()["error"] == "card_not_debit"
    wrong = user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "X", "amount": "10.00", "card_id": debit["id"]},
    )
    assert wrong.json()["error"] == "card_not_credit"
    both = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "X",
            "amount": "10.00",
            "card_id": credit["id"],
            "debit_card_id": debit["id"],
        },
    )
    assert both.json()["error"] == "card_conflict"
    parcel = user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "X",
            "amount": "10.00",
            "debit_card_id": debit["id"],
            "installments": 3,
        },
    )
    assert parcel.json()["error"] == "debit_no_installments"


def test_card_kind_change_keeps_invoices_safe(user: TestClient) -> None:
    card = user.post(
        "/api/cards", json={"name": "Azul", "kind": "both", "closing_day": 3, "due_day": 10}
    ).json()
    user.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "TV",
            "amount": "900.00",
            "card_id": card["id"],
            "purchase_date": "2030-01-05",
        },
    )
    blocked = user.patch(f"/api/cards/{card['id']}", json={"kind": "debit"})
    assert blocked.status_code == 400 and blocked.json()["error"] == "card_has_invoices"
    assert (
        user.patch(f"/api/cards/{card['id']}", json={"name": "Azul Plus"}).json()["kind"] == "both"
    )


# ---------------------------------------------------------------- dia válido no mês


def test_single_income_day_must_exist_in_month(user: TestClient) -> None:
    feb = "2027-02"
    wrong = user.post(
        f"/api/months/{feb}/incomes", json={"description": "Bônus", "amount": "100.00", "day": 31}
    )
    assert wrong.status_code == 400
    assert wrong.json()["message"] == "Fevereiro de 2027 tem 28 dias. Informe um dia entre 1 e 28."
    assert (
        user.post(
            f"/api/months/{feb}/incomes",
            json={"description": "Bônus", "amount": "100.00", "day": 28},
        ).status_code
        == 201
    )
    # Que se repete: 31 vale (nos meses curtos cai no último dia).
    monthly = user.post(
        f"/api/months/{feb}/incomes",
        json={"description": "Salário", "amount": "3000.00", "day": 31, "repeat": "monthly"},
    )
    assert monthly.status_code == 201, monthly.text
    assert (
        user.post(
            f"/api/months/{feb}/incomes", json={"description": "X", "amount": "1.00", "day": 32}
        ).status_code
        == 422
    )
    # Editar o dia de uma receita só deste mês também confere.
    single = next(
        i for i in user.get(f"/api/months/{feb}").json()["incomes"] if i["description"] == "Bônus"
    )
    assert user.patch(f"/api/incomes/{single['id']}", json={"day": 30}).status_code == 400
    assert user.patch(f"/api/incomes/{single['id']}", json={"day": 10}).status_code == 200
