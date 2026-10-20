"""Checagem de layout: nenhum texto cortado, vazando da caixa ou saindo da tela/janela (Playwright).

Percorre todas as telas e os formulários em três tamanhos (monitor, notebook e celular), tira um
print de cada um e procura: texto truncado, texto maior que a própria caixa, campo com valor
cortado, conteúdo fora da largura da tela, conteúdo fora da janela (dialog) e dica (ⓘ) cortada.

Roda no CI depois da persona (que deixa a conta com dados) e localmente:
    uv run --no-project --with playwright python e2e/layout.py
Variáveis: QA_BASE_URL, QA_CREDENTIALS, QA_OUT, QA_BROWSER (as mesmas da persona).
Sai com código 1 se encontrar qualquer problema; a lista fica em QA_OUT/layout.json.
"""

import json
import os
import pathlib
import re
import sys

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida")) / "layout"
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]

PAGES = [
    ("orcamento", "/orcamento"),
    ("calendario", "/calendario"),
    *[(f"insights-{s}", f"/analises?secao={s}") for s in (
        "resumo", "tendencias", "categorias", "saude", "patrimonio", "comparar", "projecao", "simulador", "monte",
    )],
    ("investimentos", "/investimentos"),
    ("cotacoes", "/investimentos?secao=cotacoes"),
    ("contas", "/contas"),
    ("cartoes", "/cartoes"),
    ("metas", "/metas"),
    ("historico", "/historico"),
    ("revisar", "/revisar"),
    ("busca", "/busca?q=mercado"),
    ("ajustes", "/ajustes"),
    ("recorrencias", "/ajustes/recorrencias"),
    ("categorias", "/ajustes/categorias"),
    ("dados", "/ajustes/dados"),
    ("dados-exportar", "/ajustes/dados?aba=exportar"),
    ("notas", "/ajustes/notas"),
    ("mensagens", "/mensagens"),
    ("dividas", "/dividas"),
    ("calculadoras", "/analises?secao=calculadoras"),
    ("admin-recados", "/admin?aba=recados"),
    ("seguranca", "/ajustes/seguranca"),
    ("preferencias", "/ajustes/preferencias"),
    ("atalhos", "/ajustes/atalhos"),
    ("ajuda", "/ajustes/ajuda"),
    ("admin", "/admin"),
    ("admin-emails", "/admin?aba=emails"),
    ("admin-solicitacoes", "/admin?aba=solicitacoes"),
    ("admin-solicitacoes-usuarios", "/admin?aba=solicitacoes&visao=usuarios"),
    ("admin-solicitacoes-status", "/admin?aba=solicitacoes&visao=status"),
    ("perfil", "/ajustes/perfil"),
    ("solicitacoes", "/ajustes/solicitacoes"),
]

VIEWPORTS = {
    "monitor": dict(viewport={"width": 1366, "height": 900}),
    "notebook": dict(viewport={"width": 1100, "height": 760}),
    "celular": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
    # v0.9: modo escuro no computador e no celular (o tema segue o sistema por padrão).
    "monitor-escuro": dict(viewport={"width": 1366, "height": 900}, color_scheme="dark"),
    "celular-escuro": dict(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2, color_scheme="dark"
    ),
}

