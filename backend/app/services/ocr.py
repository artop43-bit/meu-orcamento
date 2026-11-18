"""Leitura de comprovante por foto (v1.3): valor, data e descrição para a pessoa conferir.

A leitura roda no próprio servidor, sem serviço externo: a foto não sai do app.
v1.10: quem lê a foto é o leitor de cupons (`leitor_comprovantes`, RapidOCR em CPU), no lugar
do Tesseract. As regras de texto deste arquivo continuam valendo como reserva campo a campo.
- Boleto: a linha digitável traz o valor e o vencimento exatos (fator de vencimento).
- Cupom, nota ou recibo: procura o total, a data e o nome do estabelecimento no texto, e
  (v1.5) os produtos com o valor de cada um.
Nada é salvo sozinho: o resultado só preenche o formulário, e a pessoa confirma.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from app.core.errors import AppError
from app.services import files

if TYPE_CHECKING:
    from leitor_comprovantes import LeitorComprovantes, ResultadoComprovante

# Uma leitura de cada vez: o OCR usa todos os núcleos e bastante memória.
_LOCK = threading.Semaphore(1)
# O leitor carrega os modelos uma vez só (na primeira leitura) e é reaproveitado.
_LEITOR: LeitorComprovantes | None = None
_LEITOR_LOCK = threading.Lock()
logger = logging.getLogger(__name__)

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


# Linhas com valor que não são produto (pagamento, troco, descontos, tributos, contagem).
NOT_ITEM = re.compile(
    r"troco|desconto|acr[eé]scimo|sub\s*-?total|qtd|itens|dinheiro|cart[aã]o|cr[eé]dito|"
    r"d[eé]bito|\bpix\b|pagamento|pago|tribut|imposto|lei\s*12|aprox|saldo",
    re.I,
)
# Quantidade e unidade no meio da linha ("2 UN X 8,49", "0,512 KG"): o nome vem antes.
QUANTITY = re.compile(r"\s\d+(?:[.,]\d+)?\s*(?:un|und|kg|g|lt?|ml|pc|pct|cx|fd)\b", re.I)
MAX_ITEMS = 30

# v1.9.0.1: nas linhas de total o OCR às vezes troca a vírgula por ponto ("279.17").
MONEY_OCR = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[.,]\d{2})(?![\d,.])")
# Somas que não são o total da compra.
OTHER_SUM = re.compile(r"troco|desconto|acr[eé]scimo|tribut|imposto|sub\s*-?total|itens", re.I)
PAYMENTS = (
    ("pix", r"\bpix\b"),
    ("credit", r"cr[eé]dito"),
    ("debit", r"d[eé]bito"),
    ("cash", r"dinheiro|esp[eé]cie"),
)
PAYMENT_LINE = re.compile("|".join(p for _, p in PAYMENTS) + r"|cart[aã]o", re.I)


@dataclass
class Item:
    description: str
    amount: Decimal


@dataclass
class Reading:
    kind: str  # "boleto" | "cupom" | "desconhecido"
    amount: Decimal | None
    date: date | None
    description: str | None
    # v1.5: produtos do cupom (nome e valor da linha), para dividir a compra por categoria.
    items: list[Item] = field(default_factory=list)
    # v1.9.0.1: forma de pagamento ("pix" | "debit" | "credit" | "boleto" | "cash"), se clara.
    payment_method: str | None = None


def _money(text: str) -> Decimal | None:
    try:
        if "," not in text:  # "279.17": o OCR trocou a vírgula por ponto (só nas linhas de total)
            return Decimal(text)
        return Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


# ---------------------------------------------------------------- boleto


def _mod10(digits: str) -> int:
    total, weight = 0, 2
    for char in reversed(digits):
        product = int(char) * weight
        total += product // 10 + product % 10
        weight = 1 if weight == 2 else 2
    return (10 - total % 10) % 10


def _mod11(digits: str) -> int:
    total, weight = 0, 2
    for char in reversed(digits):
        total += int(char) * weight
        weight = 2 if weight == 9 else weight + 1
    rest = 11 - total % 11
    return 1 if rest in (0, 1, 10, 11) else rest


def _valid_line(digits: str) -> bool:
    """Linha digitável de verdade: os três campos (módulo 10) e o código de barras (módulo 11).

    v1.9.0.1: sem isso, 47 números quaisquer de um cupom (CNPJ, chave de acesso, protocolo)
    viravam um "boleto" com valor e vencimento inventados.
    """
    if len(digits) != 47:
        return False
    fields = ((digits[0:9], digits[9]), (digits[10:20], digits[20]), (digits[21:31], digits[31]))
    if any(_mod10(body) != int(dv) for body, dv in fields):
        return False
    free = digits[4:9] + digits[10:20] + digits[21:31]
    return _mod11(digits[0:4] + digits[33:47] + free) == int(digits[32])


def _boleto(digits: str, today: date) -> Reading | None:
    """Linha digitável de boleto bancário (47 dígitos): valor e vencimento exatos."""
    if not _valid_line(digits):
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
    return Reading("boleto", amount, due, "Boleto", payment_method="boleto")


def _find_boleto(text: str, today: date) -> Reading | None:
    """A linha digitável fica numa linha só ou quebrada em duas seguidas (fotos estreitas)."""
    lines = [re.sub(r"\D", "", line) for line in text.splitlines()]
    candidates = lines + [a + b for a, b in zip(lines, lines[1:], strict=False)]
    for digits in candidates:
        for start in range(len(digits) - 46):
            found = _boleto(digits[start : start + 47], today)
            if found:
                return found
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


def _total_rank(line: str) -> int:
    """Quanto a linha vale como total: 3 = a pagar (depois do desconto), 2 = total, 1 = pago."""
    if re.search(r"a\s+pagar|valor\s+cobrado|valor\s+do\s+documento", line, re.I):
        return 3
    if re.search(r"valor\s+pago", line, re.I):
        return 1  # o pago pode incluir o troco ("pago 50,00, troco 5,12")
    return 2


def _amount(text: str) -> Decimal | None:
    lines = text.splitlines()
    totals: list[tuple[int, Decimal]] = []
    for index, line in enumerate(lines):
        if not TOTAL_WORDS.search(line) or OTHER_SUM.search(line):
            continue
        values = MONEY_OCR.findall(line)
        # "VALOR PAGO R$" com o valor na linha de baixo ("Dinheiro 270,00"); nunca a linha de
        # desconto, acréscimo ou troco, nem um produto.
        if not values and index + 1 < len(lines):
            below = lines[index + 1]
            if not OTHER_SUM.search(below) and (
                PAYMENT_LINE.search(below) or sum(c.isalpha() for c in below) <= 3
            ):
                values = MONEY_OCR.findall(below)
        rank = _total_rank(line)
        totals.extend((rank, v) for v in (_money(x) for x in values) if v)
    if totals:
        best = max(rank for rank, _ in totals)
        return max(v for rank, v in totals if rank == best)
    every = [v for v in (_money(x) for x in MONEY.findall(text)) if v]
    return max(every) if every else None


def _discount(text: str) -> Decimal:
    found = Decimal(0)
    for line in text.splitlines():
        if re.search(r"desconto", line, re.I):
            for value in MONEY_OCR.findall(line):
                found += abs(_money(value) or Decimal(0))
    return found


def _payment(text: str) -> str | None:
    """Forma de pagamento: só depois do total (antes dele são produtos) e só se for uma só."""
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if TOTAL_WORDS.search(line) and not re.search(r"c[oó]digo|unit|itens", line, re.I)
        ),
        None,
    )
    if start is None:
        return None
    found = {
        method
        for line in lines[start:]
        for method, pattern in PAYMENTS
        if re.search(pattern, line, re.I)
    }
    return found.pop() if len(found) == 1 else None


def _description(text: str) -> str | None:
    for line in text.splitlines()[:8]:
        clean = re.sub(r"[^\wÀ-ú&.\- ]", " ", line).strip()
        clean = re.sub(r"\s+", " ", clean)
        letters = sum(c.isalpha() for c in clean)
        if letters >= 4 and not SKIP_LINE.search(clean) and not MONEY.search(clean):
            return clean[:60].title()
    return None


def _item_name(line: str) -> str:
    """Nome do produto: sem código/número do item no começo, sem quantidade e valores no fim."""
    money = MONEY.search(line)
    end = money.start() if money else len(line)
    # A quantidade é a última antes do preço: "ARROZ 5KG 1 UN X 27,90" corta em "1 UN".
    quantities = [m for m in QUANTITY.finditer(line) if m.start() < end]
    if quantities:
        end = quantities[-1].start()
    # _clean_name tira o número do item e o código de barras ("001 7891234567890 ARROZ").
    return _clean_name(line[:end])


def _items(text: str) -> list[Item]:
    """Produtos do cupom: linhas com nome e valor antes do total. Só vale com dois ou mais."""
    found: list[Item] = []
    for line in text.splitlines():
        values = MONEY.findall(line)
        if TOTAL_WORDS.search(line):
            # O total com valor encerra a lista; sem valor é o cabeçalho ("VL UNIT VL TOTAL").
            if values:
                break
            continue
        # SKIP_LINE não serve aqui: "tel" cortaria pastel; "cupom", o desconto do cupom.
        if (
            not values
            or NOT_ITEM.search(line)
            or re.search(r"cnpj|cpf|chave|protocolo", line, re.I)
        ):
            continue
        name, amount = _item_name(line), _money(values[-1])
        if amount and amount > 0 and sum(c.isalpha() for c in name) >= 3:
            found.append(Item(name, amount))
    return found[:MAX_ITEMS] if len(found) >= 2 else []


def _checked_items(text: str, total: Decimal | None) -> list[Item]:
    """v1.9.0.1: a lista só vale se a soma bater com o total (com ou sem o desconto).

    Uma vírgula perdida na foto ("1990" em vez de "19,90") faria sugerir valores errados.
    """
    items = _items(text)
    if not items or total is None:
        return []
    added = sum((i.amount for i in items), Decimal(0))
    cents = Decimal("0.02")
    if abs(added - total) <= cents or abs(added - total - _discount(text)) <= cents:
        return items
    return []


def parse(text: str, today: date | None = None) -> Reading:
    """Interpreta o texto lido da foto (separado da leitura para poder testar)."""
    today = today or date.today()
    boleto = _find_boleto(text, today)
    if boleto:
        return boleto
    amount, when, description = _amount(text), _date(text, today), _description(text)
    kind = "cupom" if amount or when else "desconhecido"
    return Reading(
        kind, amount, when, description, _checked_items(text, amount), payment_method=_payment(text)
    )


# ---------------------------------------------------------------- leitura da imagem


def available() -> bool:
    return importlib.util.find_spec("leitor_comprovantes") is not None


def _leitor() -> LeitorComprovantes:
    global _LEITOR
    with _LEITOR_LOCK:
        if _LEITOR is None:
            from leitor_comprovantes import LeitorComprovantes

            _LEITOR = LeitorComprovantes()
        return _LEITOR


def extract(raw: bytes) -> ResultadoComprovante:
    """Lê a foto com o leitor de cupons (já validada por `files.prepare`)."""
    if not available():
        raise AppError(503, "ocr_unavailable", "A leitura de fotos não está disponível agora.")
    if not _LOCK.acquire(timeout=60):
        raise AppError(
            503, "ocr_busy", "Muitas leituras ao mesmo tempo. Tente de novo em instantes."
        )
    try:
        return _leitor().ler(raw, tipo="imagem")
    except Exception as exc:  # erro interno do OpenCV/ONNX numa foto estranha: nunca um 500
        # No log, para uma instalação quebrada (cv2/ONNX) não passar por "foto ruim".
        logger.exception("Leitor de cupons falhou")
        raise AppError(
            422, "ocr_failed", "Não foi possível ler a foto. Tente outra mais nítida."
        ) from exc
    finally:
        _LOCK.release()


def _clean_name(text: str) -> str:
    """Nome do produto ou da loja: sem número/código no começo, sem símbolos, até 60 letras."""
    words = text.split()
    while words and re.fullmatch(r"[\d.\-]+", words[0]):
        words.pop(0)
    clean = re.sub(r"[^\wÀ-ú&.\- ]", " ", " ".join(words))
    return re.sub(r"\s+", " ", clean).strip(" .-")[:60].title()


def from_result(result: ResultadoComprovante, today: date | None = None) -> Reading:
    """Converte o resultado do leitor no `Reading` de sempre.

    O que falta ao leitor vem das regras de texto (`parse`) sobre o mesmo texto lido. O total
    do leitor só ganha do `parse` quando ele mesmo confere que os produtos fecham com esse total
    (mesma ideia da v1.9.0.1: melhor não sugerir do que sugerir errado).
    """
    today = today or date.today()
    text = result.texto_extraido
    base = parse(text, today)
    if base.kind == "boleto":
        return base

    # Sem a conferência, o "valor pago" (com troco) ganharia do "valor a pagar" do parse().
    leitor_fechou = result.validacao.aprovado and result.valor_total is not None
    amount = result.valor_total if leitor_fechou else (base.amount or result.valor_total)
    when = base.date or _date(result.data_hora or "", today)
    store = _clean_name(result.estabelecimento or "")
    description = store if sum(c.isalpha() for c in store) >= 3 else base.description

    # Os produtos do parse() foram conferidos contra o total dele: só valem com esse total.
    items = base.items if amount == base.amount else []
    if leitor_fechou:
        named = [(_clean_name(item.descricao), item.valor_total) for item in result.itens]
        found = [
            Item(name, value)
            for name, value in named
            if value > 0 and sum(c.isalpha() for c in name) >= 3
        ]
        if len(found) >= 2:
            items = found[:MAX_ITEMS]

    kind = "cupom" if amount or when else "desconhecido"
    return Reading(kind, amount, when, description, items, payment_method=base.payment_method)


def read(raw: bytes) -> Reading:
    # Mesma validação dos comprovantes (tipo, tamanho, pixels). A imagem devolvida já vem em pé
    # e reduzida: o leitor não abre uma foto de 40 MP em tamanho cheio.
    image, *_ = files.prepare(raw, "receipt")
    return from_result(extract(image))
