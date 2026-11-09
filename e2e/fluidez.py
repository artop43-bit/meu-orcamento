"""Enquadramento e fluidez (v1.6.5).

1. Enquadramento: abre cada tela uma vez e, nela, troca o estilo (Padrão e Liquid glass) e a
   largura do celular (360, 390 e 430 px) sem recarregar. Em cada combinação procura:
   - palavra partida no meio (ex.: "Usuário" / "s" em duas linhas);
   - conteúdo saindo pela lateral da tela (rolagem lateral da página);
   - o fim da tela escondido atrás da barra de abas flutuante.
2. Fluidez: troca as abas de baixo várias vezes e mede o tempo entre os quadros desenhados.
   Falha se a troca travar além do limite (o site publicado é bem mais rápido que o modo de
   desenvolvimento usado no CI; os limites têm folga para isso).

    uv run --no-project --with playwright python e2e/fluidez.py
Mesmas variáveis do e2e/persona.py (QA_BASE_URL, QA_CREDENTIALS, QA_OUT, QA_BROWSER).
"""

import json
import os
import pathlib
import re
import statistics
import sys

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acessibilidade import PAGES  # noqa: E402

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida")) / "fluidez"
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]

STYLES = ["padrao", "glass"]
WIDTHS = [360, 390, 430]
HEIGHT = 844
# Fluidez: pior quadro aceitável numa troca de abas (mediana e máximo das trocas), em ms.
WORST_MEDIAN_MS = 120
WORST_MAX_MS = 300

FRAMING = """() => {
  const out = [];
  const vw = window.innerWidth;
  if (document.documentElement.scrollWidth > vw + 1) out.push(`rolagem lateral: ${document.documentElement.scrollWidth}px > ${vw}px`);
  // Palavra partida no meio: o mesmo pedaço de texto em duas linhas sem hífen ou espaço entre elas.
  const root = document.querySelector('.content') || document.body;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  let n;
  while ((n = walker.nextNode())) {
    const text = n.textContent;
    if (!text.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest('[aria-hidden="true"], .sr-only, svg, input, textarea, code, .admin-user__email, .bubble__text, .error-card__message, details:not([open]) > :not(summary)')) continue;
    if (!el.getBoundingClientRect().width) continue;
    const re = /[\\p{L}\\p{N}]{4,}/gu;
    let m;
    while ((m = re.exec(text))) {
      const range = document.createRange();
      range.setStart(n, m.index);
      range.setEnd(n, m.index + m[0].length);
      const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)));
      if (tops.size > 1) {
        const key = `${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${m[0]}"`;
        if (!seen.has(key)) { seen.add(key); out.push('palavra partida: ' + key); }
      }
    }
  }
  // Fim da tela atrás da barra de abas flutuante (celular).
  const bar = document.querySelector('.tabbar');
  const page = document.querySelector('.page');
  if (bar && page && getComputedStyle(bar).display !== 'none') {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const barTop = bar.getBoundingClientRect().top;
    // Conteúdo de um <details> fechado tem posição calculada, mas não aparece: fica de fora.
    const shown = (e) => !e.closest('details:not([open]) > :not(summary)');
    const last = [...page.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.height && shown(e) && getComputedStyle(e).visibility !== 'hidden'; })
      .reduce((max, e) => Math.max(max, e.getBoundingClientRect().bottom), 0);
    if (last > barTop + 1) out.push(`fim da tela atrás da barra de abas: ${Math.round(last - barTop)}px`);
    window.scrollTo(0, 0);
  }
  return out.slice(0, 10);
}"""

APPLY = """async (style) => {
  document.documentElement.dataset.style = style;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}"""

RECORD = """() => {
  window.__frames = [];
  let last = performance.now();
  const tick = (t) => { window.__frames.push(t - last); last = t; if (window.__frames.length < 45) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}"""


def login(page: Page) -> None:
    page.goto(f"{BASE}/entrar")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill(PASSWORD)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url("**/orcamento**")


def framing(page: Page, problems: list[str]) -> int:
    combos = 0
    for path in PAGES:
        page.set_viewport_size({"width": WIDTHS[0], "height": HEIGHT})
        page.goto(f"{BASE}{path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        for style in STYLES:
            page.evaluate(APPLY, style)
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": HEIGHT})
                page.wait_for_timeout(120)
                combos += 1
                for item in page.evaluate(FRAMING):
                    problems.append(f"ENQUADRAMENTO {style}/{width}px {path}: {item}")
    return combos


def fluidity(page: Page, problems: list[str]) -> dict:
    page.set_viewport_size({"width": 390, "height": HEIGHT})
    page.goto(f"{BASE}/orcamento")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)  # telas baixadas em segundo plano depois de entrar
    worst: list[float] = []
    for name in ["Carteira", "Planejamento", "Análises", "Orçamento"] * 2:
        page.evaluate(RECORD)
        page.locator(".tabbar").get_by_role("link", name=name).first.click()
        page.wait_for_function("window.__frames.length >= 45", timeout=15000)
        frames = page.evaluate("window.__frames.slice(1)")
        worst.append(max(frames))
        page.wait_for_timeout(400)
    result = {"pior_quadro_ms": [round(w) for w in worst], "mediana_ms": round(statistics.median(worst)), "maximo_ms": round(max(worst))}
    if result["mediana_ms"] > WORST_MEDIAN_MS or result["maximo_ms"] > WORST_MAX_MS:
        problems.append(f"FLUIDEZ: troca de abas travando (mediana {result['mediana_ms']} ms, máximo {result['maximo_ms']} ms)")
    return result


def main() -> int:
    problems: list[str] = []
    with sync_playwright() as p:
        browser = getattr(p, "chromium").launch(channel=None if BROWSER == "chromium" else BROWSER)
        page = browser.new_context(
            locale="pt-BR", viewport={"width": 390, "height": HEIGHT}, is_mobile=True, has_touch=True, color_scheme="dark"
        ).new_page()
        login(page)
        combos = framing(page, problems)
        page.evaluate(APPLY, "padrao")
        speed = fluidity(page, problems)
        browser.close()
    (OUT / "fluidez.json").write_text(json.dumps({"problemas": problems, "fluidez": speed}, ensure_ascii=False, indent=2), encoding="utf-8")
    for problem in problems:
        print(problem)
    print(f"Enquadramento: {len(PAGES)} telas × {len(STYLES)} estilos × {len(WIDTHS)} larguras = {combos} combinações.")
    print(f"Fluidez: pior quadro por troca de aba {speed['pior_quadro_ms']} (mediana {speed['mediana_ms']} ms).")
    print(f"{len(problems)} problema(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
