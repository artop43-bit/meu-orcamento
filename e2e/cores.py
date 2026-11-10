"""Auditoria das cores (v1.2; matriz completa na v1.6).

Abre cada tela uma vez e, nela, troca o estilo (Padrão e Liquid glass), o tema (claro e escuro)
e as 10 cores de destaque sem recarregar (os mesmos atributos que o app grava no <html>). Em
cada combinação confere:

- contraste de todo texto visível com o fundo que ele tem de fato (camadas transparentes
  somadas; no Liquid glass, o fundo da página no ponto mais forte do brilho): 4,5:1, ou 3:1 em
  texto grande (WCAG AA);
- verde fixo: com outra cor escolhida, nada fora das cotações de mercado (alta/queda) pode
  continuar verde;
- itens do menu apagados;
- listas suspensas (v1.7): cada opção de cada <select> legível sobre o fundo sólido da lista, e a
  primeira lista da tela aberta de verdade (o texto das opções abertas passa no contraste).

Também tira uma foto do Orçamento em cada estilo e tema, para conferência visual.

    uv run --with playwright python e2e/cores.py
Mesmas variáveis do e2e/persona.py (QA_BASE_URL, QA_CREDENTIALS, QA_OUT, QA_BROWSER).
"""

import os
import pathlib
import re
import sys

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acessibilidade import PAGES, PUBLIC  # noqa: E402

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida")) / "cores"
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]

# Os mesmos de frontend/src/theme/tokens.ts e frontend/src/theme/styles.ts.
ACCENTS = ["verde", "azul", "indigo", "roxo", "rosa", "vermelho", "laranja", "ambar", "ciano", "grafite"]
STYLES = ["padrao", "glass"]
THEMES = ["light", "dark"]

# Aplica estilo, tema e cor no <html> e espera o navegador pintar de novo.
APPLY = """async ([style, theme, accent]) => {
  const root = document.documentElement;
  // Sem transições: a conferência lê a cor final, não a do meio da animação.
  if (!document.getElementById('sem-transicao')) {
    const css = document.createElement('style');
    css.id = 'sem-transicao';
    css.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
    document.head.appendChild(css);
  }
  root.dataset.style = style;
  root.dataset.theme = theme;
  root.dataset.accent = accent;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}"""

# Contraste de cada texto visível com o fundo real (camadas somadas até um fundo opaco; se não
# houver, o fundo da página com o brilho no ponto mais forte). Texto sobre imagem ou degradê
# (fotos, capa do perfil, Retrospectiva) fica de fora: lá o contraste é garantido nos testes
# de unidade (frontend/src/theme/theme.test.ts).
FIND_LOW_CONTRAST = """() => {
  // "rgb(r g b / a)" ou "color(srgb r g b / a)" (cores misturadas; componentes de 0 a 1).
  const parse = (c) => {
    const m = c.match(/[\\d.]+/g);
    if (!m) return [0, 0, 0, 0];
    const v = m.map(Number);
    const unit = c.startsWith('color(') ? 255 : 1;
    return [v[0] * unit, v[1] * unit, v[2] * unit, v[3] ?? 1];
  };
  const over = (top, bottom) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1); };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const probe = document.createElement('span');
  document.body.appendChild(probe);
  const read = (value) => { probe.style.backgroundColor = value; return parse(getComputedStyle(probe).backgroundColor); };
  const pageBg = read('var(--bg)');
  const glow = read('var(--glow)');
  const page = over(glow, pageBg);
  probe.remove();
  const found = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!['SPAN', 'P', 'A', 'BUTTON', 'LABEL', 'STRONG', 'H1', 'H2', 'H3', 'LI', 'TD', 'TH', 'DT', 'DD', 'SMALL', 'LEGEND', 'B', 'EM', 'DIV', 'SUMMARY', 'OPTION', 'SELECT', 'INPUT'].includes(el.tagName)) continue;
    if (el.tagName === 'INPUT' && ['range', 'checkbox', 'radio', 'color', 'hidden', 'file'].includes(el.type)) continue;
    const hasText = el.tagName === 'INPUT' || el.tagName === 'SELECT' ? Boolean(el.value) : [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    if (el.closest('[aria-hidden="true"], .sr-only, [disabled], .is-loading, svg, .story, .profile-hero, .auth__aside, .tone--up, .tone--down')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden') continue;
    let faded = false;
    for (let n = el; n; n = n.parentElement) if (Number(getComputedStyle(n).opacity) < 0.99) { faded = true; break; }
    if (faded) continue;
    // Fundo: camadas de baixo para cima a partir do primeiro ancestral opaco.
    const layers = [];
    let image = false;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.backgroundImage !== 'none' && n !== document.body) { image = true; break; }
      const c = parse(s.backgroundColor);
      if (c[3] > 0) { layers.push(c); if (c[3] >= 0.999) break; }
    }
    if (image) continue;
    let bg = layers.length && layers[layers.length - 1][3] >= 0.999 ? layers.pop() : page;
    for (const layer of layers.reverse()) bg = over(layer, bg);
    const fg = over(parse(cs.color), bg);
    const size = parseFloat(cs.fontSize);
    const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
    const value = ratio(fg, bg);
    if (value < (large ? 3 : 4.5)) {
      const key = `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(`${key} "${(el.value || el.textContent).trim().slice(0, 30)}" ${value.toFixed(2)}:1`);
    }
  }
  return found.slice(0, 8);
}"""

