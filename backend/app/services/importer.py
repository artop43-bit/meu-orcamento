"""Importação única: um arquivo, o sistema descobre o que é e o que cada coluna significa.

Formatos aceitos (detectados pelo conteúdo, não pela extensão):
- OFX: extrato da conta ou fatura do cartão;
- CSV e Excel (.xlsx): extrato exportado pelo banco ou planilha própria;
- backup do Meu Orçamento (.json): restaura os dados;
- arquivo do app antigo (.json).

Fluxo: `analyze` (formato, tipo e colunas) → `preview` (lançamentos, categorias sugeridas,
repetidos) → `commit` (grava num lote, que pode ser desfeito por inteiro).
"""

import csv
import hashlib
import io
import json
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, SmallInteger, Uuid, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeDecorator, TypeEngine

from app.core.errors import AppError
from app.core.months import month_of
from app.core.parsing import normalize_text, parse_amount, parse_date
from app.db.types import utcnow
from app.models import (
    Category,
    CreditCard,
    Expense,
    Goal,
    ImportBatch,
    ImportMapping,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    OtherDebt,
    RecurringItem,
    SplitShare,
    User,
)
from app.services import budget, statement_import
from app.services.statement_import import Transaction, _ref

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
SAMPLE_ROWS = 5

DATE_NAMES = statement_import.DATE_COLUMNS | {
    "data compra",
    "data da compra",
    "data do lancamento",
    "data operacao",
    "dia",
}
DESCRIPTION_NAMES = statement_import.DESCRIPTION_COLUMNS | {
    "nome",
    "transacao",
    "descricao do lancamento",
    "produto",
    "local",
    "favorecido",
    "beneficiario",
}
AMOUNT_NAMES = statement_import.AMOUNT_COLUMNS | {
    "valor (brl)",
    "valor em r$",
    "valor da transacao",
    "total",
    "valor brl",
}
CREDIT_NAMES = statement_import.CREDIT_COLUMNS | {"credito r$", "entradas"}
DEBIT_NAMES = statement_import.DEBIT_COLUMNS | {"debito r$", "saidas"}
CARD_WORDS = ("fatura", "cartao", "parcela")
FIELDS = ("date", "description", "amount", "credit", "debit")


# ---------------------------------------------------------------- leitura do arquivo


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_format(raw: bytes, filename: str) -> tuple[str, Any]:
    """Devolve (formato, conteúdo já lido)."""
    if not raw:
        raise AppError(400, "empty_file", "O arquivo está vazio.")
    if len(raw) > MAX_BYTES:
        raise AppError(413, "file_too_large", "O arquivo passa de 5 MB. Divida-o por período.")
    if raw[:5] == b"%PDF-":
        raise AppError(
            400,
            "pdf_not_supported",
            "Extrato em PDF não é aceito: cada banco monta o PDF de um jeito e a leitura erra "
            "valores. No app ou site do banco, exporte o extrato em OFX (recomendado) ou CSV.",
        )
    if raw[:4] == b"PK\x03\x04":
        return "xlsx", _read_xlsx(raw)
    text = _decode(raw)
    head = text[:3000].upper()
    if "<OFX>" in head or "OFXHEADER" in head:
        return "ofx", text
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError as exc:
            raise AppError(400, "invalid_file", "Arquivo JSON inválido.") from exc
        if isinstance(data, dict) and data.get("format") == "meu-orcamento-backup":
            return "backup", data
        if isinstance(data, dict) and ("bills" in data or "incomes" in data):
            return "legacy", data
        raise AppError(
            400,
            "invalid_file",
            "Este JSON não é um backup do Meu Orçamento nem um arquivo do app antigo.",
        )
    return "csv", _read_csv(text)


def _read_csv(text: str) -> list[list[Any]]:
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)][: MAX_ROWS + 50]


def _read_xlsx(raw: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # zip corrompido, formato antigo .xls renomeado etc.
        raise AppError(
            400, "invalid_file", "Não foi possível ler a planilha. Salve como .xlsx ou CSV."
        ) from exc
    sheet = workbook.worksheets[0]
    rows: list[list[Any]] = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if c is None else c for c in row])
        if len(rows) > MAX_ROWS + 50:
            break
    workbook.close()
    return rows