# Roda na página: devolve os problemas encontrados no que está visível.
DETECT = r"""
(scope) => {
  const issues = [];
  const root = (scope && document.querySelector(scope)) || document.body;
  const vw = document.documentElement.clientWidth;
  const label = (el) => (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const path = (el) => {
    const parts = [];
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      let p = e.tagName.toLowerCase();
      if (typeof e.className === 'string' && e.className.trim()) p += '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.');
      parts.unshift(p);
    }
    return parts.join(' > ');
  };
  // Dentro de uma faixa com rolagem horizontal (abas, filtros, tabelas), sair da tela é intencional.
  const scrolls = (el) => {
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const o = getComputedStyle(e).overflowX;
      if (o === 'auto' || o === 'scroll') return true;
    }
    return false;
  };
  // Conteúdo "só para leitor de tela" (recortado de propósito) não conta.
  const visuallyHidden = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const st = getComputedStyle(e);
      if (st.position === 'absolute' && st.clip && st.clip !== 'auto') return true;
    }
    return false;
  };
  for (const el of root.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none') continue;
    if (el.closest('svg, .chart, [aria-hidden="true"], .sr-only, .visually-hidden') || visuallyHidden(el)) continue;
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const hidden = s.overflowX === 'hidden' || s.overflow === 'hidden' || s.textOverflow === 'ellipsis';
    if (hasText && hidden && el.scrollWidth > el.clientWidth + 1) {
      issues.push({ kind: 'cortado', text: label(el), where: path(el), w: el.clientWidth, need: el.scrollWidth });
    }
    if (hasText && s.overflowX === 'visible' && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2
        && !['SPAN', 'A', 'STRONG', 'EM', 'B', 'I', 'SMALL', 'LABEL', 'KBD', 'CODE'].includes(el.tagName)) {
      issues.push({ kind: 'vazando', text: label(el), where: path(el), w: el.clientWidth, need: el.scrollWidth });
    }
    if ((el.tagName === 'INPUT' || el.tagName === 'SELECT') && !['checkbox', 'radio', 'range', 'date', 'month'].includes(el.type)
        && el.scrollWidth > el.clientWidth + 2) {
      issues.push({ kind: 'campo-cortado', text: (el.value || el.placeholder || label(el)).slice(0, 80), where: path(el) });
    }
    if (hasText && (r.right > vw + 2 || r.left < -2) && !scrolls(el)) {
      issues.push({ kind: 'fora-da-tela', text: label(el), where: path(el), left: Math.round(r.left), right: Math.round(r.right), vw });
    }
    const dlg = el.closest('dialog[open] .sheet__inner');
    if (dlg && hasText && !scrolls(el)) {
      const d = dlg.getBoundingClientRect();
      if (r.left < d.left - 1 || r.right > d.right + 1) issues.push({ kind: 'fora-da-janela', text: label(el), where: path(el) });
    }
  }
  const seen = new Set();
  return issues.filter((i) => { const k = i.kind + '|' + i.text + '|' + i.where; if (seen.has(k)) return false; seen.add(k); return true; });
}
"""

# Alinhamento das janelas: as bordas de campos, opções e formas de pagamento precisam cair
# nas mesmas colunas (no máximo 3 posições de borda esquerda e 3 de direita, como numa grade
# de 3 colunas), e campos lado a lado precisam começar na mesma altura.
ALIGN = r"""
() => {
  const issues = [];
  const form = document.querySelector('dialog[open] form.inline-form');
  if (!form) return issues;
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const cells = [
    ...form.querySelectorAll('.grid-2 > *, .segmented > label, .chips > .chip-radio'),
  ].filter(visible).filter((el) => !el.closest('details:not([open])'));
  const cluster = (values) => {
    const sorted = [...values].sort((a, b) => a - b);
    const groups = [];
    for (const v of sorted) {
      if (groups.length && v - groups[groups.length - 1] <= 3) continue;
      groups.push(v);
    }
    return groups;
  };
  const lefts = cluster(cells.map((el) => el.getBoundingClientRect().left));
  const rights = cluster(cells.map((el) => el.getBoundingClientRect().right));
  if (lefts.length > 3 || rights.length > 3) {
    issues.push({ kind: 'desalinhado', text: `bordas: ${lefts.length} esquerdas, ${rights.length} direitas`, where: 'grade do formulário' });
  }
  for (const grid of form.querySelectorAll('.grid-2')) {
    const tops = [...grid.children]
      .map((child) => child.querySelector('input:not([type="hidden"]):not(.date-field__native), select, textarea'))
      .filter((el) => el && visible(el))
      .map((el) => Math.round(el.getBoundingClientRect().top));
    const rows = {};
    for (const child of grid.children) {
      const c = child.getBoundingClientRect();
      const key = Math.round(c.top / 8);
      (rows[key] ||= []).push(child);
    }
    if (tops.length > 1 && grid.children.length > 1) {
      const first = grid.children[0].getBoundingClientRect();
      const second = grid.children[1].getBoundingClientRect();
      const sameRow = Math.abs(first.top - second.top) < 4;
      if (sameRow && Math.max(...tops.slice(0, 2)) - Math.min(...tops.slice(0, 2)) > 1) {
        issues.push({ kind: 'desalinhado', text: `campos lado a lado em alturas diferentes (${tops.slice(0, 2).join(' / ')})`, where: 'grid-2' });
      }
    }
  }
  return issues;
}
"""

