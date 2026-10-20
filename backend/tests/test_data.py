import csv
import io
import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.core.email import OutgoingEmail
from app.core.parsing import parse_amount, parse_date
from tests.conftest import create_verified_user, login

Outbox = list[OutgoingEmail]
MONTH = "2030-01"


@pytest.fixture
def user(client: TestClient, outbox: Outbox) -> TestClient:
    create_verified_user(client, outbox)
    login(client)
    return client


def month(client: TestClient, value: str) -> dict[str, Any]:
    response = client.get(f"/api/months/{value}")
    assert response.status_code == 200, response.text
    return response.json()


def category_name(client: TestClient, category_id: str | None) -> str | None:
    for c in client.get("/api/categories").json():
        if c["id"] == category_id:
            return c["name"]
    return None


# ---------------------------------------------------------------- conversões


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("R$ -12,30", "-12.30"),
        ("(12,30)", "-12.30"),
        ("2.300", "2300.00"),
        ("2300", "2300.00"),
        ("-45.9", "-45.90"),
        (563, "563.00"),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_amount(text: object, expected: str | None) -> None:
    result = parse_amount(text)
    assert (str(result) if result is not None else None) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("05/01/2030", "2030-01-05"),
        ("2030-01-05", "2030-01-05"),
        ("05/01/30", "2030-01-05"),
        ("20300105120000[-3:BRT]", "2030-01-05"),
        ("31/02/2030", None),
        ("ontem", None),
    ],
)
def test_parse_date(text: str, expected: str | None) -> None:
    result = parse_date(text)
    assert (result.isoformat() if result else None) == expected


# ---------------------------------------------------------------- app antigo

LEGACY = {
    "profile": {"name": "Pessoa Teste", "age": "30", "photo": "", "job": "", "notes": ""},
    "incomes": [
        {"name": "salário", "value": "2300"},
        {"name": "beneficio", "value": "1100"},
        {"name": "", "value": ""},
    ],
    "goal": "0",
    "reserve": "5000",
    "theme": "dark",
    "bills": [
        {
            "name": "faculdade",
            "value": "563",
            "category": "educacao",
            "due": "2030-01-10",
            "paid": True,
            "installment": {"enabled": False, "current": "1", "total": "1"},
            "notes": "",
        },
        {
            "name": "notebook",
            "value": "250,50",
            "category": "outros",
            "due": "15",
            "paid": False,
            "installment": {"enabled": True, "current": "3", "total": "5"},
            "notes": "loja X",
        },
        {
            "name": "remédio",
            "value": "80",
            "category": "essencial",
            "due": "",
            "paid": False,
            "installment": {"enabled": False, "current": "1", "total": "1"},
            "notes": "",
        },
        {"name": "", "value": "", "category": "outros", "due": "", "paid": False},
    ],
    "history": [
        {"key": "2029-11", "label": "Dez/2029", "income": 3400, "totalBills": 563},
        {"key": "2030-0", "label": "Jan/2030", "income": 3400, "totalBills": 563},
    ],
    "goals": [{"name": "Viagem", "target": "5000", "current": "1200"}],
    "apiConfig": {"endpoint": "", "token": ""},
}


def legacy_preview(client: TestClient, data: Any = LEGACY) -> dict[str, Any]:
    response = client.post("/api/import/legacy/preview", json={"month": MONTH, "data": data})
    assert response.status_code == 200, response.text
    return response.json()


def test_legacy_preview(user: TestClient) -> None:
    preview = legacy_preview(user)
    assert [i["description"] for i in preview["incomes"]] == ["salário", "beneficio"]
    assert all(i["recurring"] for i in preview["incomes"])

    expenses = {e["description"]: e for e in preview["expenses"]}
    assert set(expenses) == {"faculdade", "notebook", "remédio"}
    assert expenses["faculdade"]["category_name"] == "Educação"
    assert expenses["faculdade"]["due_day"] == 10
    assert expenses["faculdade"]["paid"] is True
    assert Decimal(expenses["notebook"]["amount"]) == Decimal("250.50")
    assert (
        expenses["notebook"]["installment_current"],
        expenses["notebook"]["installment_total"],
    ) == (3, 5)
    assert expenses["notebook"]["due_day"] == 15
    assert expenses["remédio"]["category_name"] == "Outros essenciais"

    # "2029-11" no app antigo é dezembro (mês começando em 0); o mês de destino fica de fora.
    assert preview["history"] == [{"month": "2029-12", "income": "3400.00", "expenses": "563.00"}]
    assert Decimal(preview["reserve"]) == Decimal("5000")
    assert preview["goals"][0]["name"] == "Viagem"
    assert preview["already_imported"] is False
    # O perfil não é devolvido nem importado.
    assert "profile" not in preview