# ---------------------------------------------------------------- colunas


def _cell(row: list[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return ""
    value = row[index]
    return value.strip() if isinstance(value, str) else value


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(str(value)) if value not in ("", None) else None


def _find_named(header: list[Any], names: set[str]) -> int | None:
    for index, column in enumerate(header):
        if isinstance(column, str) and normalize_text(column) in names:
            return index
    return None


def _guess_by_content(rows: list[list[Any]], start: int) -> dict[str, int | None]:
    """Sem cabeçalho reconhecível: escolhe as colunas pelo conteúdo das primeiras linhas."""
    body = [r for r in rows[start : start + 30] if any(str(c).strip() for c in r)]
    width = max((len(r) for r in body), default=0)
    best: dict[str, int | None] = {f: None for f in FIELDS}
    date_score = amount_score = text_score = 0.0
    for col in range(width):
        values = [_cell(r, col) for r in body]
        filled = [v for v in values if v not in ("", None)]
        if not filled:
            continue
        dates = sum(1 for v in filled if _to_date(v)) / len(filled)
        numbers = sum(1 for v in filled if parse_amount(v) is not None and not _to_date(v))
        numbers /= len(filled)
        texts = [str(v) for v in filled if parse_amount(v) is None and not _to_date(v)]
        avg_len = sum(len(t) for t in texts) / len(filled) if texts else 0
        if dates > date_score and dates >= 0.6:
            best["date"], date_score = col, dates
        elif numbers > amount_score and numbers >= 0.6:
            best["amount"], amount_score = col, numbers
        elif avg_len > text_score:
            best["description"], text_score = col, avg_len
    return best


def detect_columns(rows: list[list[Any]]) -> dict[str, Any]:
    """Linha do cabeçalho e o índice de cada campo (data, descrição, valor ou crédito/débito)."""
    for index, row in enumerate(rows[:20]):
        date_col = _find_named(row, DATE_NAMES)
        amount_col = _find_named(row, AMOUNT_NAMES)
        credit_col = _find_named(row, CREDIT_NAMES)
        debit_col = _find_named(row, DEBIT_NAMES)
        if date_col is not None and (
            amount_col is not None or (credit_col is not None and debit_col is not None)
        ):
            desc_col = _find_named(row, DESCRIPTION_NAMES)
            mapping = {
                "header_row": index,
                "date": date_col,
                "description": desc_col,
                "amount": amount_col,
                "credit": credit_col if amount_col is None else None,
                "debit": debit_col if amount_col is None else None,
            }
            if desc_col is None:
                mapping["description"] = _guess_by_content(rows, index + 1)["description"]
            return mapping
    # Sem nomes conhecidos: a primeira linha é cabeçalho se não tiver data nem valor.
    first = rows[0] if rows else []
    has_header = bool(first) and not any(
        _to_date(c) or parse_amount(c) is not None for c in first if c not in ("", None)
    )
    start = 1 if has_header else 0
    guessed = _guess_by_content(rows, start)
    return {"header_row": 0 if has_header else -1, **guessed}


def signature(header: list[Any]) -> str:
    text = "|".join(normalize_text(str(c)) for c in header)
    return hashlib.sha256(text.encode()).hexdigest()


def _is_card_table(rows: list[list[Any]], mapping: dict[str, Any], filename: str) -> bool:
    header = rows[mapping["header_row"]] if mapping.get("header_row", -1) >= 0 else []
    words = normalize_text(" ".join(str(c) for c in header) + " " + filename)
    if any(w in words for w in CARD_WORDS):
        return True
    if mapping.get("amount") is None:
        return False
    start = mapping["header_row"] + 1
    amounts = [parse_amount(_cell(r, mapping["amount"])) for r in rows[start : start + 200]]
    values = [a for a in amounts if a]
    # Fatura: quase tudo positivo (compras) e um ou outro negativo (pagamento, estorno).
    return len(values) >= 5 and sum(1 for a in values if a > 0) / len(values) >= 0.85


# ---------------------------------------------------------------- análise


def analyze(db: Session, user: User, raw: bytes, filename: str) -> dict[str, Any]:
    fmt, content = detect_format(raw, filename)
    if fmt == "backup":
        return {"format": fmt, "kind": "backup", "summary": _backup_summary(content)}
    if fmt == "legacy":
        return {"format": fmt, "kind": "legacy"}
    if fmt == "ofx":
        card = "<CCSTMTRS>" in content.upper() or "CREDITCARDMSGSRSV1" in content.upper()
        count = len(statement_import.parse_ofx(content))
        if not count:
            raise AppError(400, "empty_statement", "Não encontrei lançamentos neste arquivo.")
        return {
            "format": fmt,
            "kind": "card" if card else "account",
            "invert": False,
            "count": count,
        }

    rows: list[list[Any]] = content
    if not rows or not any(any(str(c).strip() for c in r) for r in rows):
        raise AppError(400, "empty_file", "O arquivo está vazio.")
    mapping = detect_columns(rows)
    header = rows[mapping["header_row"]] if mapping["header_row"] >= 0 else []
    sig = signature(header) if header else None
    source = "auto"
    if sig:
        saved = db.scalar(
            select(ImportMapping).where(
                ImportMapping.user_id == user.id, ImportMapping.signature == sig
            )
        )
        if saved:
            mapping = {**mapping, **json.loads(saved.mapping)}
            source = "saved"
    width = max(len(r) for r in rows[:50])
    columns = [
        (
            str(header[i]).strip()
            if i < len(header) and str(header[i]).strip()
            else f"Coluna {i + 1}"
        )
        for i in range(width)
    ]
    start = mapping["header_row"] + 1
    sample = [[_display(c) for c in r] for r in rows[start:] if any(str(c).strip() for c in r)][
        :SAMPLE_ROWS
    ]
    card = _is_card_table(rows, mapping, filename)
    return {
        "format": fmt,
        "kind": "card" if card else "account",
        "invert": card,
        "columns": columns,
        "sample": sample,
        "mapping": mapping,
        "mapping_source": source,
        "signature": sig,
        "ready": mapping.get("date") is not None
        and (
            mapping.get("amount") is not None
            or (mapping.get("credit") is not None and mapping.get("debit") is not None)
        ),
    }


def _display(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


# ---------------------------------------------------------------- prévia


def table_transactions(
    rows: list[list[Any]], mapping: dict[str, Any], invert: bool
) -> list[Transaction]:
    if mapping.get("date") is None or (
        mapping.get("amount") is None
        and (mapping.get("credit") is None or mapping.get("debit") is None)
    ):
        raise AppError(
            400,
            "mapping_incomplete",
            "Indique as colunas de data e de valor (ou de crédito e débito).",
        )
    transactions = []
    seen: Counter[tuple[Any, ...]] = Counter()
    for row in rows[mapping.get("header_row", -1) + 1 :]:
        if not any(str(c).strip() for c in row):
            continue
        posted = _to_date(_cell(row, mapping["date"]))
        if mapping.get("amount") is not None:
            amount = parse_amount(_cell(row, mapping["amount"]))
        else:
            credit = parse_amount(_cell(row, mapping["credit"])) or Decimal("0")
            debit = parse_amount(_cell(row, mapping["debit"])) or Decimal("0")
            amount = abs(credit) - abs(debit)
        description = str(_cell(row, mapping.get("description")) or "").strip() or "Sem descrição"
        if posted is None or amount is None or amount == 0:
            continue
        if statement_import._skip_description(description):
            continue
        if invert:
            amount = -amount
        key = (posted, amount, description)
        seen[key] += 1
        transactions.append(
            Transaction(posted, description[:120], amount, _ref("csv", *key, seen[key]))
        )
    if len(transactions) > MAX_ROWS:
        raise AppError(400, "too_many", f"O arquivo tem mais de {MAX_ROWS} lançamentos. Divida-o.")
    return transactions


def preview(
    db: Session,
    user: User,
    raw: bytes,
    filename: str,
    mapping: dict[str, Any] | None,
    invert: bool,
) -> dict[str, Any]:
    fmt, content = detect_format(raw, filename)
    if fmt in ("backup", "legacy"):
        raise AppError(400, "wrong_step", "Este arquivo não tem prévia de lançamentos.")
    if fmt == "ofx":
        transactions = statement_import.parse_ofx(content)
        if invert:
            for t in transactions:
                t.amount = -t.amount
    else:
        transactions = table_transactions(content, mapping or detect_columns(content), invert)
    if not transactions:
        raise AppError(400, "empty_statement", "Não encontrei lançamentos neste arquivo.")
    existing = statement_import._existing_refs(db, user, [t.ref for t in transactions])
    suggest = statement_import._category_suggester(db, user)
    from app.services import cards

    has_cards = bool(cards.credit_cards(db, user))
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
                "card_payment": has_cards
                and kind == "expense"
                and statement_import.is_card_payment(t.description),
            }
        )
    from app.services import reconcile

    reconcile.match(db, user, items)
    dates = [t.date for t in transactions]
    return {
        "format": fmt,
        "transactions": items,
        "period": {"start": min(dates), "end": max(dates)},
    }


# ---------------------------------------------------------------- gravação e desfazer


def commit(
    db: Session,
    user: User,
    items: list[dict[str, Any]],
    *,
    filename: str,
    file_format: str,
    account_id: uuid.UUID | None = None,
    card_id: uuid.UUID | None = None,
    save_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services import cards

    card = cards.get_credit_card(db, user, card_id) if card_id else None
    budget._check_account(db, user, account_id)
    existing = statement_import._existing_refs(db, user, [i["ref"] for i in items])
    valid_categories = {c.id for c in budget.list_categories(db, user)}
    batch = ImportBatch(user_id=user.id, filename=filename[:160], file_format=file_format)
    db.add(batch)
    db.flush()
    created = skipped = matched = 0
    now = utcnow()
    today = date.today()
    from app.services import reconcile

    for item in items:
        if item["ref"] in existing:
            skipped += 1
            continue
        existing.add(item["ref"])
        if item.get("match_id") and reconcile.confirm(db, user, item):
            # v1.4: já lançado à mão — fica conferido pelo extrato, sem entrar de novo.
            matched += 1
            continue
        category_id = item.get("category_id")
        if category_id is not None and category_id not in valid_categories:
            raise AppError(404, "not_found", "Categoria não encontrada.")
        if item["kind"] == "income":
            db.add(
                Income(
                    user_id=user.id,
                    month=month_of(item["date"], user.month_start_day),
                    description=item["description"],
                    amount=item["amount"],
                    import_ref=item["ref"],
                    account_id=account_id,
                    import_batch_id=batch.id,
                )
            )
        elif card is not None:
            # Fatura de cartão: cada compra vai para a fatura certa pelo dia da compra.
            _, due = cards.invoice_dates(card, item["date"])
            budget.ensure_month(db, user, due.replace(day=1))
            db.add(
                Expense(
                    needs_review=True,
                    user_id=user.id,
                    month=due.replace(day=1),
                    description=item["description"],
                    amount=item["amount"],
                    category_id=category_id,
                    due_date=due,
                    purchase_date=item["date"],
                    card_id=card.id,
                    payment_method="credit",
                    paid=due < today,
                    paid_at=now if due < today else None,
                    import_ref=item["ref"],
                    import_batch_id=batch.id,
                )
            )
        else:
            db.add(
                Expense(
                    needs_review=True,
                    user_id=user.id,
                    month=month_of(item["date"], user.month_start_day),
                    description=item["description"],
                    amount=item["amount"],
                    category_id=category_id,
                    due_date=item["date"],
                    paid=True,
                    paid_at=now,
                    account_id=account_id,
                    import_ref=item["ref"],
                    import_batch_id=batch.id,
                )
            )
        created += 1
    batch.count = created
    if save_mapping and save_mapping.get("signature"):
        _save_mapping(db, user, save_mapping["signature"], save_mapping.get("mapping") or {})
    db.commit()
    return {"batch_id": batch.id, "created": created, "skipped": skipped, "matched": matched}


def _save_mapping(db: Session, user: User, sig: str, mapping: dict[str, Any]) -> None:
    clean = {k: mapping.get(k) for k in ("header_row", *FIELDS) if k in mapping}
    row = db.scalar(
        select(ImportMapping).where(
            ImportMapping.user_id == user.id, ImportMapping.signature == sig
        )
    )
    if row:
        row.mapping = json.dumps(clean)
    else:
        db.add(ImportMapping(user_id=user.id, signature=sig[:64], mapping=json.dumps(clean)))


def list_batches(db: Session, user: User, limit: int = 10) -> list[ImportBatch]:
    return list(
        db.scalars(
            select(ImportBatch)
            .where(ImportBatch.user_id == user.id)
            .order_by(ImportBatch.created_at.desc())
            .limit(limit)
        )
    )


def undo(db: Session, user: User, batch_id: uuid.UUID) -> int:
    batch = budget._owned(db, ImportBatch, batch_id, user)
    if batch.undone_at is not None:
        raise AppError(400, "already_undone", "Esta importação já foi desfeita.")
    removed = 0
    for model in (Expense, Income):
        removed += db.execute(
            delete(model).where(model.user_id == user.id, model.import_batch_id == batch.id)
        ).rowcount
    batch.undone_at = utcnow()
    db.commit()
    return removed


# ---------------------------------------------------------------- backup do Meu Orçamento


BACKUP_TABLES: list[tuple[str, Any]] = [
    ("accounts", MoneyAccount),
    ("categories", Category),
    ("cards", CreditCard),
    ("recurring", RecurringItem),
    ("loans", Loan),
    ("incomes", Income),
    ("expenses", Expense),
    ("goals", Goal),
    ("investments", Investment),
    ("other_debts", OtherDebt),
    ("splits", SplitShare),
]
SKIP_COLUMNS = {"user_id", "import_batch_id"}


def _backup_summary(data: dict[str, Any]) -> dict[str, int]:
    return {key: len(data.get(key) or []) for key, _ in BACKUP_TABLES}


def _convert(column: Any, value: Any) -> Any:
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, TypeDecorator):  # ex.: UTCDateTime guarda um DateTime por baixo
        kind = kind.impl if isinstance(kind.impl, TypeEngine) else kind.impl_instance
    if isinstance(kind, Uuid):
        return uuid.UUID(str(value))
    if isinstance(kind, DateTime):
        return datetime.fromisoformat(str(value))
    if isinstance(kind, Date):
        return date.fromisoformat(str(value)[:10])
    if isinstance(kind, Numeric):
        return Decimal(str(value))
    if isinstance(kind, Boolean):
        return bool(value)
    if isinstance(kind, Integer | SmallInteger):
        return int(value)
    return value


def restore_backup(db: Session, user: User, data: dict[str, Any]) -> dict[str, int]:
    """Restaura o backup: recria o que não existe (mesmos identificadores), sem duplicar.

    Categorias com o mesmo nome de uma já existente são unificadas.
    """
    if data.get("format") != "meu-orcamento-backup":
        raise AppError(400, "invalid_file", "Arquivo não é um backup do Meu Orçamento.")
    counts = {key: 0 for key, _ in BACKUP_TABLES}
    category_map: dict[uuid.UUID, uuid.UUID] = {}
    by_name = {normalize_text(c.name): c.id for c in budget.list_categories(db, user)}
    batch = ImportBatch(user_id=user.id, filename="backup", file_format="backup")
    db.add(batch)
    db.flush()
    opened: set[date] = set()
    for key, model in BACKUP_TABLES:
        columns = {c.key: c for c in model.__table__.columns if c.key not in SKIP_COLUMNS}
        for row in data.get(key) or []:
            if not isinstance(row, dict) or "id" not in row:
                continue
            try:
                values = {k: _convert(columns[k], v) for k, v in row.items() if k in columns}
            except (ValueError, TypeError, ArithmeticError):
                continue
            if model is Category:
                existing_id = by_name.get(normalize_text(str(values.get("name", ""))))
                if existing_id:
                    category_map[values["id"]] = existing_id
                    continue
            if db.get(model, values["id"]) is not None:
                continue
            if "category_id" in values and values["category_id"] in category_map:
                values["category_id"] = category_map[values["category_id"]]
            if model in (Income, Expense):
                values["import_batch_id"] = batch.id
                if values.get("month"):
                    opened.add(values["month"])
            db.add(model(user_id=user.id, **values))
            db.flush()
            counts[key] += 1
    for month in opened:
        budget.ensure_month(db, user, month)
    batch.count = counts["incomes"] + counts["expenses"]
    db.commit()
    return counts
