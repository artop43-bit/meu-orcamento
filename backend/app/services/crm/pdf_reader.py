"""Leitor universal de PDF 100% local (tabelas nativas + texto estruturado + OCR local RapidOCR).

Traduz qualquer PDF (relatório tabular, extrato, ficha cadastral, contrato ou documento escaneado)
para colunas tipadas e linhas estruturadas prontas para Dashboards e importação no CRM.
Sem custo e sem chamadas a IA/serviços externos.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from app.core.errors import AppError
from app.services import ocr as receipt_ocr
from app.services.crm.parsing import (
    CURRENCY_RE,
    DATE_BR_RE,
    DATE_ISO_RE,
    EMAIL_RE,
    PHONE_RE,
    coerce_cell,
    infer_column_type,
    parse_date,
    parse_number,
    slugify_column,
)

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_OCR_PAGES = 5
MAX_ROWS = 5000
MIN_DIGITAL_CHARS = 20

MAX_PAGE_PIXELS = 12_000_000


def _try_pypdf_reader(content: bytes) -> Any:
    try:
        from pypdf import PdfReader

        return PdfReader(io.BytesIO(content))
    except Exception:
        return None


@dataclass
class PageText:
    page_number: int
    text: str
    used_ocr: bool = False


@dataclass
class PdfExtraction:
    strategy: str
    used_ocr: bool
    pages: int
    ocr_pages: int
    raw_text_excerpt: str
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    suggestions: dict[str, Any] = field(default_factory=dict)
    warning: str | None = None


def _unique_columns(raw_headers: list[str]) -> list[tuple[str, str]]:
    """Devolve lista de (key_slug, label_legivel) garantindo nomes únicos."""
    used: dict[str, int] = {}
    out: list[tuple[str, str]] = []
    for idx, raw in enumerate(raw_headers):
        label = re.sub(r"\s+", " ", (raw or "").strip()) or f"Coluna {idx + 1}"
        base = slugify_column(label, f"coluna_{idx + 1}")
        count = used.get(base, 0) + 1
        used[base] = count
        key = base if count == 1 else f"{base}_{count}"
        out.append((key, label[:60]))
    return out


def _clean_cell(val: object) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def _ocr_page(page: pymupdf.Page) -> str:
    """Usa o mesmo motor e a mesma fila do leitor de cupons, com renderização limitada."""
    width, height = float(page.rect.width), float(page.rect.height)
    if not all(math.isfinite(side) and side > 0 for side in (width, height)):
        raise AppError(422, "invalid_pdf_page", "O PDF contém uma página com tamanho inválido.")
    area = max(width * height, 1.0)
    # PyMuPDF arredonda as bordas para pixels inteiros: reserve essa margem antes de renderizar.
    render_budget = MAX_PAGE_PIXELS - 4 * 4096
    scale = min(200 / 72, (render_budget / area) ** 0.5, 4096 / max(width, height))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB)
    return receipt_ocr.extract(pix.tobytes("png")).texto_extraido


def _extract_native_tables(doc: pymupdf.Document) -> tuple[list[str], list[list[str]]] | None:
    """Extrai tabelas nativas detectadas pelo PyMuPDF unindo páginas com o mesmo cabeçalho."""
    best_headers: list[str] = []
    best_rows: list[list[str]] = []
    candidates: list[tuple[list[str], list[list[str]]]] = []

    for page_index in range(min(len(doc), MAX_PDF_PAGES)):
        page = doc[page_index]
        try:
            finder = page.find_tables()
            tables = list(getattr(finder, "tables", []) or [])
        except Exception:
            tables = []
        for table in tables:
            raw_matrix = table.extract() or []
            rows_meta = getattr(table, "rows", None)
            if rows_meta:
                bbox_matrix: list[list[str]] = []
                for row_obj in rows_meta:
                    row_cells: list[str] = []
                    for cell_bbox in getattr(row_obj, "cells", []) or []:
                        if cell_bbox is None:
                            row_cells.append("")
                        else:
                            txt = page.get_text("text", clip=pymupdf.Rect(cell_bbox)) or ""
                            row_cells.append(_clean_cell(txt))
                    if any(row_cells):
                        bbox_matrix.append(row_cells)
                if len(bbox_matrix) >= 2:
                    matrix = bbox_matrix
                else:
                    matrix = [
                        [_clean_cell(c) for c in row]
                        for row in raw_matrix
                        if row and any(_clean_cell(c) for c in row)
                    ]
            else:
                matrix = [
                    [_clean_cell(c) for c in row]
                    for row in raw_matrix
                    if row and any(_clean_cell(c) for c in row)
                ]
            if len(matrix) < 2:
                continue
            width = max(len(r) for r in matrix)
            if width < 2:
                continue
            normalized = [r + [""] * (width - len(r)) for r in matrix]
            headers = normalized[0]
            data_rows = normalized[1:]
            if sum(1 for h in headers if not h or parse_number(h) is not None) > width / 2:
                headers = [f"Coluna {i + 1}" for i in range(width)]
                data_rows = normalized

            merged = False
            for existing_headers, existing_rows in candidates:
                if len(existing_headers) == len(headers) and [
                    slugify_column(h) for h in existing_headers
                ] == [slugify_column(h) for h in headers]:
                    existing_rows.extend(data_rows)
                    merged = True
                    break
            if not merged:
                candidates.append((headers, data_rows))

    for headers, rows in candidates:
        header_sig = [h.lower() for h in headers]
        cleaned = [r for r in rows if [c.lower() for c in r] != header_sig and any(r)]
        if len(cleaned) > len(best_rows):
            best_headers, best_rows = headers, cleaned

    if best_rows and len(best_headers) >= 2:
        return best_headers, best_rows[:MAX_ROWS]
    return None


def _parse_aligned_columns(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """Detecta tabelas separadas por '|', tabulação, ';' ou múltiplos espaços."""
    clean_lines = [line.strip() for line in lines if line.strip()]
    if len(clean_lines) < 3:
        return None

    for pattern in (r"\s*\|\s*", r"\t+", r"\s*;\s*", r"\s{2,}"):
        split_rows: list[list[str]] = []
        for line in clean_lines:
            if re.fullmatch(r"[-=_+| ]{4,}", line):
                continue
            cells = [c.strip() for c in re.split(pattern, line.strip("| ")) if c.strip() != ""]
            if len(cells) >= 2:
                split_rows.append(cells)

        if len(split_rows) < 3:
            continue
        counts: dict[int, int] = {}
        for row in split_rows:
            counts[len(row)] = counts.get(len(row), 0) + 1
        target_cols, freq = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
        if target_cols < 2 or freq < 3 or freq / len(split_rows) < 0.55:
            continue

        matched = [r for r in split_rows if len(r) == target_cols]
        first = matched[0]
        non_data = sum(
            1 for cell in first if parse_number(cell) is None and parse_date(cell) is None
        )
        if non_data >= max(1, target_cols - 1):
            headers = first
            body = matched[1:]
        else:
            headers = [f"Coluna {i + 1}" for i in range(target_cols)]
            body = matched
        if len(body) >= 2:
            return headers, body[:MAX_ROWS]
    return None


def _parse_financial_lines(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """Detecta linhas de extrato / relatório com data + descrição + valor monetário."""
    rows: list[list[str]] = []
    amount_tail = re.compile(
        r"([-+]?\s*(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|[-+]?\s*R\$\s*\d+(?:[.,]\d{2})?)\s*([CDcd])?$"
    )
    for raw in lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) < 10:
            continue
        date_m = DATE_BR_RE.search(line) or DATE_ISO_RE.search(line)
        amt_m = amount_tail.search(line)
        if not date_m or not amt_m:
            continue
        date_str = parse_date(date_m.group(0))
        num = parse_number(amt_m.group(1))
        if not date_str or num is None:
            continue
        dc = (amt_m.group(2) or "").upper()
        if dc == "D" and num > 0:
            num = -num
        desc = line[date_m.end() : amt_m.start()].strip(" -–|;:")
        if not desc:
            desc = line[: date_m.start()].strip(" -–|;:") or "Registro"
        kind = "Saída" if num < 0 else "Entrada"
        rows.append([date_str, desc[:160], f"{num:.2f}", kind])

    if len(rows) >= 2:
        return ["Data", "Descrição", "Valor", "Tipo"], rows[:MAX_ROWS]
    return None


def _parse_key_value_blocks(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """Extrai fichas estruturadas no padrão 'Campo: Valor' (1 ou vários registros)."""
    kv_re = re.compile(r"^([A-Za-zÀ-ÿ0-9 _/().-]{2,36}):\s+(.+)$")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    key_order: list[str] = []

    def _flush() -> None:
        nonlocal current
        if len(current) >= 2:
            records.append(current)
        current = {}

    for raw in lines:
        line = raw.strip()
        if not line or re.fullmatch(r"[-=_*]{4,}", line):
            if len(current) >= 2:
                _flush()
            continue
        m = kv_re.match(line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        value = m.group(2).strip()
        if not label or not value:
            continue
        slug = slugify_column(label)
        if slug in {slugify_column(k) for k in current}:
            _flush()
        current[label] = value
        if not any(slugify_column(k) == slug for k in key_order):
            key_order.append(label)
    _flush()

    if not records or len(key_order) < 2:
        return None
    if len(records) == 1 and len(records[0]) < 3:
        return None

    headers = key_order
    rows: list[list[str]] = []
    for rec in records[:MAX_ROWS]:
        by_slug = {slugify_column(k): v for k, v in rec.items()}
        rows.append([by_slug.get(slugify_column(h), "") for h in headers])
    return headers, rows


def _parse_free_document(pages: list[PageText]) -> tuple[list[str], list[list[str]]]:
    """Fallback para qualquer PDF narrativo/livre: estrutura por seção/bloco com entidades."""
    headers = [
        "Página",
        "Seção",
        "Conteúdo",
        "Data detectada",
        "Valor detectado",
        "Contato detectado",
    ]
    rows: list[list[str]] = []
    heading_re = re.compile(r"^(?:\d+[\.\)]\s+)[A-ZÀ-Ý].{1,75}$")

    for page in pages:
        sections: list[tuple[str, list[str]]] = []
        current_title = f"Página {page.page_number}"
        current_buf: list[str] = []

        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                joined = re.sub(r"\s+", " ", " ".join(current_buf)).strip()
                if joined:
                    sections.append((current_title, [joined]))
                current_buf = []
                continue
            if heading_re.match(line) or (
                len(line) <= 60
                and not line.endswith(".")
                and line.isupper()
                and any(ch.isalpha() for ch in line)
            ):
                joined = re.sub(r"\s+", " ", " ".join(current_buf)).strip()
                if joined:
                    sections.append((current_title, [joined]))
                current_buf = []
                current_title = line
                continue
            current_buf.append(line)
        joined = re.sub(r"\s+", " ", " ".join(current_buf)).strip()
        if joined:
            sections.append((current_title, [joined]))

        for section_title, blocks in sections:
            for para in blocks:
                date_m = DATE_BR_RE.search(para) or DATE_ISO_RE.search(para)
                amt_m = CURRENCY_RE.search(para)
                email_m = EMAIL_RE.search(para)
                phone_m = PHONE_RE.search(para)
                contact = email_m.group(0) if email_m else (phone_m.group(0) if phone_m else "")
                date_val = parse_date(date_m.group(0)) if date_m else ""
                amt_num = parse_number(amt_m.group(0)) if amt_m else None
                rows.append(
                    [
                        str(page.page_number),
                        section_title[:80],
                        para[:500],
                        date_val or "",
                        f"{amt_num:.2f}" if amt_num is not None else "",
                        contact,
                    ]
                )
                if len(rows) >= MAX_ROWS:
                    return headers, rows

    if not rows:
        rows.append(["1", "Documento", "(Sem texto reconhecível no PDF)", "", "", ""])
    return headers, rows


def build_schema_and_rows(
    raw_headers: list[str],
    raw_rows: list[list[Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Infere tipos de coluna e normaliza todas as células para o formato tabular do sistema."""
    col_defs = _unique_columns(raw_headers)
    col_values: list[list[Any]] = [[] for _ in col_defs]
    for row in raw_rows[:MAX_ROWS]:
        for idx in range(len(col_defs)):
            col_values[idx].append(row[idx] if idx < len(row) else None)

    schema: list[dict[str, str]] = []
    for idx, (key, label) in enumerate(col_defs):
        col_type = infer_column_type(label, col_values[idx])
        schema.append({"name": key, "label": label, "type": col_type})

    normalized_rows: list[dict[str, Any]] = []
    for row in raw_rows[:MAX_ROWS]:
        record: dict[str, Any] = {}
        has_any = False
        for idx, col in enumerate(schema):
            val = row[idx] if idx < len(row) else None
            coerced = coerce_cell(val, col["type"])
            if coerced is not None and coerced != "":
                has_any = True
            record[col["name"]] = coerced
        if has_any:
            normalized_rows.append(record)
    return schema, normalized_rows