TIP_OUT = """() => {
  const t = document.querySelector('dialog[open] .tip__text');
  const d = document.querySelector('dialog[open] .sheet__inner');
  if (!t || !d) return null;
  const a = t.getBoundingClientRect(), b = d.getBoundingClientRect();
  return {text: t.innerText.slice(0, 70), out: a.left < b.left - 1 || a.right > b.right + 1 || a.left < 0 || a.right > innerWidth};
}"""

results: list[dict] = []


def login(page: Page):
    page.goto(f"{BASE}/entrar")
    page.evaluate("() => { localStorage.setItem('tour-v05-visto', '1'); localStorage.setItem('novidades-vistas', '9.9.9'); }")
    # QA_TEXT=grande repete a checagem com o texto ampliado (rótulos quebram em mais linhas).
    if os.environ.get("QA_TEXT"):
        page.evaluate("t => localStorage.setItem('preferencias-v1', JSON.stringify({ text: t }))", os.environ["QA_TEXT"])
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill(PASSWORD)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url("**/orcamento**", timeout=15000)


def settle(page: Page, ms: int = 700):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def check(page: Page, device: str, name: str, full: bool = True, scope: str | None = None):
    page.screenshot(path=OUT / f"{device}-{name}.png", full_page=full)
    for issue in page.evaluate(DETECT, scope):
        results.append({"device": device, "screen": name, **issue})


def check_tips(page: Page, device: str, name: str):
    tips = page.locator("dialog[open] .tip__btn")
    for i in range(tips.count()):
        tips.nth(i).click()
        page.wait_for_timeout(120)
        box = page.evaluate(TIP_OUT)
        if box and box["out"]:
            results.append({"device": device, "screen": name, "kind": "dica-cortada", "text": box["text"], "where": "tip"})
        tips.nth(i).click()
        page.wait_for_timeout(80)


def form(page: Page, device: str, name: str):
    page.wait_for_timeout(350)
    check(page, device, name, full=False, scope="dialog[open]")
    for issue in page.evaluate(ALIGN):
        results.append({"device": device, "screen": name, **issue})
    check_tips(page, device, name)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)


