"""Celular no motor do Safari (WebKit) em tamanho de iPhone (v1.4.1).

Confere o que mais pesa no uso pelo iPhone: trocar de aba (tocando e deslizando) sem tela
vazia, o menu "Mais" abrindo e fechando na hora, o gráfico do Histórico cabendo na tela e
nenhuma tela mais larga que o celular. Roda depois da persona (conta com dados):
    uv run --no-project --with playwright python e2e/iphone.py
Variáveis: QA_BASE_URL, QA_CREDENTIALS, QA_OUT (as mesmas da persona).
Sai com código 1 se algo falhar.
"""

import os
import pathlib
import re
import sys

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida")) / "iphone"
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]

PAGES = ["/orcamento", "/contas", "/cartoes", "/dividas", "/divisoes", "/calendario", "/metas", "/analises", "/historico", "/investimentos", "/ajustes", "/mensagens"]

# Arrasto feito com eventos de toque do próprio navegador; mede, a cada quadro, quanto da
# largura da tela fica sem a página nem a tela vizinha (deve ser zero).
SWIPE = """async ([x0, x1, y]) => {
  const target = document.elementFromPoint(x0, y);
  const touch = (x) => new Touch({ identifier: 1, target, clientX: x, clientY: y, pageX: x, pageY: y + scrollY });
  const fire = (type, x) => target.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true,
    touches: type === 'touchend' ? [] : [touch(x)], changedTouches: [touch(x)] }));
  const W = innerWidth;
  const gaps = [];
  let running = true;
  const tick = () => {
    const r = document.querySelector('.page')?.getBoundingClientRect(); const pad = parseFloat(getComputedStyle(document.querySelector('.content')).paddingLeft) || 0; const page = r && { left: r.left - pad, right: r.right + pad };
    const peek = document.querySelector('.swipe-peek:not([hidden])')?.getBoundingClientRect();
    const ghost = document.querySelector('.swipe-ghost')?.getBoundingClientRect();
    const spans = [page, peek, ghost].filter(Boolean).map((r) => [Math.max(0, r.left), Math.min(W, r.right)]).sort((a, b) => a[0] - b[0]);
    let covered = 0, x = 0;
    for (const [a, b] of spans) { if (b > x) { covered += b - Math.max(a, x); x = b; } }
    gaps.push(W - covered);
    if (running) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  fire('touchstart', x0);
  for (let i = 1; i <= 12; i++) { await wait(16); fire('touchmove', x0 + (x1 - x0) * i / 12); }
  fire('touchend', x1);
  await wait(700);
  running = false;
  return Math.max(...gaps);
}"""

problems: list[str] = []


def check(ok: bool, message: str):
    print(("PASS  " if ok else "FAIL  ") + message)
    if not ok:
        problems.append(message)


def idle(page: Page, ms: int = 300):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def main():
    with sync_playwright() as p:
        browser = p.webkit.launch()
        device = dict(p.devices["iPhone 15 Pro"])
        device.pop("default_browser_type", None)
        ctx = browser.new_context(**device, locale="pt-BR")
        page = ctx.new_page()
        page.goto(f"{BASE}/entrar")
        page.get_by_label("E-mail").fill(EMAIL)
        page.get_by_label("Senha").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/orcamento**")
        idle(page)
        width = page.evaluate("innerWidth")

        # Nenhuma tela mais larga que o celular.
        for path in PAGES:
            page.goto(f"{BASE}{path}")
            idle(page, 500)
            wide = page.evaluate("document.documentElement.scrollWidth")
            check(wide <= width + 1, f"{path}: cabe na largura ({wide} de {width}px)")
            page.screenshot(path=OUT / f"{path.strip('/').replace('/', '-')}.png")

        # Abas de baixo por toque: cada uma abre a tela certa.
        page.goto(f"{BASE}/orcamento")
        idle(page)
        tabbar = page.locator(".tabbar")
        for name, url in (("Carteira", "/contas"), ("Planejamento", "/calendario"), ("Análises", "/analises"), ("Orçamento", "/orcamento")):
            tabbar.get_by_role("link", name=name).tap()
            page.wait_for_url(f"**{url}**")
            expect(page.locator(".page h1").first).to_be_visible()
        check(True, "abas de baixo por toque")

        # Deslizar: troca a aba de baixo, sem vazio na tela.
        if page.evaluate("() => { try { new Touch({ identifier: 1, target: document.body }); return true; } catch { return false; } }"):
            page.goto(f"{BASE}/cartoes")
            idle(page, 600)
            gap = page.evaluate(SWIPE, [width - 40, 50, 560])
            check(page.url.endswith("/calendario") and gap < 8, f"deslizar Cartões → Calendário sem vazio ({page.url}, vazio máx. {gap:.0f}px)")
            idle(page, 400)
            gap = page.evaluate(SWIPE, [50, width - 40, 560])
            check(page.url.endswith("/cartoes") and gap < 8, f"deslizar de volta para Cartões sem vazio ({page.url}, vazio máx. {gap:.0f}px)")
        else:
            print("SKIP  deslizar (este WebKit não cria eventos de toque; coberto pela persona no Chromium)")

        # Abrir o "Mais" logo depois de trocar de aba: o menu abre e continua aberto.
        idle(page, 600)
        tabbar.get_by_role("link", name="Carteira").tap()
        page.wait_for_timeout(30)
        tabbar.get_by_role("button", name="Mais").tap()
        page.wait_for_timeout(700)
        check(page.locator("dialog[open]", has_text="Mais opções").count() == 1, "Mais abre logo depois de trocar de aba")
        page.keyboard.press("Escape")

        # Menu "Mais": abre, e ao tocar num item fecha na hora.
        idle(page, 600)
        tabbar.get_by_role("button", name="Mais").tap()
        menu = page.locator("dialog[open]", has_text="Mais opções")
        expect(menu).to_be_visible()
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "menu-mais.png")
        heights = menu.locator(".menu-theme label").evaluate_all("els => els.map((e) => Math.round(e.getBoundingClientRect().height))")
        check(len(set(heights)) == 1 and heights[0] < 52, f"tema em uma linha só ({heights})")
        menu.get_by_role("link", name="Investimentos").tap()
        try:
            expect(menu).to_have_count(0, timeout=300)
            closed = True
        except AssertionError:
            closed = False
        check(closed, "menu Mais fecha na hora ao abrir uma tela")
        page.wait_for_url("**/investimentos")

        # Histórico: gráfico cabe na tela e os meses não se sobrepõem.
        page.goto(f"{BASE}/historico")
        idle(page, 800)
        check(page.locator(".chart2__scroll.is-scrollable").count() == 0, "gráfico do Histórico cabe na tela")
        overlaps = page.evaluate("""() => {
          const svg = document.querySelector('.chart2__svg');
          const h = svg.getBoundingClientRect().bottom;
          const xs = [...svg.querySelectorAll('text.chart2__axis')].map((t) => t.getBoundingClientRect()).filter((r) => r.bottom > h - 20).sort((a, b) => a.left - b.left);
          return xs.slice(1).filter((r, i) => r.left < xs[i].right - 0.5).length;
        }""")
        check(overlaps == 0, f"meses do Histórico sem sobreposição ({overlaps})")
        page.screenshot(path=OUT / "historico.png")
        browser.close()

    print(f"\niPhone (WebKit): {len(problems)} problema(s).")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