def suggest_crm_mapping(schema: list[dict[str, str]]) -> dict[str, Any]:
    """Sugere como traduzir as colunas lidas para Contatos, Negócios ou Dashboard."""
    by_name = {c["name"]: c for c in schema}

    def _pick(keywords: tuple[str, ...], preferred_type: str | None = None) -> str | None:
        if preferred_type:
            for col in schema:
                if col["type"] == preferred_type and any(k in col["name"] for k in keywords):
                    return col["name"]
        for col in schema:
            if any(k in col["name"] for k in keywords):
                return col["name"]
        if preferred_type:
            for col in schema:
                if col["type"] == preferred_type:
                    return col["name"]
        return None

    contact_map = {
        "name": _pick(("cliente", "nome", "contato", "lead", "pessoa", "razao", "name")),
        "phone": _pick(("telefone", "celular", "whatsapp", "fone", "phone"), "phone"),
        "email": _pick(("email", "e_mail", "mail"), "email"),
        "company": _pick(("empresa", "companhia", "organizacao", "loja", "company")),
        "notes": _pick(("observac", "nota", "detalhe", "resumo", "conteudo", "notes")),
    }
    deal_map = {
        "title": _pick(
            ("negocio", "oportunidade", "titulo", "produto", "servico", "descricao", "secao")
        ),
        "value": _pick(("valor", "total", "preco", "receita", "faturamento", "amount"), "currency")
        or _pick(("valor", "total", "preco"), "number"),
        "contact_name": contact_map["name"],
        "expected_close_date": _pick(
            ("previsao", "vencimento", "fechamento", "data", "date"), "date"
        ),
        "notes": contact_map["notes"],
    }

    has_contact = bool(contact_map["name"] and (contact_map["phone"] or contact_map["email"]))
    has_deal = bool(deal_map["title"] and deal_map["value"])
    if has_deal and not has_contact:
        recommended = "deals"
    elif has_contact and not has_deal:
        recommended = "contacts"
    elif has_contact and has_deal:
        recommended = "deals"
    else:
        recommended = "dataset"

    return {
        "recommended_target": recommended,
        "contact_mapping": {k: v for k, v in contact_map.items() if v and v in by_name},
        "deal_mapping": {k: v for k, v in deal_map.items() if v and v in by_name},
    }


