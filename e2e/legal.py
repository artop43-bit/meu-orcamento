"""Confere documentos públicos e aceite no cadastro, numa instância de teste."""

import os
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = Path(os.environ.get("QA_OUT", "e2e/saida"))
VERSION = "2026-11-21"


def conferir_documento(page: Page, title: str, path: str, style: str, theme: str, tag: str):
    page.wait_for_url(f"**{path}")
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
    expect(page.get_by_text(f"Versão {VERSION}", exact=False)).to_be_visible()
    expect(page.get_by_role("link", name="Voltar", exact=False)).to_have_attribute(
        "href", "/entrar"
    )
    page.evaluate(
        "([style, theme]) => Object.assign(document.documentElement.dataset, {style, theme})",
        [style, theme],
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=OUT / f"{tag}.png", full_page=True, animations="disabled")


def cadastro(browser: Browser, width: int, style: str, theme: str):
    context = browser.new_context(viewport={"width": width, "height": 900}, locale="pt-BR")
    try:
        page = context.new_page()
        page.goto(f"{BASE}/cadastro")
        expect(page.get_by_role("heading", name="Criar conta")).to_be_visible()
        form = page.locator("form")
        checkbox = form.get_by_role("checkbox")
        expect(checkbox).to_have_accessible_name(
            "Aceito os Termos de uso e declaro que li a Política de privacidade."
        )
        for title, path in (
            ("Termos de uso", "/termos"),
            ("Política de privacidade", "/privacidade"),
        ):
            with page.expect_popup() as popup:
                form.get_by_role("link", name=title, exact=True).click()
            doc = popup.value
            conferir_documento(doc, title, path, style, theme, f"legal-{width}-{style}-{path[1:]}")
            for solution in ("Cofre & Garantias", "Caderno & Conhecimento"):
                expect(doc.get_by_text(solution, exact=False).first).to_be_visible()
            if path == "/termos":
                expect(doc.get_by_role("link", name="Política de privacidade")).to_have_attribute(
                    "href", "/privacidade"
                )
            else:
                expect(doc.get_by_role("link", name="Segurança → Excluir conta")).to_have_attribute(
                    "href", "/seguranca"
                )
                expect(
                    doc.get_by_role("link", name="Meu Orçamento → Ajustes → Importar e exportar")
                ).to_have_attribute("href", "/ajustes/dados?aba=exportar")
            doc.close()

        page.get_by_label("E-mail", exact=True).fill(f"legal-{uuid4().hex}@example.com")
        page.get_by_label("Senha", exact=True).fill("senha-ficticia-teste-legal-123")
        page.get_by_label("Confirme a senha", exact=True).fill("senha-ficticia-teste-legal-123")
        submit = page.get_by_role("button", name="Criar conta", exact=True)
        submit.click()
        expect(checkbox).to_have_attribute("aria-invalid", "true")

        checkbox.check()
        with page.expect_response(
            lambda response: response.url.endswith("/api/auth/register")
        ) as registered:
            submit.click()
        assert registered.value.ok, registered.value.status
        expect(page.get_by_role("heading", name="Verifique seu e-mail")).to_be_visible()
        print(f"Termos, privacidade e cadastro em {width}px ({style}, {theme}): OK", flush=True)
    finally:
        context.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    channel = os.environ.get("QA_BROWSER", "chromium")
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch(channel=None if channel == "chromium" else channel)
        for width, style, theme in (
            (1366, "padrao", "light"),
            (1366, "glass", "dark"),
            (390, "padrao", "light"),
        ):
            cadastro(chromium, width, style, theme)
        chromium.close()
