"""Importação de extratos bancários (OFX e CSV).

`preview` lê o arquivo, sugere categorias e marca o que já foi importado antes;
`commit` grava os lançamentos confirmados como contas pagas ou rendas.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.parsing import normalize_text, parse_amount, parse_date
from app.db.types import utcnow
from app.models import Expense, Income, User
from app.services import budget

REF_PREFIX = "stmt:"
MAX_TRANSACTIONS = 2000

DATE_COLUMNS = {
    "data",
    "date",
    "dt",
    "data lancamento",
    "data de lancamento",
    "data movimento",
    "data da transacao",
    "data transacao",
}
DESCRIPTION_COLUMNS = {
    "descricao",
    "historico",
    "lancamento",
    "title",
    "memo",
    "description",
    "estabelecimento",
    "detalhes",
    "identificacao",
}
AMOUNT_COLUMNS = {"valor", "amount", "value", "valor (r$)", "valor r$", "quantia"}
CREDIT_COLUMNS = {"credito", "entrada", "creditos", "credito (r$)"}
DEBIT_COLUMNS = {"debito", "saida", "debitos", "debito (r$)"}

# Palavra no texto do extrato -> categoria padrão sugerida.
KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "aluguel",
            "condominio",
            "energia",
            "enel",
            "cemig",
            "light",
            "copel",
            "sabesp",
            "agua",
            "gas ",
            "iptu",
        ),
        "Moradia",
    ),
    (
        (
            "mercado",
            "supermerc",
            "padaria",
            "acougue",
            "hortifruti",
            "atacad",
            "assai",
            "carrefour",
            "pao de acucar",
            "ifood",
            "rappi",
            "restaurante",
            "lanchonete",
        ),
        "Alimentação",
    ),
    (
        (
            "uber",
            "99 ",
            "99app",
            "posto",
            "combustivel",
            "shell",
            "ipiranga",
            "estacionamento",
            "pedagio",
            "metro",
            "onibus",
            "bilhete unico",
        ),
        "Transporte",
    ),
    (
        (
            "farmacia",
            "drogaria",
            "drogasil",
            "raia",
            "pague menos",
            "hospital",
            "clinica",
            "laboratorio",
            "unimed",
            "amil",
            "dentista",
        ),
        "Saúde",
    ),
    (("escola", "faculdade", "universidade", "curso", "udemy", "alura", "livraria"), "Educação"),
    (
        (
            "netflix",
            "spotify",
            "disney",
            "prime video",
            "hbo",
            "youtube",
            "internet",
            "vivo",
            "claro",
            "tim ",
            "oi ",
            "celular",
            "telefone",
        ),
        "Serviços",
    ),
    (
        ("cinema", "ingresso", "bar ", "show", "steam", "playstation", "viagem", "hotel", "airbnb"),
        "Lazer",
    ),
]


@dataclass
class Transaction:
    date: date
    description: str
    amount: Decimal  # positivo = entrada; negativo = saída
    ref: str


def _ref(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return REF_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:40]


def _skip_description(description: str) -> bool:
    text = normalize_text(description)
    return text.startswith("saldo") or text in {"s a l d o", "saldo anterior"}


# ---------------------------------------------------------------- OFX


def parse_ofx(text: str) -> list[Transaction]:
    transactions = []
    for block in re.findall(
        r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", text, re.S | re.I
    ):

        def tag(name: str, block: str = block) -> str | None:
            match = re.search(rf"<{name}>([^<\r\n]*)", block, re.I)
            return match.group(1).strip() if match else None

        posted = parse_date(tag("DTPOSTED"))
        amount = parse_amount(tag("TRNAMT"))
        description = tag("MEMO") or tag("NAME") or "Sem descrição"
        if posted is None or amount is None or amount == 0 or _skip_description(description):
            continue
        fitid = tag("FITID")
        ref = _ref("ofx", fitid) if fitid else _ref("ofx", posted, amount, description)
        transactions.append(Transaction(posted, description[:120], amount, ref))
    return transactions


# ---------------------------------------------------------------- CSV


def _find(header: list[str], names: set[str]) -> int | None:
    for index, column in enumerate(header):
        if normalize_text(column) in names:
            return index
    return None


def parse_csv(text: str, invert: bool = False) -> list[Transaction]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    # Alguns bancos colocam linhas de título antes do cabeçalho: procura a primeira linha com
    # uma coluna de data e uma de valor.
    header_index = None
    for index, row in enumerate(rows[:20]):
        if _find(row, DATE_COLUMNS) is not None and (
            _find(row, AMOUNT_COLUMNS) is not None
            or (_find(row, CREDIT_COLUMNS) is not None and _find(row, DEBIT_COLUMNS) is not None)
        ):
            header_index = index
            break
    if header_index is None:
        raise AppError(
            400,
            "unrecognized_csv",
            "Não reconheci as colunas do CSV. Ele precisa ter colunas de data e de valor "
            "(ou crédito e débito). Se o banco oferecer, prefira o formato OFX.",
        )

    header = rows[header_index]
    col_date = _find(header, DATE_COLUMNS)
    col_desc = _find(header, DESCRIPTION_COLUMNS)
    col_amount = _find(header, AMOUNT_COLUMNS)
    col_credit = _find(header, CREDIT_COLUMNS)
    col_debit = _find(header, DEBIT_COLUMNS)

    def cell(row: list[str], index: int | None) -> str:
        return row[index].strip() if index is not None and index < len(row) else ""

    transactions = []
    seen: Counter[tuple[Any, ...]] = Counter()
    for row in rows[header_index + 1 :]:
        if not any(c.strip() for c in row):
            continue
        posted = parse_date(cell(row, col_date))
        if col_amount is not None:
            amount = parse_amount(cell(row, col_amount))
        else:
            credit = parse_amount(cell(row, col_credit)) or Decimal("0")
            debit = parse_amount(cell(row, col_debit)) or Decimal("0")
            amount = abs(credit) - abs(debit)
        description = cell(row, col_desc) or "Sem descrição"
        if posted is None or amount is None or amount == 0 or _skip_description(description):
            continue
        if invert:
            amount = -amount
        # Duas compras iguais no mesmo dia são lançamentos diferentes.
        key = (posted, amount, description)
        seen[key] += 1
        transactions.append(
            Transaction(posted, description[:120], amount, _ref("csv", *key, seen[key]))
        )
    return transactions


# ---------------------------------------------------------------- prévia e gravação


def _existing_refs(db: Session, user: User, refs: list[str]) -> set[str]:
    found: set[str] = set()
    for model in (Income, Expense):
        found.update(
            r
            for (r,) in db.execute(
                select(model.import_ref).where(model.user_id == user.id, model.import_ref.in_(refs))
            )
        )
    return found


def _category_suggester(db: Session, user: User) -> Any:
    categories = budget.list_categories(db, user)
    by_name = {normalize_text(c.name): c.id for c in categories}
    # O que o próprio usuário já categorizou vale mais que as palavras-chave.
    learned: dict[str, Any] = {}
    for description, category_id in db.execute(
        select(Expense.description, Expense.category_id)
        .where(Expense.user_id == user.id, Expense.category_id.is_not(None))
        .order_by(Expense.created_at)
    ):
        learned[normalize_text(description)] = category_id

    def suggest(description: str) -> Any:
        text = normalize_text(description)
        if text in learned:
            return learned[text]
        padded = f" {text} "
        for words, name in KEYWORDS:
            if any(word in padded for word in words):
                return by_name.get(normalize_text(name))
        return None

    return suggest


def preview(db: Session, user: User, filename: str, content: str, invert: bool) -> dict[str, Any]:
    is_ofx = filename.lower().endswith((".ofx", ".qfx")) or "<OFX>" in content[:2000].upper()
    transactions = parse_ofx(content) if is_ofx else parse_csv(content, invert)
    if is_ofx and invert:
        for t in transactions:
            t.amount = -t.amount
    if not transactions:
        raise AppError(400, "empty_statement", "Não encontrei lançamentos neste arquivo.")
    if len(transactions) > MAX_TRANSACTIONS:
        raise AppError(
            400, "too_many", f"O arquivo tem mais de {MAX_TRANSACTIONS} lançamentos. Divida-o."
        )

    existing = _existing_refs(db, user, [t.ref for t in transactions])
    suggest = _category_suggester(db, user)
    items = []
    for t in sorted(transactions, key=lambda t: t.date):
        kind = "income" if t.amount > 0 else "expense"
        items.append(
            {
                "ref": t.ref,
                "date": t.date,
                "description": t.description,
                "amount": abs(t.amount),
                "kind": kind,
                "category_id": suggest(t.description) if kind == "expense" else None,
                "duplicate": t.ref in existing,
            }
        )
    return {"format": "ofx" if is_ofx else "csv", "transactions": items}


def commit(db: Session, user: User, items: list[dict[str, Any]]) -> dict[str, int]:
    existing = _existing_refs(db, user, [i["ref"] for i in items])
    valid_categories = {c.id for c in budget.list_categories(db, user)}
    created = skipped = 0
    now = utcnow()
    for item in items:
        if item["ref"] in existing:
            skipped += 1
            continue
        existing.add(item["ref"])
        month = item["date"].replace(day=1)
        if item["kind"] == "income":
            db.add(
                Income(
                    user_id=user.id,
                    month=month,
                    description=item["description"],
                    amount=item["amount"],
                    import_ref=item["ref"],
                )
            )
        else:
            category_id = item.get("category_id")
            if category_id is not None and category_id not in valid_categories:
                raise AppError(404, "not_found", "Categoria não encontrada.")
            db.add(
                Expense(
                    user_id=user.id,
                    month=month,
                    description=item["description"],
                    amount=item["amount"],
                    category_id=category_id,
                    due_date=item["date"],
                    paid=True,
                    paid_at=now,
                    import_ref=item["ref"],
                )
            )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}
