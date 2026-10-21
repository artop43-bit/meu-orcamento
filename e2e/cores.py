"""Auditoria das cores de destaque (v1.2).

Com cada cor de destaque, no claro e no escuro, abre as telas principais e procura elementos
pintados com o verde fixo de "positivo" (--ok). Com a cor trocada, nada fora das cotações de
mercado (alta/queda, convenção da bolsa) pode continuar verde: o positivo segue a cor escolhida.
Também tira uma foto do Orçamento em cada combinação, para conferência visual.

    uv run --with playwright python e2e/cores.py
Mesmas variáveis do e2e/persona.py (QA_BASE_URL, QA_CREDENTIALS, QA_OUT, QA_BROWSER).
"""

import os
import pathlib
import re
import sys

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida")) / "cores"
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]

ACCENTS = ["roxo", "azul", "vermelho", "ambar", "grafite"]
PAGES = ["/orcamento", "/contas", "/metas", "/analises?secao=resumo", "/analises?secao=saude", "/historico", "/calendario", "/dividas", "/investimentos"]

# Cores computadas de todos os elementos visíveis; devolve os que usam o verde fixo (--ok).
FIND_FIXED_GREEN = """() => {
  const probe = document.createElement('span');
  probe.style.color = 'var(--ok)';
  document.body.appendChild(probe);
  const fixed = new Set([getComputedStyle(probe).color]);
  // O verde da cor padrão também não pode sobrar fixo em gráficos e ícones.
  for (const hex of ['#1f7a62', '#3fb994']) { probe.style.color = hex; fixed.add(getComputedStyle(probe).color); }
  probe.remove();
  const found = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.tone--up, .tone--down, .market, .ticker')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    for (const prop of ['color', 'backgroundColor', 'borderLeftColor', 'fill', 'stroke']) {
      if (prop === 'borderLeftColor' && cs.borderLeftWidth === '0px') continue;
      if (fixed.has(cs[prop]) && (prop !== 'color' || el.textContent.trim())) {
        found.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} (${prop})`);
        break;
      }
    }
  }
  return [...new Set(found)].slice(0, 10);
}"""


def set_appearance(page: Page, theme: str, accent: str):
    page.evaluate(
        """async ([theme, accent]) => {
          const r = await fetch('/api/me/appearance', {method: 'PATCH', credentials: 'include',
            headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
            body: JSON.stringify({theme, accent})});
          if (!r.ok) throw new Error('aparência: ' + r.status);
          localStorage.removeItem('preferencias-v1');
        }""",
        [theme, accent],
    )


def main() -> int:
    problems: list[str] = []
    with sync_playwright() as p:
        browser = getattr(p, "chromium").launch(channel=None if BROWSER == "chromium" else BROWSER)
        page = browser.new_page(locale="pt-BR", viewport={"width": 1366, "height": 900})
        page.goto(f"{BASE}/entrar")
        page.get_by_label("E-mail").fill(EMAIL)
        page.get_by_label("Senha").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/orcamento**")
        for accent in ACCENTS:
            for theme in ("light", "dark"):
                set_appearance(page, theme, accent)
                for path in PAGES:
                    page.goto(f"{BASE}{path}")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(500)
                    assert page.evaluate("document.documentElement.dataset.accent") == accent
                    found = page.evaluate(FIND_FIXED_GREEN)
                    faded = page.evaluate("[...document.querySelectorAll('.sidebar__sublink')].filter((e) => getComputedStyle(e).opacity !== '1').length")
                    if faded:
                        problems.append(f"{accent}/{theme} {path}: {faded} item(ns) do menu apagado(s)")
                    if found:
                        problems.append(f"{accent}/{theme} {path}: {', '.join(found)}")
                    if path == "/orcamento":
                        page.screenshot(path=OUT / f"orcamento-{accent}-{theme}.png", full_page=True)
        set_appearance(page, "system", "verde")
        browser.close()
    for problem in problems:
        print("VERDE FIXO", problem)
    combos = len(ACCENTS) * 2 * len(PAGES)
    print(f"Cores: {combos} telas ({len(ACCENTS)} cores, claro e escuro); {len(problems)} problema(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
