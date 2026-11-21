"""Leitor universal de CSV (detecção automática de codificação, delimitador e tipos)."""

from __future__ import annotations

import csv
import io
from typing import Any

from app.core.errors import AppError
from app.services.crm.pdf_reader import MAX_ROWS, build_schema_and_rows, suggest_crm_mapping

MAX_CSV_BYTES = 10 * 1024 * 1024


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AppError(400, "invalid_encoding", "Não foi possível ler a codificação deste arquivo CSV.")


def _detect_delimiter(sample: str) -> str:
    lines = [line for line in sample.splitlines()[:10] if line.strip()]
    joined = "\n".join(lines)
    if not joined:
        return ","
    try:
        dialect = csv.Sniffer().sniff(joined, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {delim: joined.count(delim) for delim in (";", ",", "\t", "|")}
        best = max(counts.items(), key=lambda kv: kv[1])
        return best[0] if best[1] > 0 else ","


def extract_csv(content: bytes, delimiter: str | None = None) -> dict[str, Any]:
    if not content:
        raise AppError(400, "empty_file", "O arquivo CSV enviado está vazio.")
    if len(content) > MAX_CSV_BYTES:
        raise AppError(400, "file_too_large", "O CSV excede o limite de 10 MB.")

    text = _decode_csv(content)
    delim = delimiter or _detect_delimiter(text)
    if len(delim) != 1 or delim in "\r\n\0":
        raise AppError(400, "invalid_delimiter", "Escolha um separador de apenas um caractere.")
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delim, strict=True)
        matrix = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise AppError(
            400, "invalid_csv", "Não foi possível ler este CSV. Confira o separador e as aspas."
        ) from exc
    if len(matrix) < 2:
        raise AppError(
            400, "empty_csv", "O CSV precisa ter cabeçalho e pelo menos uma linha de dados."
        )

    headers = [cell.strip() for cell in matrix[0]]
    body = matrix[1 : MAX_ROWS + 1]
    schema, rows = build_schema_and_rows(headers, body)
    return {
        "delimiter": delim,
        "columns": schema,
        "rows": rows,
        "total_rows": len(rows),
        "suggestions": suggest_crm_mapping(schema),
    }
