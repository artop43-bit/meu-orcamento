"""Leitura de comprovante por foto (v1.3): valor, data e descrição para a pessoa conferir.

A leitura roda no próprio servidor (Tesseract, sem serviço externo): a foto não sai do app.
- Boleto: a linha digitável traz o valor e o vencimento exatos (fator de vencimento).
- Cupom, nota ou recibo: procura o total, a data e o nome do estabelecimento no texto.
Nada é salvo sozinho: o resultado só preenche o formulário, e a pessoa confirma.
"""

import io
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageOps

from app.core.errors import AppError
from app.services import files

# Um processo de cada vez: a VM tem poucos núcleos e a leitura é pesada.
_LOCK = threading.Semaphore(1)
TIMEOUT = 40  # segundos

MONEY = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?![\d,])")
DATE = re.compile(r"(?<!\d)(\d{2})[/.-](\d{2})[/.-](\d{4}|\d{2})(?!\d)")
TOTAL_WORDS = re.compile(
    r"(valor\s+(total|a\s+pagar|pago|cobrado|do\s+documento)|total(\s+a\s+pagar|\s+r\$|\s+geral)?\b"
    r"|a\s+pagar)",
    re.I,
)
SKIP_LINE = re.compile(
    r"cnpj|cpf|cupom|documento|auxiliar|nfc-?e|nota\s+fiscal|sat\b|extrato|ie\s*:|im\s*:|"
    r"rua|av\.|avenida|cep|tel|fone|www|http|consumidor|protocolo|chave|via\s",
    re.I,
)


@dataclass
class Reading:
    kind: str  # "boleto" | "cupom" | "desconhecido"
    amount: Decimal | None
    date: date | None
    description: str | None


def _money(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


# ---------------------------------------------------------------- boleto


def _boleto(digits: str, today: date) -> Reading | None:
    """Linha digitável de boleto bancário (47 dígitos): valor e vencimento exatos."""
    if len(digits) != 47:
        return None
    factor = int(digits[33:37])
    cents = int(digits[37:47])
    due = None
    if factor:
        # O fator recomeçou em 1000 no dia 22/02/2025; vale a data mais próxima de hoje.
        old = date(1997, 10, 7) + timedelta(days=factor)
        new = date(2025, 2, 22) + timedelta(days=factor - 1000)
        due = min((old, new), key=lambda d: abs((d - today).days))
    amount = Decimal(cents) / 100 if cents else None
    return Reading("boleto", amount, due, "Boleto")


def _find_boleto(text: str, today: date) -> Reading | None:
    for line in text.splitlines():
        digits = re.sub(r"\D", "", line)
        if len(digits) == 47:
            return _boleto(digits, today)
    joined = re.sub(r"\D", "", text)
    match = re.search(r"\d{47}", joined)
    if match and re.search(r"boleto|banco|benefici|vencimento|linha", text, re.I):
        return _boleto(match.group(0), today)
    return None


# ---------------------------------------------------------------- cupom, nota ou recibo


def _date(text: str, today: date) -> date | None:
    found: list[date] = []
    for day, month, year in DATE.findall(text):
        full = int(year) + (2000 if len(year) == 2 else 0)
        try:
            value = date(full, int(month), int(day))
        except ValueError:
            continue
        if date(2000, 1, 1) <= value <= today + timedelta(days=400):
            found.append(value)
    if not found:
        return None
    # Data da compra: a mais recente que não está no futuro (validade e vencimento ficam depois).
    past = [d for d in found if d <= today]
    return max(past) if past else min(found)


def _amount(text: str) -> Decimal | None:
    lines = text.splitlines()
    totals: list[Decimal] = []
    for index, line in enumerate(lines):
        if TOTAL_WORDS.search(line) and not re.search(r"troco|desconto|tribut|imposto", line, re.I):
            values = MONEY.findall(line)
            if not values and index + 1 < len(lines):
                values = MONEY.findall(lines[index + 1])
            totals.extend(v for v in (_money(x) for x in values) if v)
    if totals:
        return max(totals)
    every = [v for v in (_money(x) for x in MONEY.findall(text)) if v]
    return max(every) if every else None


def _description(text: str) -> str | None:
    for line in text.splitlines()[:8]:
        clean = re.sub(r"[^\wÀ-ú&.\- ]", " ", line).strip()
        clean = re.sub(r"\s+", " ", clean)
        letters = sum(c.isalpha() for c in clean)
        if letters >= 4 and not SKIP_LINE.search(clean) and not MONEY.search(clean):
            return clean[:60].title()
    return None


def parse(text: str, today: date | None = None) -> Reading:
    """Interpreta o texto lido da foto (separado da leitura para poder testar)."""
    today = today or date.today()
    boleto = _find_boleto(text, today)
    if boleto:
        return boleto
    amount, when, description = _amount(text), _date(text, today), _description(text)
    kind = "cupom" if amount or when else "desconhecido"
    return Reading(kind, amount, when, description)


# ---------------------------------------------------------------- leitura da imagem


def available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(raw: bytes) -> bytes:
    """Foto pronta para leitura: em pé, cinza, com contraste e tamanho bom para o OCR."""
    files.prepare(raw, "receipt")  # mesma validação dos comprovantes (tipo, tamanho, pixels)
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    if max(image.size) < 1600:
        scale = 1600 / max(image.size)
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    image = ImageOps.autocontrast(image)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def read_text(raw: bytes) -> str:
    if not available():
        raise AppError(503, "ocr_unavailable", "A leitura de fotos não está disponível agora.")
    image = _prepare(raw)
    if not _LOCK.acquire(timeout=60):
        raise AppError(
            503, "ocr_busy", "Muitas leituras ao mesmo tempo. Tente de novo em instantes."
        )
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "por", "--psm", "6"],
            input=image,
            capture_output=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            504, "ocr_timeout", "A leitura demorou demais. Tente uma foto mais nítida."
        ) from exc
    finally:
        _LOCK.release()
    if result.returncode != 0:
        raise AppError(422, "ocr_failed", "Não foi possível ler a foto. Tente outra mais nítida.")
    return result.stdout.decode("utf-8", errors="ignore")


def read(raw: bytes) -> Reading:
    return parse(read_text(raw))