def test_legacy_import(user: TestClient) -> None:
    payload = legacy_preview(user)
    for expense in payload["expenses"]:
        if expense["description"] == "faculdade":
            expense["recurring"] = True
    payload.pop("already_imported")

    response = user.post("/api/import/legacy", json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "incomes": 2,
        "expenses": 3,
        "goals": 1,
        "history_months": 1,
        "investments": 1,
    }

    january = month(user, MONTH)
    assert sorted(i["description"] for i in january["incomes"]) == ["beneficio", "salário"]
    assert all(i["recurring_id"] for i in january["incomes"])
    by_desc = {e["description"]: e for e in january["expenses"]}
    assert by_desc["faculdade"]["recurring_id"] is not None
    # Estava paga no arquivo antigo: continua paga no mês importado (só nele).
    assert by_desc["faculdade"]["paid"] is True
    assert by_desc["notebook"]["installment_number"] == 3
    assert by_desc["notebook"]["due_date"] == "2030-01-15"
    assert category_name(user, by_desc["remédio"]["category_id"]) == "Outros essenciais"
    essential = {c["name"]: c["is_essential"] for c in user.get("/api/categories").json()}
    assert essential["Outros essenciais"] is True

    february = {e["description"]: e for e in month(user, "2030-02")["expenses"]}
    assert february["notebook"]["installment_number"] == 4
    assert february["faculdade"]["paid"] is False  # fixa, ainda a pagar
    march = [e["description"] for e in month(user, "2030-03")["expenses"]]
    assert "notebook" in march
    april = [e["description"] for e in month(user, "2030-04")["expenses"]]
    assert "notebook" not in april  # parcela 5/5 foi em março

    december = month(user, "2029-12")
    assert Decimal(december["summary"]["income_total"]) == Decimal("3400")
    assert Decimal(december["summary"]["paid_total"]) == Decimal("563")

    investments = user.get("/api/investments").json()
    assert investments[0]["is_emergency_reserve"] is True
    assert Decimal(investments[0]["current_value"]) == Decimal("5000")
    assert user.get("/api/goals").json()[0]["progress_pct"] == 24.0

    assert legacy_preview(user)["already_imported"] is True


def test_legacy_invalid_file(user: TestClient) -> None:
    response = user.post("/api/import/legacy/preview", json={"month": MONTH, "data": {"foo": 1}})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_file"


# ---------------------------------------------------------------- extratos

OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
ENCODING:USASCII

<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKTRANLIST>
<DTSTART>20300101
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20300105120000[-3:BRT]
<TRNAMT>-45.90
<FITID>A1
<MEMO>SUPERMERCADO BOM PRECO
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20300105
<TRNAMT>3000.00
<FITID>A2
<MEMO>SALARIO EMPRESA
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20300210
<TRNAMT>-25,00
<FITID>A3
<NAME>UBER TRIP
</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""


def statement_preview(
    client: TestClient, content: str, filename: str = "extrato.csv", invert: bool = False
) -> dict[str, Any]:
    response = client.post(
        "/api/import/statement/preview",
        json={"filename": filename, "content": content, "invert": invert},
    )
    assert response.status_code == 200, response.text
    return response.json()


def to_commit(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "transactions": [
            {k: v for k, v in t.items() if k != "duplicate"} for t in preview["transactions"]
        ]
    }


