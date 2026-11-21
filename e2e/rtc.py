import os
from pathlib import Path

from playwright.sync_api import Page, Route, expect

XML = Path(__file__).resolve().parents[1] / "integrations" / "rtc" / "nfse-teste.xml"


def _resposta_exemplo(route: Route):
    rota = route.request.url.split("?")[0].rsplit("/", 1)[-1]
    if rota == "danfse":
        route.fulfill(content_type="application/pdf", body="%PDF-1.7\n%%EOF\n")
        return
    if rota == "simular":
        entrada = route.request.post_data_json
        regular = entrada["regime"] == "regular"
        assert entrada["itens"][0]["classificacao"] == "000001"
        assert entrada["itens"][0]["base"] == ("100.00" if regular else "950.00")
        if regular:
            assert entrada["municipio"] == 3550308
        else:
            assert entrada["itens"][0]["atividade"] == "01"
        tributos = {"ibs": {"valor": "0.10"}, "cbs": {"valor": "0.90" if regular else "26.12"}}
        route.fulfill(json={
            "parcial": False, "simulado": not regular, "versao_base": "V0073",
            "totais": tributos, "itens": [{
                "numero": 1, "estado": "CALCULADO", "tributos": tributos,
                "erros": [], "memoria": ["Tributação integral."],
            }],
        })
        return
    if rota == "fundamentos":
        route.fulfill(json=[{"referencia": "LC 214/2025", "texto": "Regra Geral"}])
        return
    codigos = {
        "ncm": ("09012100", "Café torrado"),
        "uf": ("SP", "SÃO PAULO"), "municipio": ("3550308", "São Paulo"),
        "classificacao": ("000001", "Tributação integral"), "atividade": ("01", "Revenda"),
    }
    codigo, descricao = codigos[rota]
    item = {"codigo": codigo, "descricao": descricao}
    if rota == "classificacao":
        item["cst"] = "000"
    route.fulfill(json={"itens": [item], "total": 1, "versao_base": "V0073"})


def validar_reforma(page: Page, base: str):
    real = os.environ.get("QA_RTC_REAL") == "1"
    if not real:
        page.route("**/api/rtc/**", _resposta_exemplo)
    try:
        page.goto(f"{base}/analises?secao=reforma-tributaria")
        page.get_by_label("Data da operação").fill("2026-11-20")
        page.get_by_label("UF da operação").select_option("SP")
        page.get_by_label("Município da operação").select_option("3550308")
        page.get_by_role("button", name="Consultar cClassTrib", exact=True).click()
        dialogo = page.get_by_role("dialog")
        dialogo.get_by_label("Buscar por código ou descrição").fill("000001")
        dialogo.get_by_role("button", name="Buscar", exact=True).click()
        dialogo.get_by_role("button", name="Fundamentação de 000001", exact=True).click()
        expect(dialogo.get_by_text("LC 214/2025", exact=True)).to_be_visible()
        dialogo.get_by_role("button", name="Usar 000001", exact=True).click()
        expect(dialogo).not_to_be_visible()
        expect(page.get_by_label("CST", exact=True)).to_have_value("000")
        page.get_by_label("Base de cálculo (R$)", exact=True).fill("100,00")
        page.get_by_role("button", name="Calcular tributos", exact=True).click()
        resultado = page.get_by_role("region", name="Resultado da simulação")
        expect(resultado).to_contain_text("0,90")
        expect(resultado.get_by_text("Memória de cálculo", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        page.get_by_label("Regime de IBS e CBS").select_option("simples")
        page.get_by_label("Data da operação").fill("2027-03-15")
        page.get_by_label("Base de cálculo (R$)", exact=True).fill("950,00")
        page.get_by_label("Atividade do Simples", exact=True).fill("01")
        page.get_by_label("Alíquota efetiva IBS (%)").fill("1,25")
        page.get_by_label("Alíquota efetiva CBS (%)").fill("2,75")
        page.get_by_role("button", name="Calcular tributos", exact=True).click()
        expect(resultado).to_contain_text("26,12")

        page.get_by_role("button", name="Consultar tabelas", exact=True).click()
        tabela = page.get_by_role("region", name="Tabelas da Receita Federal")
        tabela.get_by_label("Tabela fiscal").select_option("classificacao")
        tabela.get_by_label("Data de vigência").fill("2026-11-20")
        tabela.get_by_label("Buscar por código ou descrição").fill("000001")
        tabela.get_by_role("button", name="Buscar", exact=True).click()
        expect(tabela.get_by_role("button", name="Fundamentação de 000001")).to_be_visible()

        page.get_by_role("button", name="Gerar DANFSe", exact=True).click()
        page.get_by_label("XML da NFS-e").set_input_files(XML)
        with page.expect_download() as download:
            page.get_by_role("button", name="Baixar DANFSe", exact=True).click()
        assert download.value.suggested_filename == "danfse.pdf"
        assert download.value.path().read_bytes().startswith(b"%PDF-")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        if not real:
            page.unroute("**/api/rtc/**", _resposta_exemplo)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    from persona import BASE, BROWSER, EMAIL, PASSWORD

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(channel=None if BROWSER == "chromium" else BROWSER)
        for largura in (1366, 390):
            contexto = navegador.new_context(viewport={"width": largura, "height": 850})
            login = contexto.request.post(
                f"{BASE}/api/auth/login",
                headers={"X-Requested-With": "fetch"},
                data={"email": EMAIL, "password": PASSWORD},
            )
            assert login.ok, login.status
            inicio = contexto.request.post(
                f"{BASE}/api/onboarding/done", headers={"X-Requested-With": "fetch"}
            )
            assert inicio.ok, inicio.status
            validar_reforma(contexto.new_page(), BASE)
            print(f"Reforma Tributária ({largura}px): OK")
            contexto.close()
