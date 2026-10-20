"""Auditoria automática de acessibilidade (axe-core) em todas as telas.

Roda cada tela no celular e no desktop, em modo claro e escuro, e também com as janelas
principais abertas. Falha se houver problema "sério" ou "crítico" (padrão WCAG 2.1 AA).

    uv run --with playwright python e2e/acessibilidade.py
Mesmas variáveis do e2e/persona.py (QA_BASE_URL, QA_CREDENTIALS, QA_OUT, QA_BROWSER).
"""

import json
import os
import pathlib
import re
import sys

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida"))
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]
AXE = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "node_modules" / "axe-core" / "axe.min.js"

PUBLIC = ["/entrar", "/cadastro", "/esqueci-senha", "/privacidade", "/termos"]
PAGES = [
    "/orcamento",
    "/metas",
    "/analises?secao=resumo",
    "/analises?secao=tendencias",
    "/analises?secao=categorias",
    "/analises?secao=saude",
    "/analises?secao=patrimonio",
    "/analises?secao=comparar",
    "/analises?secao=projecao",
    "/analises?secao=simulador",
    "/analises?secao=monte",
    "/investimentos",
    "/investimentos?secao=cotacoes",
    "/calendario",
    "/contas",
    "/cartoes",
    "/historico",
    "/revisar",
    "/busca?q=mercado",
    "/admin",
    "/admin?aba=solicitacoes",
    "/ajustes/perfil",
    "/ajustes/solicitacoes",
    "/ajustes",
    "/ajustes/recorrencias",
    "/ajustes/categorias",
    "/ajustes/dados",
    "/ajustes/dados?aba=exportar",
    "/ajustes/notas",
    "/mensagens",
    "/dividas",
    "/divisoes",
    "/ajustes/app",
    "/analises?secao=calculadoras",
    "/admin?aba=recados",
    "/ajustes/seguranca",
    "/ajustes/preferencias",
    "/ajustes/ajuda",
]
DEVICES = {
    "desktop": dict(viewport={"width": 1366, "height": 900}),
    "celular": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True),
}
SERIOUS = {"serious", "critical"}


def audit(page: Page, where: str, found: list[dict]) -> None:
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
            const r = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
            return r.violations.map(v => ({
                id: v.id, impact: v.impact, help: v.help,
                nodes: v.nodes.slice(0, 3).map(n => n.target.join(" ") + " — " + (n.failureSummary || "").split("\\n").slice(1, 2).join(""))
            }));
        }"""
    )
    for violation in result:
        violation["where"] = where
        found.append(violation)


def settle(page: Page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def main() -> int:
    found: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=None if BROWSER == "chromium" else BROWSER)
        guest = browser.new_context(**DEVICES["desktop"])
        page = guest.new_page()
        for path in PUBLIC:
            page.goto(BASE + path)
            settle(page)
            audit(page, f"visitante desktop claro {path}", found)
        page.goto(f"{BASE}/entrar")
        page.get_by_label("E-mail").fill(EMAIL)
        page.get_by_label("Senha").fill(PASSWORD)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/orcamento**")
        state = guest.storage_state()
        guest.close()

        for device, options in DEVICES.items():
            for scheme in ("light", "dark"):
                ctx = browser.new_context(storage_state=state, color_scheme=scheme, reduced_motion="reduce", **options)
                page = ctx.new_page()
                label = f"{device} {'claro' if scheme == 'light' else 'escuro'}"
                for path in PAGES:
                    page.goto(BASE + path)
                    settle(page)
                    audit(page, f"{label} {path}", found)
                # Janelas: nova despesa (parcelada, com todos os passos) e nova receita; menu "Mais" no celular
                page.goto(f"{BASE}/orcamento")
                settle(page)
                page.get_by_role("button", name="Nova despesa", exact=True).click()
                page.locator("dialog[open]").get_by_label("Parcelada").check()
                page.wait_for_timeout(400)
                audit(page, f"{label} janela Nova despesa", found)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                page.get_by_role("button", name="Nova receita", exact=True).click()
                page.wait_for_timeout(400)
                audit(page, f"{label} janela Nova receita", found)
                page.keyboard.press("Escape")
                page.goto(f"{BASE}/ajustes/perfil")
                settle(page)
                page.get_by_role("button", name="Começar do zero").click()
                page.locator("dialog[open]").get_by_label("Selecionar tudo").check()
                page.wait_for_timeout(400)
                audit(page, f"{label} janela Começar do zero", found)
                page.keyboard.press("Escape")
                if device == "celular":
                    page.wait_for_timeout(300)
                    page.locator(".tabbar").get_by_role("button", name="Mais").click()
                    page.wait_for_timeout(400)
                    audit(page, f"{label} menu Mais", found)
                ctx.close()
        browser.close()

    serious = [v for v in found if v["impact"] in SERIOUS]
    (OUT / "acessibilidade.json").write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    by_rule: dict[str, list[dict]] = {}
    for v in found:
        by_rule.setdefault(f"[{v['impact']}] {v['id']}: {v['help']}", []).append(v)
    for rule, items in sorted(by_rule.items()):
        print(f"{rule} — {len(items)} tela(s)")
        for item in items[:4]:
            print(f"    {item['where']}: {item['nodes'][0] if item['nodes'] else ''}"[:220])
    print(f"\n{len(found)} problema(s) no total; {len(serious)} sério(s) ou crítico(s).")
    return 1 if serious else 0


if __name__ == "__main__":
    sys.exit(main())