def test_ofx_import(user: TestClient) -> None:
    preview = statement_preview(user, OFX, "extrato.ofx")
    assert preview["format"] == "ofx"
    items = preview["transactions"]
    assert [(t["date"], t["kind"], t["amount"]) for t in items] == [
        ("2030-01-05", "expense", "45.90"),
        ("2030-01-05", "income", "3000.00"),
        ("2030-02-10", "expense", "25.00"),
    ]
    assert category_name(user, items[0]["category_id"]) == "Alimentação"
    assert category_name(user, items[2]["category_id"]) == "Transporte"
    assert items[1]["category_id"] is None
    assert not any(t["duplicate"] for t in items)

    result = user.post("/api/import/statement", json=to_commit(preview))
    assert result.json() == {"created": 3, "skipped": 0}

    january = month(user, MONTH)
    assert [i["description"] for i in january["incomes"]] == ["SALARIO EMPRESA"]
    market = january["expenses"][0]
    assert market["paid"] is True
    assert market["due_date"] == "2030-01-05"
    assert [e["description"] for e in month(user, "2030-02")["expenses"]] == ["UBER TRIP"]

    # Importar o mesmo arquivo de novo não duplica.
    again = statement_preview(user, OFX, "extrato.ofx")
    assert all(t["duplicate"] for t in again["transactions"])
    assert user.post("/api/import/statement", json=to_commit(again)).json() == {
        "created": 0,
        "skipped": 3,
    }


BANK_CSV = """Extrato conta corrente
Data;Lançamento;Valor (R$);Saldo (R$)
02/01/2030;SALDO ANTERIOR;;1.000,00
03/01/2030;PAG BOLETO ALUGUEL;-1.200,00;-200,00
03/01/2030;PIX RECEBIDO;1.500,50;1.300,50
04/01/2030;PADARIA;-12,00;
04/01/2030;PADARIA;-12,00;
"""


def test_brazilian_bank_csv(user: TestClient) -> None:
    items = statement_preview(user, BANK_CSV)["transactions"]
    assert [(t["description"], t["kind"], t["amount"]) for t in items] == [
        ("PAG BOLETO ALUGUEL", "expense", "1200.00"),
        ("PIX RECEBIDO", "income", "1500.50"),
        ("PADARIA", "expense", "12.00"),
        ("PADARIA", "expense", "12.00"),
    ]
    # Duas compras iguais no mesmo dia são lançamentos distintos.
    assert items[2]["ref"] != items[3]["ref"]
    assert category_name(user, items[0]["category_id"]) == "Moradia"


def test_credit_card_csv_with_inverted_signs(user: TestClient) -> None:
    content = "date,title,amount\n2030-01-04,Netflix.com,39.90\n2030-01-05,Estorno compra,-10.00\n"
    items = statement_preview(user, content, invert=True)["transactions"]
    assert [(t["description"], t["kind"]) for t in items] == [
        ("Netflix.com", "expense"),
        ("Estorno compra", "income"),
    ]
    assert category_name(user, items[0]["category_id"]) == "Assinaturas"


def test_csv_with_credit_and_debit_columns(user: TestClient) -> None:
    content = "Data,Histórico,Crédito,Débito\n05/01/2030,Salário,3000,\n06/01/2030,Farmácia,,45.5\n"
    items = statement_preview(user, content)["transactions"]
    assert [(t["kind"], t["amount"]) for t in items] == [
        ("income", "3000.00"),
        ("expense", "45.50"),
    ]
    assert category_name(user, items[1]["category_id"]) == "Saúde"


def test_category_learned_from_user_history(user: TestClient) -> None:
    lazer = next(c["id"] for c in user.get("/api/categories").json() if c["name"] == "Lazer")
    user.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "Padaria", "amount": "5", "category_id": lazer},
    )
    items = statement_preview(user, BANK_CSV)["transactions"]
    padaria = next(t for t in items if t["description"] == "PADARIA")
    assert padaria["category_id"] == lazer


