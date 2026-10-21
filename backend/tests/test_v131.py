"""v1.3.1: respostas públicas nos recados, tema das solicitações e anexos de documentos."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import OutgoingEmail
from app.models import User
from tests.conftest import create_verified_user, login


def switch(client: TestClient, address: str) -> None:
    client.post("/api/auth/logout")
    login(client, address)


@pytest.fixture
def people(
    client: TestClient, outbox: list[OutgoingEmail], monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(get_settings(), "admin_emails", "chefe@example.com")
    for address in ("ana@example.com", "bia@example.com", "chefe@example.com"):
        create_verified_user(client, outbox, address)
    login(client, "ana@example.com")
    return client


# ---------------------------------------------------------------- recados com thread pública


def test_announcement_thread_is_public_with_profile_names(people: TestClient, db: Session) -> None:
    ana = db.scalar(select(User).where(User.email == "ana@example.com"))
    assert ana is not None
    ana.display_name = "Ana Souza"
    db.commit()
    switch(people, "chefe@example.com")
    people.post("/api/admin/announcements", json={"title": "Bom dia amigos!", "body": "Novidades."})
    switch(people, "ana@example.com")
    [item] = people.get("/api/announcements").json()
    out = people.post(f"/api/announcements/{item['id']}/replies", json={"message": "Adorei!"})
    assert out.status_code == 200, out.text
    [reply] = out.json()["replies"]
    assert (reply["author_name"], reply["mine"], reply["can_delete"]) == ("Ana Souza", True, True)
    # Outra pessoa vê a resposta (thread pública), sem e-mail, e não pode apagar.
    switch(people, "bia@example.com")
    [feed] = people.get("/api/announcements").json()
    [seen] = feed["replies"]
    assert seen["body"] == "Adorei!" and seen["mine"] is False and seen["can_delete"] is False
    assert "ana@example.com" not in str(feed)
    assert people.delete(f"/api/announcement-replies/{seen['id']}").status_code == 404
    people.post(f"/api/announcements/{item['id']}/replies", json={"message": "Também!"})
    # A administração responde na mesma thread e pode apagar qualquer resposta.
    switch(people, "chefe@example.com")
    out = people.post(f"/api/announcements/{item['id']}/replies", json={"message": "Obrigado!"})
    replies = out.json()["replies"]
    assert [r["body"] for r in replies] == ["Adorei!", "Também!", "Obrigado!"]
    assert replies[2]["from_admin"] is True
    assert people.get("/api/admin/announcements").json()[0]["replies"] == 3
    assert people.delete(f"/api/announcement-replies/{replies[1]['id']}").status_code == 204
    # A autora apaga a própria resposta.
    switch(people, "ana@example.com")
    mine = people.get("/api/announcements").json()[0]["replies"][0]
    assert people.delete(f"/api/announcement-replies/{mine['id']}").status_code == 204
    assert [r["body"] for r in people.get("/api/announcements").json()[0]["replies"]] == [
        "Obrigado!"
    ]
    # Limite de 1000 caracteres.
    long = people.post(f"/api/announcements/{item['id']}/replies", json={"message": "x" * 1001})
    assert long.status_code == 422


def test_announcement_thread_only_for_who_received_it(
    people: TestClient, outbox: list[OutgoingEmail]
) -> None:
    switch(people, "chefe@example.com")
    people.post("/api/admin/announcements", json={"title": "Recado antigo", "body": "Texto."})
    # Quem entrou depois não recebeu o recado: não vê nem responde.
    create_verified_user(people, outbox, "novo@example.com")
    switch(people, "chefe@example.com")
    [announcement] = people.get("/api/announcements").json()
    switch(people, "novo@example.com")
    assert people.get("/api/announcements").json() == []
    out = people.post(f"/api/announcements/{announcement['id']}/replies", json={"message": "Oi"})
    assert out.status_code == 404


# ---------------------------------------------------------------- tema e texto da solicitação


def test_new_request_has_topic_and_title_from_the_text(people: TestClient) -> None:
    out = people.post(
        "/api/support/threads",
        data={"kind": "question", "message": "Como faço para exportar o ano inteiro em PDF?"},
    )
    assert out.status_code == 201, out.text
    assert out.json()["title"] == "Dúvida: Como faço para exportar o ano inteiro em PDF?"
    assert out.json()["kind"] == "question"
    praise = people.post("/api/support/threads", data={"kind": "praise", "message": "x" * 1000})
    assert praise.status_code == 201 and praise.json()["title"].startswith("Elogio: ")
    long = people.post("/api/support/threads", data={"kind": "idea", "message": "x" * 1001})
    assert long.status_code == 422
    bad = people.post("/api/support/threads", data={"kind": "reclamacao", "message": "Oi"})
    assert bad.status_code == 422


# ---------------------------------------------------------------- anexos de documentos


def xlsx(macros: bool = False) -> bytes:
    book = Workbook()
    book.active.append(["Data", "Valor"])
    out = io.BytesIO()
    book.save(out)
    if not macros:
        return out.getvalue()
    source = zipfile.ZipFile(io.BytesIO(out.getvalue()))
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("xl/vbaProject.bin", b"macro")
    return result.getvalue()


def send(client: TestClient, files: list[tuple[str, bytes]]):  # type: ignore[no-untyped-def]
    uploads = [("images", (name, raw, "application/octet-stream")) for name, raw in files]
    return client.post(
        "/api/support/threads", data={"kind": "bug", "message": "Segue o arquivo."}, files=uploads
    )


def test_pdf_and_spreadsheets_are_accepted_and_only_downloaded(people: TestClient) -> None:
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    csv = b"data;valor\n01/10/2026;120,50\n"
    ods = io.BytesIO()
    with zipfile.ZipFile(ods, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", "<x/>")
    out = send(people, [("extrato.pdf", pdf), ("gastos.xlsx", xlsx()), ("lista.csv", csv)])
    assert out.status_code == 201, out.text
    detail = people.get(f"/api/support/threads/{out.json()['id']}").json()
    files = detail["messages"][0]["attachments"]
    assert [(f["content_type"], f["filename"]) for f in files] == [
        ("application/pdf", "extrato.pdf"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "gastos.xlsx"),
        ("text/csv", "lista.csv"),
    ]
    download = people.get(f"/api/files/{files[0]['id']}")
    assert download.status_code == 200 and download.content == pdf
    assert download.headers["content-disposition"].startswith('attachment; filename="extrato.pdf"')
    assert "sandbox" in download.headers["content-security-policy"]
    assert send(people, [("planilha.ods", ods.getvalue())]).status_code == 201


def test_macros_and_unknown_files_are_refused(people: TestClient) -> None:
    macro = send(people, [("contas.xlsx", xlsx(macros=True))])
    assert macro.status_code == 400 and macro.json()["error"] == "macros_not_allowed"
    ole_macro = (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + "_VBA_PROJECT".encode("utf-16-le") + b"\0" * 64
    )
    assert send(people, [("antiga.xls", ole_macro)]).json()["error"] == "macros_not_allowed"
    exe = send(people, [("planilha.xlsx", b"MZ\x90\x00\x03" + b"\x00" * 200)])
    assert exe.status_code == 400 and "PDF ou planilha" in exe.json()["message"]
    assert people.get("/api/support/threads").json() == []