def extract_pdf(content: bytes, filename: str = "documento.pdf") -> PdfExtraction:
    """Lê qualquer PDF (digital ou escaneado) localmente e traduz em dados estruturados."""
    if not content:
        raise AppError(400, "empty_file", "O arquivo PDF enviado está vazio.")
    if len(content) > MAX_PDF_BYTES:
        raise AppError(400, "file_too_large", "O PDF excede o limite de 15 MB.")
    if not content.lstrip().startswith(b"%PDF"):
        raise AppError(400, "invalid_pdf", "O arquivo enviado não é um PDF válido.")

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise AppError(400, "invalid_pdf", "Não foi possível abrir este arquivo PDF.") from exc

    try:
        total_pages = len(doc)
        if total_pages == 0:
            raise AppError(400, "empty_pdf", "O PDF não possui páginas.")
        pages_to_read = min(total_pages, MAX_PDF_PAGES)

        native_table = _extract_native_tables(doc)

        pages_text: list[PageText] = []
        ocr_pages = 0
        ocr_truncated = False
        pypdf_fallback: Any = None
        pypdf_tried = False

        for idx in range(pages_to_read):
            page = doc[idx]
            text = (page.get_text("text") or "").strip()
            if len(text) < MIN_DIGITAL_CHARS and not pypdf_tried:
                pypdf_tried = True
                pypdf_fallback = _try_pypdf_reader(content)
            if len(text) < MIN_DIGITAL_CHARS and pypdf_fallback is not None:
                if idx < len(pypdf_fallback.pages):
                    alt = (pypdf_fallback.pages[idx].extract_text() or "").strip()
                    if len(alt) > len(text):
                        text = alt

            used_ocr = False
            if len(text) < MIN_DIGITAL_CHARS:
                if ocr_pages >= MAX_OCR_PAGES:
                    ocr_truncated = True
                else:
                    ocr_text = _ocr_page(page)
                    if ocr_text:
                        text = ocr_text
                        used_ocr = True
                        ocr_pages += 1

            pages_text.append(PageText(page_number=idx + 1, text=text, used_ocr=used_ocr))
    finally:
        doc.close()

    full_text = "\n\n".join(p.text for p in pages_text if p.text).strip()
    all_lines = [line for p in pages_text for line in p.text.splitlines()]
    used_ocr_any = ocr_pages > 0

    strategy = "documento_livre"
    headers: list[str]
    raw_rows: list[list[str]]

    if native_table is not None:
        headers, raw_rows = native_table
        strategy = "tabela_pdf"
    else:
        parsed_cols = _parse_aligned_columns(all_lines)
        if parsed_cols is not None:
            headers, raw_rows = parsed_cols
            strategy = "ocr_tabela" if used_ocr_any else "colunas_texto"
        else:
            parsed_fin = _parse_financial_lines(all_lines)
            if parsed_fin is not None:
                headers, raw_rows = parsed_fin
                strategy = "ocr_financeiro" if used_ocr_any else "linhas_financeiras"
            else:
                parsed_kv = _parse_key_value_blocks(all_lines)
                if parsed_kv is not None:
                    headers, raw_rows = parsed_kv
                    strategy = "ocr_campos" if used_ocr_any else "pares_chave_valor"
                else:
                    headers, raw_rows = _parse_free_document(pages_text)
                    strategy = "ocr_texto" if used_ocr_any else "documento_livre"

    schema, rows = build_schema_and_rows(headers, raw_rows)
    suggestions = suggest_crm_mapping(schema)

    return PdfExtraction(
        strategy=strategy,
        used_ocr=used_ocr_any,
        pages=total_pages,
        ocr_pages=ocr_pages,
        raw_text_excerpt=full_text[:1500],
        columns=schema,
        rows=rows,
        suggestions=suggestions,
        warning="Leia até 5 páginas digitalizadas por vez." if ocr_truncated else None,
    )