def test_unrecognized_csv(user: TestClient) -> None:
    response = user.post(
        "/api/import/statement/preview",
        json={"filename": "x.csv", "content": "nome,idade\nana,30\n"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "unrecognized_csv"


def test_statement_commit_rejects_foreign_category(user: TestClient) -> None:
    preview = statement_preview(user, OFX, "extrato.ofx")
    payload = to_commit(preview)
    payload["transactions"][0]["category_id"] = str(uuid.uuid4())
    assert user.post("/api/import/statement", json=payload).status_code == 404


def test_statement_ref_must_be_valid(user: TestClient) -> None:
    payload = {
        "transactions": [
            {
                "ref": "legacy:hack",
                "date": "2030-01-01",
                "description": "X",
                "amount": "1",
                "kind": "expense",
            }
        ]
    }
    assert user.post("/api/import/statement", json=payload).status_code == 422


# ---------------------------------------------------------------- exportar


def seed_month(client: TestClient) -> None:
    client.post(f"/api/months/{MONTH}/incomes", json={"description": "Salário", "amount": "3000"})
    moradia = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Moradia")
    client.post(
        f"/api/months/{MONTH}/expenses",
        json={
            "description": "Aluguel; centro",
            "amount": "1234.50",
            "category_id": moradia,
            "due_date": "2030-01-10",
        },
    )
    client.post(
        f"/api/months/{MONTH}/expenses",
        json={"description": "Celular", "amount": "100", "installments": 2},
    )


def test_export_csv(user: TestClient) -> None:
    seed_month(user)
    response = user.get(f"/api/export/transactions?start={MONTH}&end=2030-02&format=csv")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")

    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == [
        "Mês",
        "Tipo",
        "Data",
        "Descrição",
        "Categoria",
        "Conta ou cartão",
        "Forma de pagamento",
        "Valor",
        "Pago",
        "Parcela",
        "Recorrente",
    ]
    salario = rows[1]
    assert (salario[0], salario[1], salario[3], salario[7]) == (
        "2030-01",
        "Receita",
        "Salário",
        "3000,00",
    )
    aluguel = next(r for r in rows if r[3] == "Aluguel; centro")
    assert aluguel[1] == "Despesa"
    assert aluguel[2] == "10/01/2030"
    assert aluguel[4] == "Moradia"
    assert aluguel[7] == "-1234,50"
    assert [r[9] for r in rows if r[3] == "Celular"] == ["1/2", "2/2"]

    # Filtros: só despesas, só uma categoria; a contagem acompanha.
    only = user.get(f"/api/export/transactions?start={MONTH}&end=2030-02&kind=expense")
    kinds = {
        r[1]
        for r in list(csv.reader(io.StringIO(only.content.decode("utf-8-sig")), delimiter=";"))[1:]
    }
    assert kinds == {"Despesa"}
    moradia = next(c["id"] for c in user.get("/api/categories").json() if c["name"] == "Moradia")
    count = user.get(f"/api/export/count?start={MONTH}&end=2030-02&category={moradia}").json()
    assert count == {"count": 1}
    assert user.get(f"/api/export/count?start={MONTH}&end=2030-02").json()["count"] == len(rows) - 1


def test_export_xlsx(user: TestClient) -> None:
    seed_month(user)
    response = user.get(f"/api/export/transactions?start={MONTH}&end={MONTH}&format=xlsx")
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["Lançamentos", "Resumo mensal", "Por categoria"]
    sheet = workbook["Lançamentos"]
    assert sheet["D1"].value == "Descrição"
    assert sheet.max_row == 4  # cabeçalho + salário + aluguel + celular 1/2
    categories = workbook["Por categoria"]
    assert categories["A2"].value == "Moradia"
    resume = workbook["Resumo mensal"]
    assert resume["A2"].value == MONTH
    assert resume["B2"].value == 3000
    assert resume["E2"].value == pytest.approx(3000 - 1234.5 - 100)


def test_export_invalid_period(user: TestClient) -> None:
    response = user.get("/api/export/transactions?start=2030-05&end=2030-01")
    assert response.status_code == 400


def test_backup(user: TestClient) -> None:
    seed_month(user)
    user.post("/api/goals", json={"name": "Viagem", "target_amount": "1000"})
    response = user.get("/api/export/backup")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["account"]["email"] == "ana@example.com"
    assert len(data["categories"]) == 11
    assert len(data["incomes"]) == 1
    assert len(data["expenses"]) == 3
    assert data["goals"][0]["name"] == "Viagem"
    text = response.content.decode()
    assert "password" not in text
    assert "totp_secret" not in text
    assert "user_id" not in text


def test_data_routes_require_login(client: TestClient) -> None:
    assert client.get("/api/export/backup").status_code == 401
    assert client.get(f"/api/export/transactions?start={MONTH}").status_code == 401
    response = client.post(
        "/api/import/statement/preview", json={"filename": "a.ofx", "content": OFX}
    )
    assert response.status_code == 401
