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
from app.core.money import brl as _core_brl
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
    return _core_brl(value, signed=signed)


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
    "none": "sem cobrança de juros",
    "total": "com juros de {rate} sobre o valor emprestado",
    "simple": "com juros simples de {rate} ao mês",
    "price": "com juros compostos de {rate} ao mês, em parcelas iguais (Tabela Price)",
    "sac": "com juros compostos de {rate} ao mês, com devolução constante do valor (SAC)",
}
MONTHS_FULL = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def _rate(value: Decimal | float) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text}%"


def _cpf(value: str | None) -> str | None:
    digits = "".join(c for c in (value or "") if c.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return (value or "").strip() or None


class _Term(_Doc):
    """Documento para entregar: sem a marca do app, sem data de geração; só o número da página."""

    def header(self) -> None:
        if self.page_no() == 1:
            self.set_text_color(*INK)
            self.set_font("Inter", "B", 15)
            self.cell(0, 9, self.title_text.upper(), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(3)
        else:
            self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Inter", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, f"Página {self.page_no()} de {{nb}}", align="C")


def _party(role: str, name: str, cpf: str | None, address: str | None) -> str:
    if name.startswith("_"):
        return f"{role}: {name}"  # em branco, para preencher à mão
    text = f"{role}: {name}"
    if cpf:
        text += f", CPF {cpf}"
    if address:
        text += f", residente em {address}"
    return text + "."


def loan_term_pdf(loan: dict[str, Any], parties: dict[str, Any], today: date) -> bytes:
    """Instrumento particular de empréstimo, pronto para as partes assinarem. Os dados das partes
    são opcionais: só entra no documento o que foi informado."""
    me = parties.get("my_name") or "_" * 40
    other = parties.get("person_name") or loan["person"]
    my_cpf, other_cpf = _cpf(parties.get("my_cpf")), _cpf(parties.get("person_cpf"))
    my_addr = (parties.get("my_address") or "").strip() or None
    other_addr = (parties.get("person_address") or "").strip() or None
    lender = (me, my_cpf, my_addr)
    borrower = (other, other_cpf, other_addr)
    if loan["direction"] == "i_owe":
        lender, borrower = borrower, lender
    city = (parties.get("city") or "").strip() or None
    pix = (parties.get("pix_key") or "").strip() or None

    doc = _Term("Instrumento particular de empréstimo", "", "")
    doc.add_page()
    doc.set_text_color(*INK)

    def para(text: str, bold: bool = False, gap: float = 2.5) -> None:
        doc.set_font("Inter", "B" if bold else "", 10)
        doc.multi_cell(0, 5.4, text, align="J", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        doc.ln(gap)

    para(_party("CREDOR (quem empresta)", *lender), gap=1)
    para(_party("DEVEDOR (quem recebe o empréstimo)", *borrower))
    para(
        "As partes acima ajustam o presente empréstimo de dinheiro, que se rege pelas cláusulas "
        "a seguir."
    )
    count = loan["count"]
    items = loan["installments"]
    first, last = items[0]["due_date"], items[-1]["due_date"]
    equal = len({i["amount"] for i in items[:-1]}) <= 1
    each = (
        f"de {brl(items[0]['amount'])}"
        + (
            f" (a última de {brl(items[-1]['amount'])})"
            if items[-1]["amount"] != items[0]["amount"]
            else ""
        )
        if equal
        else "nos valores do cronograma abaixo"
    )
    clauses = [
        f"O CREDOR empresta ao DEVEDOR a quantia de {brl(loan['principal'])}"
        + (f", destinada a: {loan['description']}" if loan.get("description") else "")
        + ".",
        f"O empréstimo é feito {MODE_TEXT[loan['mode']].format(rate=_rate(loan['rate']))}. "
        f"O DEVEDOR devolverá ao CREDOR o total de {brl(loan['total'])}, sendo "
        f"{brl(loan['principal'])} do valor emprestado e {brl(loan['profit'])} de juros.",
        (
            f"O pagamento será feito em {count} parcela{'s' if count > 1 else ''} "
            f"{FREQUENCY_TEXT[loan['frequency']] if count > 1 else ''} {each}, "
            f"de {first:%d/%m/%Y} a {last:%d/%m/%Y}, conforme o cronograma abaixo."
        ).replace("  ", " "),
        "Os pagamentos serão feitos por Pix"
        + (f" para a chave {pix}" if pix else "")
        + ", ou de outra forma combinada entre as partes, valendo o comprovante como recibo.",
    ]
    if loan.get("late_fee") or loan.get("late_interest"):
        parts = []
        if loan.get("late_fee"):
            parts.append(f"multa de {_rate(loan['late_fee'])}")
        if loan.get("late_interest"):
            parts.append(
                f"juros de {_rate(loan['late_interest'])} ao mês, proporcionais aos dias de atraso"
            )
        clauses.append(f"Em caso de atraso, incidem sobre a parcela em aberto {' e '.join(parts)}.")
    clauses.append(
        "O DEVEDOR pode antecipar o pagamento de parcelas ou quitar o saldo a qualquer momento, "
        "com desconto dos juros das parcelas que ainda não venceram."
    )
    if city:
        clauses.append(
            f"Fica eleito o foro da comarca de {city} para resolver questões deste instrumento."
        )
    for index, text in enumerate(clauses, start=1):
        # Rótulo em negrito e o texto normal, na mesma linha.
        doc.set_font("Inter", "B", 10)
        doc.write(5.2, f"Cláusula {index}ª. ")
        doc.set_font("Inter", "", 10)
        doc.write(5.2, text)
        doc.ln(5.2)
        doc.ln(1.8)
    doc.section("Cronograma de pagamento")
    rows = [
        [
            str(i["number"]),
            f"{i['due_date']:%d/%m/%Y}",
            brl(i["amount"]),
            brl(i["interest"]),
            brl(i["principal"]),
        ]
        for i in items
    ]
    doc.table(
        [
            ("Parcela", 0.14, "L"),
            ("Vencimento", 0.24, "L"),
            ("Valor", 0.22, "R"),
            ("Juros", 0.2, "R"),
            ("Devolução", 0.2, "R"),
        ],
        rows,
        total=["", "Total", brl(loan["total"]), brl(loan["profit"]), brl(loan["principal"])],
    )
    doc.ln(4)
    # Fechamento, assinaturas e testemunhas ficam juntos na mesma página.
    if doc.get_y() > doc.h - doc.b_margin - 60:
        doc.add_page()
    para("E, por estarem de acordo, as partes assinam este instrumento, com duas testemunhas.")
    when = f"{today.day} de {MONTHS_FULL[today.month - 1]} de {today.year}"
    doc.set_font("Inter", "", 10)
    place = f"{city}, {when}." if city else f"______________________________, {when}."
    doc.cell(0, 6, place, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def signatures(pairs: list[tuple[str, str | None, str]]) -> None:
        half = (doc.width - 12) / 2
        doc.ln(10)
        y = doc.get_y()
        doc.set_draw_color(*INK)
        for col, (name, cpf, role) in enumerate(pairs):
            x = doc.l_margin + col * (half + 12)
            doc.line(x, y, x + half, y)
            doc.set_xy(x, y + 1.5)
            doc.set_font("Inter", "B", 9)
            doc.cell(half, 4.5, "" if name.startswith("_") else name)
            doc.set_xy(x, y + 6)
            doc.set_font("Inter", "", 8.5)
            doc.set_text_color(*MUTED)
            doc.cell(half, 4.5, f"{role}" + (f" · CPF {cpf}" if cpf else ""))
            doc.set_text_color(*INK)
        doc.set_y(y + 11)

    signatures([(lender[0], lender[1], "Credor"), (borrower[0], borrower[1], "Devedor")])
    signatures(
        [
            ("Testemunha 1", None, "Nome e CPF: ______________________"),
            ("Testemunha 2", None, "Nome e CPF: ______________________"),
        ]
    )
    return bytes(doc.output())