def dialogs(page: Page, device: str):
    page.goto(f"{BASE}/orcamento")
    settle(page)
    for kind in ("Única", "Parcelada", "Recorrente"):
        page.get_by_role("button", name="Nova despesa", exact=True).click()
        d = page.locator("dialog[open]")
        d.get_by_label(kind, exact=True).check()
        if kind == "Parcelada":
            d.get_by_label("Número de parcelas").fill("10")
            d.get_by_label("Valor total da compra").fill("1.800,00")
        d.get_by_label("Crédito").check()
        form(page, device, f"form-despesa-{kind.lower()}")
    # Débito com cartão e cartão só de débito.
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    page.locator("dialog[open]").get_by_label("Débito").check()
    form(page, device, "form-despesa-debito")
    page.get_by_role("button", name="Nova receita", exact=True).click()
    form(page, device, "form-receita")
    for url, button, name in (
        ("/calendario", "Agendar despesa prevista", "form-prevista"),
        ("/contas", "Nova conta", "form-conta"),
        ("/contas", "Transferir", "form-transferencia"),
        ("/cartoes", "Novo cartão", "form-cartao"),
        ("/investimentos", "Novo investimento", "form-investimento"),
        ("/metas", "Nova meta", "form-meta"),
        ("/dividas", "Novo financiamento", "form-financiamento"),
        ("/ajustes/solicitacoes", "Nova solicitação", "form-solicitacao"),
        ("/ajustes/perfil", "Editar perfil", "form-perfil"),
    ):
        page.goto(BASE + url)
        settle(page, 500)
        btn = page.get_by_role("button", name=button).first
        if btn.count() and btn.is_visible():
            btn.click()
            if name == "form-cartao":
                page.locator("dialog[open]").get_by_label("Crédito e débito").check()
            form(page, device, name)
    # Segunda etapa da meta (valor e prazo).
    page.goto(BASE + "/metas")
    settle(page, 500)
    page.get_by_role("button", name="Nova meta").first.click()
    d = page.locator("dialog[open]")
    d.get_by_label("Nome da meta").fill("Cirurgia no joelho")
    d.get_by_role("button", name="Continuar").click()
    d.get_by_label("Valor total").fill("12.000,00")
    form(page, device, "form-meta-valor")
    # Começar do zero (Perfil › Zona de risco), com tudo marcado.
    page.goto(BASE + "/ajustes/perfil")
    settle(page, 500)
    page.get_by_role("button", name="Começar do zero").click()
    page.locator("dialog[open]").get_by_label("Selecionar tudo").check()
    form(page, device, "form-comecar-do-zero")
    # Recado da administração: prévia antes de enviar.
    page.goto(BASE + "/admin?aba=recados")
    settle(page, 500)
    page.get_by_label("Título").fill("Nova versão disponível")
    page.get_by_label("Mensagem", exact=True).fill("A versão 0.9 traz a caixa de mensagens, o tema escuro salvo na conta e o começar do zero.")
    page.get_by_role("button", name="Revisar e enviar").click()
    form(page, device, "form-recado-previa")
    if device.startswith("celular"):
        page.locator(".tabbar").get_by_role("button", name="Mais").click()
        page.wait_for_timeout(350)
        check(page, device, "menu-mais", full=False, scope="dialog[open]")
        page.keyboard.press("Escape")
    # Importação: etapa de conferir as colunas de uma planilha.
    sample = OUT / "planilha.csv"
    sample.write_text("Data;Histórico;Valor\n05/01/2026;SUPERMERCADO BH LTDA;-152,30\n06/01/2026;SALARIO;3200,00\n", encoding="utf-8")
    page.goto(BASE + "/ajustes/dados")
    settle(page, 500)
    page.get_by_test_id("import-input").set_input_files(str(sample))
    settle(page, 700)
    check(page, device, "importar-colunas")


def main() -> int:
    with sync_playwright() as p:
        browser = getattr(p, "chromium").launch(**({"channel": BROWSER} if BROWSER != "chromium" else {}))
        for device, opts in VIEWPORTS.items():
            ctx = browser.new_context(locale="pt-BR", **opts)
            page = ctx.new_page()
            login(page)
            for name, url in PAGES:
                page.goto(BASE + url)
                settle(page)
                check(page, device, name)
            try:
                dialogs(page, device)
            except Exception as exc:  # noqa: BLE001 — um formulário que não abre vira problema, sem parar o resto
                page.screenshot(path=OUT / f"{device}-erro-formularios.png")
                results.append({"device": device, "screen": "formulários", "kind": "erro", "text": str(exc)[:300], "where": ""})
            ctx.close()
        browser.close()
    (OUT / "layout.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        print(f"PROBLEMA  [{r['device']}] {r['screen']}: {r['kind']} — {r['text']!r} ({r['where']})")
    screens = len(PAGES) * len(VIEWPORTS)
    print(f"Layout: {screens} telas e formulários em {len(VIEWPORTS)} tamanhos; {len(results)} problema(s).")
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
