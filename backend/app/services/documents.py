"""Anexos de documento nas solicitações (v1.3.1): PDF e planilhas (XLSX, XLS, CSV e ODS).

O tipo é conferido pelo conteúdo do arquivo, nunca pela extensão ou pelo cabeçalho do envio.
Planilhas com macros são recusadas. Documentos nunca abrem dentro do app: só baixam, com o tipo
fixo e sem "adivinhação" do navegador (ver /api/files).
"""

import io
import re
import zipfile

from app.core.errors import AppError

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS = "application/vnd.ms-excel"
ODS = "application/vnd.oasis.opendocument.spreadsheet"
CSV = "text/csv"
EXTENSIONS = {PDF: "pdf", XLSX: "xlsx", XLS: "xls", ODS: "ods", CSV: "csv"}
DOCUMENT_TYPES = set(EXTENSIONS)

OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_LIMIT = 60 * 1024 * 1024  # conteúdo descompactado (proteção contra "bomba" de zip)
NO_MACROS = "Planilhas com macros não são aceitas. Salve como .xlsx comum e envie de novo."


def _zip_type(raw: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = set(archive.namelist())
            if sum(info.file_size for info in archive.infolist()) > ZIP_LIMIT:
                raise AppError(400, "invalid_file", "Arquivo compactado grande demais.")
            if "xl/workbook.xml" in names:
                types = (
                    archive.read("[Content_Types].xml") if "[Content_Types].xml" in names else b""
                )
                if "xl/vbaProject.bin" in names or b"macroEnabled" in types:
                    raise AppError(400, "macros_not_allowed", NO_MACROS)
                return XLSX
            if "mimetype" in names and archive.read("mimetype").strip() == ODS.encode():
                if any(n.lower().startswith("basic/") for n in names):
                    raise AppError(400, "macros_not_allowed", NO_MACROS)
                return ODS
    except zipfile.BadZipFile:
        return None
    return None


def _is_csv(raw: bytes) -> bool:
    if b"\x00" in raw:
        return False
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    first = text.splitlines()[0] if text.strip() else ""
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text[:4000])
    return (
        bool(first) and bool(re.search(r"[,;\t]", first)) and printable >= len(text[:4000]) * 0.97
    )


def detect(raw: bytes) -> str | None:
    """Tipo do documento pelo conteúdo (None se não for um documento aceito)."""
    if raw.startswith(b"%PDF-"):
        return PDF
    if raw.startswith(b"PK\x03\x04"):
        return _zip_type(raw)
    if raw.startswith(OLE):
        # Planilha antiga do Excel: o projeto de macros aparece no diretório do arquivo.
        if "_VBA_PROJECT".encode("utf-16-le") in raw or b"_VBA_PROJECT" in raw:
            raise AppError(400, "macros_not_allowed", NO_MACROS)
        if "Workbook".encode("utf-16-le") in raw or "Book".encode("utf-16-le") in raw:
            return XLS
        return None
    if _is_csv(raw):
        return CSV
    return None


def safe_name(name: str | None, content_type: str) -> str:
    """Nome para o download: sem caminhos nem caracteres estranhos, com a extensão certa."""
    base = (name or "arquivo").replace("\\", "/").split("/")[-1]
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base)
    base = re.sub(r"[^\w\- .()À-ú]", "_", base).strip(" ._") or "arquivo"
    return f"{base[:100]}.{EXTENSIONS[content_type]}"
