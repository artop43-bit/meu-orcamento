"""Gerador 100% local de PDFs A4 para propostas, ordens de serviço, contratos e recibos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core.config import get_settings
from app.core.money import brl

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

INK = (20, 27, 25)
MUTED = (95, 108, 102)
LINE = (214, 222, 218)
SOFT = (242, 246, 244)
ACCENT = (16, 134, 96)

DOC_TYPE_TITLES = {
    "proposal": "PROPOSTA COMERCIAL",
    "service_order": "ORDEM DE SERVIÇO",
    "contract": "CONTRATO DE PRESTAÇÃO",
    "receipt": "RECIBO DE PAGAMENTO",
}

DOC_STATUS_LABELS = {
    "draft": "Rascunho",
    "sent": "Enviada",
    "approved": "Aprovada",
    "rejected": "Recusada",
    "cancelled": "Cancelada",
}


def _fmt_date(d: date | datetime | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, datetime):
        tz = ZoneInfo(get_settings().timezone)
        return d.astimezone(tz).strftime("%d/%m/%Y")
    return d.strftime("%d/%m/%Y")


def _fmt_qty(val: Any) -> str:
    dec = Decimal(str(val or 0))
    if dec == dec.to_integral_value():
        return str(int(dec))
    text = f"{dec:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


class _CommercialPdf(FPDF):
    def __init__(self, doc_label: str, doc_code: str, emitter: str, generated_at: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Inter", "", str(FONTS_DIR / "Inter-Regular.ttf"))
        self.add_font("Inter", "B", str(FONTS_DIR / "Inter-Bold.ttf"))
        self.doc_label = doc_label
        self.doc_code = doc_code
        self.emitter = emitter
        self.generated_at = generated_at
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    @property
    def content_w(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def header(self) -> None:
        if self.page_no() == 1:
            self.set_font("Inter", "B", 9)
            self.set_text_color(*ACCENT)
            self.cell(self.content_w * 0.65, 5, self.doc_label)
            self.set_text_color(*MUTED)
            self.set_font("Inter", "", 8.5)
            self.cell(
                0,
                5,
                self.doc_code,
                align="R",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            self.set_draw_color(*LINE)
            self.line(self.l_margin, self.get_y() + 1.5, self.w - self.r_margin, self.get_y() + 1.5)
            self.ln(5)
        else:
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.cell(
                0,
                4,
                f"{self.doc_label} · {self.doc_code}",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            self.ln(3)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Inter", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, f"Emitido em {self.generated_at} · {self.emitter}", align="L")
        self.set_x(self.l_margin)
        self.cell(0, 4, f"Página {self.page_no()} de {{nb}}", align="R")


def build_commercial_pdf(
    *,
    doc_type: str,
    number: int,
    title: str,
    status: str,
    emitter_name: str,
    emitter_email: str,
    customer_name: str,
    customer_doc: str | None,
    customer_contact: str | None,
    items: list[dict[str, Any]],
    discount: Decimal,
    total_amount: Decimal,
    valid_until: date | None,
    terms_text: str | None,
    created_at: datetime,
) -> bytes:
    """Gera o arquivo PDF A4 completo (sem vínculos bancários externos)."""
    doc_label = DOC_TYPE_TITLES.get(doc_type, "DOCUMENTO COMERCIAL")
    doc_code = f"#{number:04d} · {DOC_STATUS_LABELS.get(status, status)}"
    pdf = _CommercialPdf(
        doc_label=doc_label,
        doc_code=doc_code,
        emitter=emitter_name or emitter_email,
        generated_at=_fmt_date(created_at),
    )
    pdf.add_page()

    # Título principal
    pdf.set_font("Inter", "B", 16)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 7.5, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Inter", "", 8.5)
    pdf.set_text_color(*MUTED)
    meta_parts = [f"Emissão: {_fmt_date(created_at)}"]
    if valid_until:
        meta_parts.append(f"Validade: {_fmt_date(valid_until)}")
    pdf.cell(0, 5, "   ·   ".join(meta_parts), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # Quadro Emissor x Cliente
    col_w = (pdf.content_w - 6) / 2
    box_top = pdf.get_y()
    pdf.set_fill_color(*SOFT)
    pdf.rect(pdf.l_margin, box_top, col_w, 22, style="F")
    pdf.rect(pdf.l_margin + col_w + 6, box_top, col_w, 22, style="F")

    pdf.set_xy(pdf.l_margin + 3, box_top + 2.5)
    pdf.set_font("Inter", "B", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(col_w - 6, 4, "EMISSOR")
    pdf.set_xy(pdf.l_margin + 3, box_top + 7.5)
    pdf.set_font("Inter", "B", 9.5)
    pdf.set_text_color(*INK)
    pdf.cell(col_w - 6, 5, (emitter_name or emitter_email)[:55])
    pdf.set_xy(pdf.l_margin + 3, box_top + 13.5)
    pdf.set_font("Inter", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(col_w - 6, 4.5, emitter_email[:58])

    rx = pdf.l_margin + col_w + 9
    pdf.set_xy(rx, box_top + 2.5)
    pdf.set_font("Inter", "B", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(col_w - 6, 4, "CLIENTE")
    pdf.set_xy(rx, box_top + 7.5)
    pdf.set_font("Inter", "B", 9.5)
    pdf.set_text_color(*INK)
    pdf.cell(col_w - 6, 5, customer_name[:55])
    pdf.set_xy(rx, box_top + 13.5)
    pdf.set_font("Inter", "", 8.5)
    pdf.set_text_color(*MUTED)
    client_sub = " · ".join([p for p in (customer_doc, customer_contact) if p]) or "—"
    pdf.cell(col_w - 6, 4.5, client_sub[:58])

    pdf.set_y(box_top + 27)

    # Tabela de itens
    w_name = pdf.content_w * 0.50
    w_qty = pdf.content_w * 0.14
    w_unit = pdf.content_w * 0.18
    w_tot = pdf.content_w * 0.18

    def _draw_table_header() -> None:
        pdf.set_fill_color(*SOFT)
        pdf.set_draw_color(*LINE)
        pdf.set_font("Inter", "B", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(w_name, 7, "  Item / Descrição", border="TB", fill=True)
        pdf.cell(w_qty, 7, "Qtd", border="TB", align="R", fill=True)
        pdf.cell(w_unit, 7, "Unitário", border="TB", align="R", fill=True)
        pdf.cell(
            w_tot,
            7,
            "Subtotal  ",
            border="TB",
            align="R",
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    _draw_table_header()

    subtotal = Decimal("0.00")
    for idx, row in enumerate(items):
        if pdf.get_y() > pdf.h - 38:
            pdf.add_page()
            _draw_table_header()
        line_total = Decimal(str(row.get("total", 0)))
        unit_price = Decimal(str(row.get("unit_price", 0)))
        subtotal += line_total
        qty_str = f"{_fmt_qty(row.get('qty', 1))} {row.get('unit', 'un')}".strip()

        pdf.set_font("Inter", "", 9)
        pdf.set_text_color(*INK)
        pdf.set_draw_color(*LINE)
        if idx % 2 == 1:
            pdf.set_fill_color(249, 251, 250)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(w_name, 7, f"  {str(row.get('name', 'Item'))[:54]}", border="B", fill=True)
        pdf.cell(w_qty, 7, qty_str[:14], border="B", align="R", fill=True)
        pdf.cell(w_unit, 7, brl(unit_price), border="B", align="R", fill=True)
        pdf.cell(
            w_tot,
            7,
            f"{brl(line_total)}  ",
            border="B",
            align="R",
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.ln(3)

    # Totais alinhados à direita
    summary_w = 72
    sx = pdf.w - pdf.r_margin - summary_w
    pdf.set_x(sx)
    pdf.set_font("Inter", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(36, 6, "Subtotal")
    pdf.set_text_color(*INK)
    pdf.cell(36, 6, brl(subtotal), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if discount > Decimal("0"):
        pdf.set_x(sx)
        pdf.set_text_color(*MUTED)
        pdf.cell(36, 6, "Desconto")
        pdf.set_text_color(*INK)
        pdf.cell(36, 6, f"- {brl(discount)}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(sx)
    pdf.set_fill_color(*SOFT)
    pdf.set_font("Inter", "B", 10.5)
    pdf.set_text_color(*ACCENT)
    pdf.cell(36, 8, "  Total", border="TB", fill=True)
    pdf.cell(
        36,
        8,
        f"{brl(total_amount)}  ",
        border="TB",
        align="R",
        fill=True,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    if terms_text and terms_text.strip():
        pdf.ln(6)
        if pdf.get_y() > pdf.h - 46:
            pdf.add_page()
        pdf.set_font("Inter", "B", 9.5)
        pdf.set_text_color(*INK)
        pdf.cell(0, 6, "Condições, prazos e observações", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Inter", "", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 4.6, terms_text.strip(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Bloco simples de assinatura
    if pdf.get_y() > pdf.h - 34:
        pdf.add_page()
    pdf.ln(10)
    sig_w = (pdf.content_w - 16) / 2
    y_sig = pdf.get_y() + 8
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, y_sig, pdf.l_margin + sig_w, y_sig)
    pdf.line(pdf.l_margin + sig_w + 16, y_sig, pdf.w - pdf.r_margin, y_sig)
    pdf.set_xy(pdf.l_margin, y_sig + 1.5)
    pdf.set_font("Inter", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(sig_w, 4, (emitter_name or emitter_email)[:46], align="C")
    pdf.set_x(pdf.l_margin + sig_w + 16)
    pdf.cell(sig_w, 4, customer_name[:46], align="C")

    return bytes(pdf.output())