# Elementos pintados com o verde fixo de "positivo" (--ok) ou com o verde da cor padrão.
FIND_FIXED_GREEN = """() => {
  const probe = document.createElement('span');
  probe.style.color = 'var(--ok)';
  document.body.appendChild(probe);
  const fixed = new Set([getComputedStyle(probe).color]);
  for (const hex of ['#1f7a62', '#3fb994']) { probe.style.color = hex; fixed.add(getComputedStyle(probe).color); }
  probe.remove();
  const found = [];
  for (const el of document.querySelectorAll('body *')) {
    // Alta/queda do mercado (convenção da bolsa) e as amostras do seletor de cor (a do Verde é verde).
    if (el.closest('.tone--up, .tone--down, .market, .ticker, .accent-swatch')) continue;
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

# Opções dos <select>: texto sobre o fundo da lista (que precisa ser sólido; translúcido, o
# navegador pinta a lista aberta de branco por baixo).
FIND_BAD_OPTIONS = """() => {
  const parse = (c) => {
    const m = c.match(/[\\d.]+/g);
    if (!m) return [0, 0, 0, 0];
    const v = m.map(Number);
    const unit = c.startsWith('color(') ? 255 : 1;
    return [v[0] * unit, v[1] * unit, v[2] * unit, v[3] ?? 1];
  };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const over = (top, bottom) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1); };
  const custom = CSS.supports('appearance', 'base-select');
  const found = new Set();
  for (const select of document.querySelectorAll('select')) {
    if (select.disabled) continue;
    const list = parse(getComputedStyle(select, custom ? '::picker(select)' : null).backgroundColor);
    if (list[3] < 0.999) { found.add(`select#${select.id || select.name || '?'}: lista com fundo translúcido`); continue; }
    for (const option of select.options) {
      if (option.disabled) continue;
      const cs = getComputedStyle(option);
      const bg = over(parse(cs.backgroundColor), list);
      const value = ratio(over(parse(cs.color), bg), bg);
      if (value < 4.5) found.add(`option "${option.textContent.trim().slice(0, 24)}" ${value.toFixed(2)}:1`);
    }
  }
  return [...found].slice(0, 6);
}"""

OPEN_FIRST_SELECT = """() => {
  const select = [...document.querySelectorAll('select')].find((s) => !s.disabled && s.getBoundingClientRect().width && s.closest('.page, main'));
  if (!select) return false;
  select.scrollIntoView({ block: 'center' });
  select.id ||= 'lista-em-teste';
  return '#' + CSS.escape(select.id);
}"""

FADED_MENU = "[...document.querySelectorAll('.sidebar__sublink')].filter((e) => getComputedStyle(e).opacity !== '1').length"


def check(page: Page, path: str, problems: list[str]) -> int:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)
    combos = 0
    for style in STYLES:
        for theme in THEMES:
            for accent in ACCENTS:
                page.evaluate(APPLY, [style, theme, accent])
                where = f"{style}/{theme}/{accent} {path}"
                combos += 1
                for item in page.evaluate(FIND_LOW_CONTRAST):
                    problems.append(f"CONTRASTE {where}: {item}")
                if accent != "verde":
                    found = page.evaluate(FIND_FIXED_GREEN)
                    if found:
                        problems.append(f"VERDE FIXO {where}: {', '.join(found)}")
                if accent == "verde":
                    faded = page.evaluate(FADED_MENU)
                    if faded:
                        problems.append(f"MENU {where}: {faded} item(ns) do menu apagado(s)")
                for item in page.evaluate(FIND_BAD_OPTIONS):
                    problems.append(f"LISTA {where}: {item}")
            if path == "/orcamento":
                page.screenshot(path=OUT / f"orcamento-{style}-{theme}.png", full_page=True)
            # A primeira lista da tela aberta de verdade (o navegador desenha as opções).
            target = page.evaluate(OPEN_FIRST_SELECT)
            if target and page.evaluate("CSS.supports('appearance', 'base-select')"):
                page.click(target)
                page.wait_for_timeout(150)
                for item in page.evaluate(FIND_LOW_CONTRAST):
                    problems.append(f"LISTA ABERTA {style}/{theme} {path}: {item}")
                name = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "inicio"
                if style == "glass" and theme == "dark":
                    page.screenshot(path=OUT / f"lista-{name}.png")
                page.keyboard.press("Escape")
    return combos


def main() -> int:
    problems: list[str] = []
    combos = 0
    with sync_playwright() as p:
        browser = getattr(p, "chromium").launch(channel=None if BROWSER == "chromium" else BROWSER)
        page = browser.new_page(locale="pt-BR", viewport={"width": 1366, "height": 900})
        for path in PUBLIC:
            combos += check(page, path, problems)
        page.goto(f"{BASE}/entrar")
        page.get_by_label("E-mail").fill(EMAIL)
        page.get_by_label("Senha").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/orcamento**")
        for path in PAGES:
            combos += check(page, path, problems)
        browser.close()
    for problem in problems:
        print(problem)
    pages = len(PUBLIC) + len(PAGES)
    print(
        f"Cores: {pages} telas × {len(STYLES)} estilos × claro/escuro × {len(ACCENTS)} cores = {combos} combinações; "
        f"{len(problems)} problema(s)."
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
