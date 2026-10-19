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
    ("seguranca", "/ajustes/seguranca"),
    ("preferencias", "/ajustes/preferencias"),
    ("atalhos", "/ajustes/atalhos"),
    ("ajuda", "/ajustes/ajuda"),
    ("admin", "/admin"),
    ("admin-emails", "/admin?aba=emails"),
    ("admin-feedback", "/admin?aba=feedback"),
]

VIEWPORTS = {
    "monitor": dict(viewport={"width": 1366, "height": 900}),
    "notebook": dict(viewport={"width": 1100, "height": 760}),
    "celular": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2),
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
  for (const el of root.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none') continue;
    if (el.closest('svg, .chart, [aria-hidden="true"], .sr-only, .visually-hidden')) continue;
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
    page.get_by_role("button", name="Nova receita", exact=True).click()
    form(page, device, "form-receita")
    for url, button, name in (
        ("/calendario", "Agendar despesa prevista", "form-prevista"),
        ("/contas", "Nova conta", "form-conta"),
        ("/contas", "Transferir", "form-transferencia"),
        ("/cartoes", "Novo cartão", "form-cartao"),
        ("/investimentos", "Novo investimento", "form-investimento"),
        ("/metas", "Nova meta", "form-meta"),
    ):
        page.goto(BASE + url)
        settle(page, 500)
        btn = page.get_by_role("button", name=button).first
        if btn.count() and btn.is_visible():
            btn.click()
            form(page, device, name)


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
