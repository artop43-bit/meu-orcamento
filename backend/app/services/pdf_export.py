"""PDF da exportação (v1.7.6.1): o recorte escolhido em Exportar, o relatório do mês e o resumo
anual, como arquivo PDF de verdade.

Gerado aqui no servidor com o fpdf2 (biblioteca livre, sem serviço externo) e a fonte Inter,
a mesma do site, embutida no arquivo para os acentos e o "R$" saírem certos em qualquer leitor.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core.config import get_settings
from app.services.insights import MONTH_NAMES

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
ZERO = Decimal("0")

# Cores do tema padrão (verde) em tons de impressão.
INK = (24, 32, 30)
MUTED = (96, 108, 104)
LINE = (214, 222, 219)
SOFT = (238, 245, 242)
ACCENT = (31, 111, 92)
GOOD = (24, 128, 84)
BAD = (196, 52, 52)


def brl(value: Decimal | float, signed: bool = False) -> str:
    amount = Decimal(str(value))
    text = f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sign = "-" if amount < 0 else ("+" if signed and amount > 0 else "")
    return f"{sign}R$ {text}"


def month_name(month: date) -> str:
    return f"{MONTH_NAMES[month.month - 1]} de {month.year}"


def period_label(start: date, end: date) -> str:
    if start == end:
        return month_name(start).capitalize()
    if start.month == 1 and end.month == 12 and start.year == end.year:
        return f"Ano de {start.year}"
    return f"{month_name(start).capitalize()} a {month_name(end)}"


def _pct(part: Decimal, whole: Decimal) -> str:
    if not whole:
        return "—"
    return f"{part / whole * 100:.1f}".replace(".", ",") + "%"


class _Doc(FPDF):
    def __init__(self, title: str, subtitle: str, owner: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title_text = title
        self.subtitle_text = subtitle
        self.owner = owner
        zone = ZoneInfo(get_settings().timezone)
        self.generated = datetime.now(zone).strftime("%d/%m/%Y às %H:%M")
        self.add_font("Inter", "", str(FONTS / "Inter-Regular.ttf"))
        self.add_font("Inter", "B", str(FONTS / "Inter-Bold.ttf"))
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, 18)
        self.set_title(f"{title} · {subtitle}")
        self.set_author("Meu Orçamento")
        self.set_creator("Meu Orçamento")
        self.alias_nb_pages()

    # -------------------------------------------------- cabeçalho e rodapé

    def header(self) -> None:
        self.set_font("Inter", "B", 9)
        self.set_text_color(*ACCENT)
        self.cell(0, 5, "Meu Orçamento", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if self.page_no() == 1:
            self.set_text_color(*INK)
            self.set_font("Inter", "B", 18)
            self.cell(0, 9, self.title_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Inter", "", 10)
            self.set_text_color(*MUTED)
            self.cell(0, 5, self.subtitle_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        else:
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.cell(
                0,
                4,
                f"{self.title_text} · {self.subtitle_text}",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            self.ln(2)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Inter", "", 7.5)
        self.set_text_color(*MUTED)
        left = f"Gerado em {self.generated}" + (f" · {self.owner}" if self.owner else "")
        self.cell(0, 4, left, align="L")
        self.set_x(self.l_margin)
        self.cell(0, 4, f"Página {self.page_no()} de {{nb}}", align="R")

    # -------------------------------------------------- blocos

    @property
    def width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def section(self, title: str, note: str | None = None) -> None:
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(3)
        self.set_font("Inter", "B", 12)
        self.set_text_color(*INK)
        self.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if note:
            self.set_font("Inter", "", 8.5)
            self.set_text_color(*MUTED)
            self.multi_cell(0, 4.2, note, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def filters(self, lines: list[tuple[str, str]]) -> None:
        """Quadro com o recorte aplicado (período, conteúdo, contas, categorias)."""
        self.set_font("Inter", "", 8.5)
        value_w = self.width - 40
        heights = [
            5 * len(self.multi_cell(value_w, 5, value, dry_run=True, output="LINES"))
            for _, value in lines
        ]
        top = self.get_y()
        self.set_fill_color(*SOFT)
        self.rect(self.l_margin, top, self.width, sum(heights) + 5, style="F")
        y = top + 2.5
        for (label, value), height in zip(lines, heights, strict=True):
            self.set_xy(self.l_margin + 3, y)
            self.set_font("Inter", "B", 8.5)
            self.set_text_color(*MUTED)
            self.cell(34, 5, label)
            self.set_font("Inter", "", 8.5)
            self.set_text_color(*INK)
            self.multi_cell(value_w, 5, value)
            y += height
        self.set_y(top + sum(heights) + 9)

    def stats(self, items: list[tuple[str, str, tuple[int, int, int] | None]]) -> None:
        gap = 3
        size = (self.width - gap * (len(items) - 1)) / len(items)
        top = self.get_y()
        self.set_draw_color(*LINE)
        for index, (label, value, color) in enumerate(items):
            x = self.l_margin + index * (size + gap)
            self.rect(x, top, size, 17, style="D", round_corners=True, corner_radius=2)
            self.set_xy(x + 3, top + 2.5)
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.cell(size - 6, 4, label)
            self.set_xy(x + 3, top + 7.5)
            self.set_font("Inter", "B", 12.5 if len(value) < 15 else 10.5)
            self.set_text_color(*(color or INK))
            self.cell(size - 6, 7, value)
        self.set_y(top + 21)

    def table(
        self,
        columns: list[tuple[str, float, str]],
        rows: list[list[str]],
        colors: list[list[tuple[int, int, int] | None]] | None = None,
        total: list[str] | None = None,
    ) -> None:
        """`columns`: (título, fração da largura, alinhamento L/R/C)."""
        widths = [self.width * share for _, share, _ in columns]
        line = 5.6

        def head() -> None:
            self.set_font("Inter", "B", 8)
            self.set_text_color(*MUTED)
            self.set_fill_color(*SOFT)
            for (title, _, align), w in zip(columns, widths, strict=True):
                self.cell(w, 6.5, title, align=align, fill=True)
            self.ln(6.5)

        head()
        self.set_draw_color(*LINE)
        for index, row in enumerate(rows):
            if self.get_y() + line > self.h - self.b_margin:
                self.add_page()
                head()
            self.set_font("Inter", "", 8.5)
            for col, ((_, _, align), w) in enumerate(zip(columns, widths, strict=True)):
                color = colors[index][col] if colors else None
                self.set_text_color(*(color or INK))
                text = row[col]
                while text and self.get_string_width(text) > w - 1.5:
                    text = text[:-2] + "…"
                self.cell(w, line, text, align=align)
            self.ln(line)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        if total:
            self.set_font("Inter", "B", 8.5)
            self.set_text_color(*INK)
            for (_, _, align), w, text in zip(columns, widths, total, strict=True):
                self.cell(w, 6.5, text, align=align)
            self.ln(6.5)

    def empty(self, text: str) -> None:
        self.set_font("Inter", "", 9.5)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---------------------------------------------------------------- recorte


def _totals(rows: list[dict[str, Any]]) -> tuple[Decimal, Decimal]:
    income = sum((r["amount"] for r in rows if r["type"] == "Receita"), ZERO)
    expenses = sum((-r["amount"] for r in rows if r["type"] == "Despesa"), ZERO)
    return income, expenses


def _months(rows: list[dict[str, Any]]) -> list[tuple[date, Decimal, Decimal]]:
    found: dict[date, list[Decimal]] = {}
    for r in rows:
        point = found.setdefault(r["month"], [ZERO, ZERO])
        if r["type"] == "Receita":
            point[0] += r["amount"]
        else:
            point[1] += -r["amount"]
    return [(month, values[0], values[1]) for month, values in sorted(found.items())]


def _summary_block(doc: _Doc, rows: list[dict[str, Any]], kind: str) -> None:
    income, expenses = _totals(rows)
    items: list[tuple[str, str, tuple[int, int, int] | None]] = [
        ("Lançamentos", str(len(rows)), None)
    ]
    if kind in ("all", "income"):
        items.append(("Receitas", brl(income), GOOD if income else None))
    if kind in ("all", "expense"):
        items.append(("Despesas", brl(expenses), BAD if expenses else None))
    if kind == "all":
        balance = income - expenses
        items.append(("Saldo", brl(balance), GOOD if balance >= 0 else BAD))
        items.append(("Comprometido", _pct(expenses, income), None))
    doc.stats(items)


def _categories_block(doc: _Doc, by_category: list[dict[str, Any]]) -> None:
    if not by_category:
        return
    doc.section("Despesas por categoria")
    total = sum((c["total"] for c in by_category), ZERO)
    doc.table(
        [("Categoria", 0.56, "L"), ("Total", 0.24, "R"), ("% das despesas", 0.20, "R")],
        [
            [c["name"], brl(c["total"]), f"{c['share'] * 100:.1f}".replace(".", ",") + "%"]
            for c in by_category
        ],
        total=["Total", brl(total), "100%"],
    )


def _months_block(doc: _Doc, rows: list[dict[str, Any]], kind: str) -> None:
    months = _months(rows)
    if len(months) < 2:
        return
    doc.section("Mês a mês")
    columns: list[tuple[str, float, str]] = [("Mês", 0.34, "L")]
    if kind in ("all", "income"):
        columns.append(("Receitas", 0.22, "R"))
    if kind in ("all", "expense"):
        columns.append(("Despesas", 0.22, "R"))
    if kind == "all":
        columns.append(("Saldo", 0.22, "R"))
    share = 0.66 / (len(columns) - 1)
    columns = [columns[0], *[(t, share, a) for t, _, a in columns[1:]]]
    body, colors = [], []
    for month, income, expenses in months:
        line: list[str] = [month_name(month).capitalize()]
        tint: list[tuple[int, int, int] | None] = [None]
        if kind in ("all", "income"):
            line.append(brl(income))
            tint.append(None)
        if kind in ("all", "expense"):
            line.append(brl(expenses))
            tint.append(None)
        if kind == "all":
            line.append(brl(income - expenses))
            tint.append(GOOD if income >= expenses else BAD)
        body.append(line)
        colors.append(tint)
    doc.table(columns, body, colors)


def _short_month(month: date) -> str:
    """Lançamento sem dia: "jan/2030"."""
    return f"{MONTH_NAMES[month.month - 1][:3]}/{month.year}"


def _list_block(
    doc: _Doc, rows: list[dict[str, Any]], total_label: str = "Total do recorte"
) -> None:
    doc.section(
        "Lançamentos",
        "Despesas aparecem com sinal de menos. Data é o vencimento da despesa (ou o dia da receita).",
    )
    body, colors = [], []
    for r in rows:
        when = r["date"].strftime("%d/%m/%Y") if r["date"] else _short_month(r["month"])
        description = r["description"] + (f" ({r['installment']})" if r["installment"] else "")
        body.append(
            [
                when,
                description,
                r["category"] or ("Receita" if r["type"] == "Receita" else "Sem categoria"),
                r["place"] or "—",
                r["payment"] or "—",
                brl(r["amount"]),
            ]
        )
        colors.append([None, None, MUTED, MUTED, MUTED, GOOD if r["amount"] > 0 else INK])
    income, expenses = _totals(rows)
    doc.table(
        [
            ("Data", 0.12, "L"),
            ("Descrição", 0.33, "L"),
            ("Categoria", 0.16, "L"),
            ("Conta ou cartão", 0.15, "L"),
            ("Pagamento", 0.10, "L"),
            ("Valor", 0.14, "R"),
        ],
        body,
        colors,
        total=["", total_label, "", "", "", brl(income - expenses)],
    )


def transactions_pdf(
    rows: list[dict[str, Any]],
    by_category: list[dict[str, Any]],
    *,
    start: date,
    end: date,
    kind: str,
    filters: list[tuple[str, str]],
    owner: str,
    title: str = "Lançamentos",
) -> bytes:
    """PDF do recorte: resumo, categorias, mês a mês e a lista de lançamentos."""
    doc = _Doc(title, period_label(start, end), owner)
    doc.add_page()
    doc.filters(filters)
    _summary_block(doc, rows, kind)
    if not rows:
        doc.empty("Nenhum lançamento neste recorte. Mude o período ou os filtros e baixe de novo.")
        return bytes(doc.output())
    if kind != "income":
        _categories_block(doc, by_category)
    _months_block(doc, rows, kind)
    _list_block(doc, rows)
    return bytes(doc.output())


# ---------------------------------------------------------------- resumo anual


def annual_pdf(data: dict[str, Any], rows: list[dict[str, Any]], owner: str) -> bytes:
    """Resumo anual: totais, mês a mês, categorias e a parte para o Imposto de Renda."""
    year = data["year"]
    doc = _Doc("Resumo anual", str(year), owner)
    doc.add_page()
    balance = data["balance"]
    doc.stats(
        [
            ("Receitas", brl(data["income"]), GOOD if data["income"] else None),
            ("Despesas", brl(data["expenses"]), BAD if data["expenses"] else None),
            ("Saldo do ano", brl(balance), GOOD if balance >= 0 else BAD),
            (
                "Taxa de poupança",
                f"{data['savings_rate']:.1f}%".replace(".", ",")
                if data["savings_rate"] is not None
                else "—",
                None,
            ),
        ]
    )
    months = [m for m in data["months"] if m["has_data"]]
    if months:
        doc.section("Mês a mês")
        doc.table(
            [
                ("Mês", 0.28, "L"),
                ("Receitas", 0.18, "R"),
                ("Despesas", 0.18, "R"),
                ("Saldo", 0.18, "R"),
                ("Comprometido", 0.18, "R"),
            ],
            [
                [
                    month_name(m["month"]).capitalize(),
                    brl(m["income"]),
                    brl(m["expenses"]),
                    brl(m["balance"]),
                    f"{m['committed_pct']:.1f}%".replace(".", ",")
                    if m["committed_pct"] is not None
                    else "—",
                ]
                for m in months
            ],
            [[None, None, None, GOOD if m["balance"] >= 0 else BAD, None] for m in months],
            total=["Ano", brl(data["income"]), brl(data["expenses"]), brl(balance), ""],
        )
    _categories_block(doc, data["by_category"])

    tax = data["tax"]
    doc.section(
        "Para o Imposto de Renda",
        "Ajuda a preencher a declaração; não é documento fiscal. Confira os comprovantes originais.",
    )
    if tax["incomes"]:
        doc.table(
            [("Rendimentos", 0.76, "L"), ("Total", 0.24, "R")],
            [[i["label"], brl(i["total"])] for i in tax["incomes"]],
        )
        doc.ln(3)
    if tax["deductions"]:
        doc.table(
            [("Pagamentos dedutíveis", 0.76, "L"), ("Total", 0.24, "R")],
            [[d["label"], brl(d["total"])] for d in tax["deductions"]],
            total=["Total dedutível", brl(tax["deductions_total"])],
        )
        doc.ln(3)
    if tax["assets"]:
        doc.table(
            [(f"Bens e direitos em 31/12/{year}", 0.76, "L"), ("Valor", 0.24, "R")],
            [[a["description"], brl(a["value"])] for a in tax["assets"]],
        )
        doc.ln(3)
    if tax["debts"]:
        doc.table(
            [(f"Dívidas e ônus em 31/12/{year}", 0.76, "L"), ("Saldo", 0.24, "R")],
            [[d["description"], brl(d["value"])] for d in tax["debts"]],
        )
    if not any(tax[k] for k in ("incomes", "deductions", "assets", "debts")):
        doc.empty("Nada a mostrar para o Imposto de Renda neste ano.")
    if rows:
        _list_block(doc, rows, "Total do ano")
    return bytes(doc.output())


# ---------------------------------------------------------------- termo de empréstimo (v1.8)

FREQUENCY_TEXT = {"day": "diárias", "week": "semanais", "biweek": "quinzenais", "month": "mensais"}
MODE_TEXT = {
    "none": "sem juros",
    "total": "com juros de {rate} sobre o valor emprestado",
    "simple": "com juros simples de {rate} ao mês",
    "price": "com juros compostos de {rate} ao mês (parcelas iguais, Tabela Price)",
    "sac": "com juros compostos de {rate} ao mês (devolução constante, SAC)",
}


def _rate(value: Decimal | float) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text}%"


def loan_term_pdf(loan: dict[str, Any], owner: str) -> bytes:
    """Termo simples de empréstimo entre pessoas, com o cronograma para as duas assinarem."""
    lender, borrower = (owner, loan["person"])
    if loan["direction"] == "i_owe":
        lender, borrower = borrower, owner
    doc = _Doc("Termo de empréstimo", f"{lender} para {borrower}", owner)
    doc.add_page()
    count = loan["count"]
    plural = "parcela" if count == 1 else f"{count} parcelas {FREQUENCY_TEXT[loan['frequency']]}"
    form = MODE_TEXT[loan["mode"]].format(rate=_rate(loan["rate"]))
    first = loan["installments"][0]["due_date"]
    last = loan["installments"][-1]["due_date"]
    doc.set_font("Inter", "", 10)
    doc.set_text_color(*INK)
    text = (
        f"{lender} empresta a {borrower} a quantia de {brl(loan['principal'])}, {form}. "
        f"{borrower} se compromete a devolver {brl(loan['total'])} em {plural}, "
        f"de {first:%d/%m/%Y} a {last:%d/%m/%Y}, conforme o cronograma abaixo."
    )
    if loan.get("description"):
        text += f" Motivo: {loan['description']}."
    if loan.get("late_fee") or loan.get("late_interest"):
        parts = []
        if loan.get("late_fee"):
            parts.append(f"multa de {_rate(loan['late_fee'])}")
        if loan.get("late_interest"):
            parts.append(f"juros de {_rate(loan['late_interest'])} ao mês, proporcionais aos dias")
        text += f" Em caso de atraso, incidem {' e '.join(parts)} sobre a parcela em aberto."
    text += (
        " O pagamento antecipado é permitido, com desconto dos juros das parcelas que ainda "
        "não venceram."
    )
    doc.multi_cell(0, 5.4, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(3)
    doc.stats(
        [
            ("Valor emprestado", brl(loan["principal"]), None),
            ("Total a devolver", brl(loan["total"]), None),
            ("Juros", brl(loan["profit"]), None),
            ("Equivale a", f"{_rate(loan['monthly_equivalent'])} ao mês", None),
        ]
    )
    doc.section("Cronograma")
    rows = [
        [
            str(i["number"]),
            f"{i['due_date']:%d/%m/%Y}",
            brl(i["amount"]),
            brl(i["interest"]),
            brl(i["principal"]),
            "Pago" if i["status"] == "paid" else "",
        ]
        for i in loan["installments"]
    ]
    doc.table(
        [
            ("Nº", 0.08, "L"),
            ("Vencimento", 0.2, "L"),
            ("Valor", 0.2, "R"),
            ("Juros", 0.18, "R"),
            ("Devolução", 0.18, "R"),
            ("Situação", 0.16, "R"),
        ],
        rows,
        total=["", "Total", brl(loan["total"]), brl(loan["profit"]), brl(loan["principal"]), ""],
    )
    if doc.get_y() > doc.h - 60:
        doc.add_page()
    doc.ln(16)
    half = (doc.width - 10) / 2
    y = doc.get_y()
    doc.set_draw_color(*INK)
    doc.line(doc.l_margin, y, doc.l_margin + half, y)
    doc.line(doc.l_margin + half + 10, y, doc.w - doc.r_margin, y)
    doc.set_y(y + 1.5)
    doc.set_font("Inter", "", 9)
    doc.cell(half, 5, f"{lender} (quem empresta)")
    doc.set_x(doc.l_margin + half + 10)
    doc.cell(half, 5, f"{borrower} (quem recebe)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(8)
    doc.set_font("Inter", "", 8)
    doc.set_text_color(*MUTED)
    doc.multi_cell(
        0,
        4,
        "Local e data: ______________________________________________\n\n"
        "Modelo simples para registrar um acordo entre pessoas. Não substitui orientação "
        "jurídica. Entre particulares, a Lei da Usura (Decreto 22.626/33) limita os juros a "
        "1% ao mês.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    return bytes(doc.output())
