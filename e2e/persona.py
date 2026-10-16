"""QA da persona: usa o Meu Orçamento pela interface, como uma pessoa de verdade (Playwright).

Roda no CI a cada PR e localmente:
    uv run --with playwright --with pyotp python e2e/persona.py
Variáveis: QA_BASE_URL (padrão http://localhost:5173), QA_CREDENTIALS (arquivo com e-mail e
senha gerado por `python -m app.cli seed-demo --credentials-file`), QA_OUT (pasta dos prints),
QA_BROWSER (chromium ou msedge). Precisa de uma conta de demonstração VAZIA.

Persona: Carla, 34 anos, assistente administrativa em Belo Horizonte.
Salário líquido de R$ 3.200 (perto do rendimento médio do trabalho no Brasil, IBGE/PNAD),
aluguel, contas da casa, transporte público, mercado e lazer moderado. Celular novo
parcelado, dentista parcelado, uma viagem que deixa um mês no vermelho, freelas
eventuais, um aumento em outubro, reserva pequena e uma meta de viagem.

Cada passo é verificado; falhas viram FAIL com print e o roteiro continua.
"""

import json
import os
import pathlib
import re
import sys
import time
import traceback
from datetime import date

import pyotp
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("QA_BASE_URL", "http://localhost:5173")
OUT = pathlib.Path(os.environ.get("QA_OUT", "e2e/saida"))
OUT.mkdir(parents=True, exist_ok=True)
CRED = pathlib.Path(os.environ.get("QA_CREDENTIALS", "backend/local-dev-cred.txt")).read_text(encoding="utf-8")
BROWSER = os.environ.get("QA_BROWSER", "chromium")
EMAIL = re.search(r"E-mail:\s*(\S+)", CRED)[1]
PASSWORD = re.search(r"Senha:\s*(\S+)", CRED)[1]
TODAY = date.today()
CURRENT = f"{TODAY.year}-{TODAY.month:02d}"

results: list[dict] = []
console_errors: list[str] = []
http_errors: list[str] = []


def step(name):
    def wrap(fn):
        def run(*args, **kwargs):
            started = time.time()
            try:
                value = fn(*args, **kwargs)
                results.append({"step": name, "ok": True, "s": round(time.time() - started, 1)})
                print(f"PASS  {name}", flush=True)
                return value
            except Exception as exc:  # noqa: BLE001
                page = args[0] if args and isinstance(args[0], Page) else None
                shot = None
                if page:
                    shot = OUT / f"falha-{len(results):02d}.png"
                    try:
                        page.screenshot(path=shot, full_page=True)
                    except Exception:  # noqa: BLE001
                        shot = None
                results.append({"step": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:600], "shot": str(shot)})
                print(f"FAIL  {name}: {exc}"[:400], flush=True)
                traceback.print_exc(limit=2)
                return None

        return run

    return wrap


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def months_back(n: int) -> str:
    y, m = TODAY.year, TODAY.month - n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def dialog(page: Page):
    return page.locator("dialog[open]")


def idle(page: Page, ms: int = 150):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def open_month(page: Page, month: str):
    page.goto(f"{BASE}/orcamento/{month}")
    idle(page)
    expect(page.locator("h1")).to_be_visible()


def add_expense(page: Page, month: str, desc: str, amount: float, cat: str, day: int | None = None, kind: str = "single", parcelas: int | None = None):
    page.get_by_role("button", name="Nova conta", exact=True).click()
    d = dialog(page)
    expect(d).to_be_visible()
    d.get_by_label("Descrição").fill(desc)
    if kind == "installments":
        d.get_by_label("Parcelada").check()
    elif kind == "recurring":
        d.get_by_label("Todo mês").check()
    d.get_by_label(re.compile(r"^Valor")).fill(money(amount))
    if day:
        d.locator('input[type="date"]').fill(f"{month}-{day:02d}")
    d.get_by_label("Categoria").select_option(label=cat)
    if parcelas:
        d.get_by_label("Número de parcelas").fill(str(parcelas))
    d.get_by_role("button", name="Adicionar conta").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page, 50)


def add_income(page: Page, desc: str, amount: float, every_month: bool = False):
    page.get_by_role("button", name="Nova renda", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill(desc)
    d.get_by_label("Valor", exact=True).fill(money(amount))
    if every_month:
        d.get_by_label("Recebo todo mês (renda fixa)").check()
    d.get_by_role("button", name="Adicionar renda").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page, 50)


def pay_all(page: Page):
    boxes = page.locator(".ledger__row input[type=checkbox]:not(:checked)")
    for _ in range(40):
        if boxes.count() == 0:
            return
        boxes.first.click()
        idle(page, 80)
    raise AssertionError("contas não ficaram pagas")


def api(page: Page, path: str):
    response = page.request.get(f"{BASE}/api{path}")
    assert response.ok, f"{path}: {response.status}"
    return response.json()


# ---------------------------------------------------------------- dados da persona

FIXED = [  # descrição, valor, categoria, dia
    ("Aluguel", 1050.00, "Moradia", 10),
    ("Internet", 99.90, "Serviços", 15),
    ("Plano de celular", 49.90, "Serviços", 20),
    ("Academia", 89.90, "Saúde", 5),
    ("Streaming", 44.90, "Lazer", 8),
    ("Passe de ônibus (BHBus)", 180.00, "Transporte", 1),
]

# mercado, delivery, energia, água, farmácia, lazer, uber (do mais antigo ao mês atual)
VARIABLE = [
    (690, 95, 158.4, 68.2, 45, 180, 52),
    (720, 140, 149.1, 71.5, 80, 260, 64),
    (705, 110, 132.7, 66.0, 38, 210, 48),
    (760, 180, 127.3, 70.1, 52, 240, 75),
    (735, 80, 141.6, 69.3, 120, 120, 58),
    (810, 210, 155.2, 72.4, 60, 700, 90),
    (690, 90, 151.0, 70.0, 45, 160, 40),
    (700, 60, 160.3, 74.6, 70, 150, 55),
    (380, 60, 0, 0, 35, 260, 30),  # mês atual, até agora
]
LABELS = ["Mercado", "Delivery (iFood)", "Energia (Cemig)", "Água (Copasa)", "Farmácia", "Lazer e saídas", "Uber"]
CATS = ["Alimentação", "Alimentação", "Serviços", "Serviços", "Saúde", "Lazer", "Transporte"]
DAYS = [6, 12, 25, 22, 14, 18, 9]


@step("Login com a conta de demonstração (vazia)")
def login(page: Page):
    page.goto(f"{BASE}/entrar")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill(PASSWORD)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url("**/orcamento**")
    idle(page)


@step("Conta nova: orçamento vazio mostra orientação")
def empty_state(page: Page):
    expect(page.get_by_role("heading", name="Comece pela sua renda")).to_be_visible()
    page.goto(f"{BASE}/analises")
    idle(page)
    expect(page.get_by_role("heading", name="Vamos começar?")).to_be_visible()
    expect(page.get_by_role("heading", name="Como começar")).to_be_visible()


@step("Faixa do 2FA: 'Agora não' esconde até fechar o navegador")
def banner_later(page: Page):
    banner = page.get_by_role("region", name="Sugestão de segurança")
    expect(banner).to_be_visible()
    banner.get_by_role("button", name="Agora não").click()
    expect(banner).to_have_count(0)
    page.reload()
    idle(page)
    expect(page.get_by_role("region", name="Sugestão de segurança")).to_have_count(0)


@step("Categorias: limites de Lazer (R$ 300) e Alimentação (R$ 1.000)")
def limits(page: Page):
    page.goto(f"{BASE}/categorias")
    idle(page)
    for name, value in (("Lazer", 300), ("Alimentação", 1000)):
        page.locator(".item__main", has_text=name).first.click()
        page.get_by_label(re.compile("Limite por mês")).fill(money(value))
        page.get_by_role("button", name="Salvar").click()
        idle(page)
        expect(page.locator(".item__meta", has_text=f"limite de R$ {money(value)}")).to_be_visible()


@step("Primeiro mês: salário fixo e 6 contas fixas")
def first_month(page: Page, month: str):
    open_month(page, month)
    add_income(page, "Salário", 3200, every_month=True)
    for desc, value, cat, day in FIXED:
        add_expense(page, month, desc, value, cat, day, kind="recurring")
    expenses = api(page, f"/months/{month}")["expenses"]
    assert len(expenses) == 6, len(expenses)
    assert len(api(page, "/recurring")) == 7


def fill_month(page: Page, index: int, month: str, current: bool):
    open_month(page, month)
    data = api(page, f"/months/{month}")
    assert any(i["description"] == "Salário" for i in data["incomes"]), "salário fixo não apareceu"
    assert sum(1 for e in data["expenses"] if e["recurring_id"]) == 6, "contas fixas não apareceram"
    for label, cat, day, value in zip(LABELS, CATS, DAYS, VARIABLE[index], strict=True):
        if value:
            add_expense(page, month, label, value, cat, min(day, 28) if not current else min(day, TODAY.day))
    if index == 2:
        add_expense(page, month, "Celular novo (Samsung A55)", 159.90, "Outros", 12, kind="installments", parcelas=10)
    if index == 3:
        add_income(page, "Freela (planilhas)", 400)
    if index == 4:
        add_expense(page, month, "Dentista (canal)", 200, "Saúde", 15, kind="installments", parcelas=3)
    if index == 6:
        add_income(page, "Freela (site)", 450)
    if not current:
        pay_all(page)


@step("Lançar 8 meses completos (variáveis, parcelas, freelas) e marcar tudo como pago")
def history(page: Page, months: list[str]):
    for index, month in enumerate(months[:-1]):
        fill_month(page, index, month, current=False)
        summary = api(page, f"/months/{month}")["summary"]
        assert summary["pending_total"] in ("0.00", "0"), f"{month}: pendente {summary['pending_total']}"


@step("Mês atual: aumento de salário em Contas fixas (R$ 3.350) e gastos até hoje")
def current_month(page: Page, months: list[str]):
    page.goto(f"{BASE}/fixas")
    idle(page)
    page.locator(".item__main", has_text="Salário").first.click()
    page.get_by_label("Valor", exact=True).fill(money(3350))
    page.get_by_role("button", name="Salvar").click()
    idle(page)
    fill_month(page, len(months) - 1, months[-1], current=True)
    data = api(page, f"/months/{months[-1]}")
    salary = next(i for i in data["incomes"] if i["description"] == "Salário")
    assert salary["amount"].startswith("3350"), salary["amount"]
    before = api(page, f"/months/{months[-2]}")
    old = next(i for i in before["incomes"] if i["description"] == "Salário")
    assert old["amount"].startswith("3200"), "aumento não pode mudar meses passados"
    # Paga só as contas que já venceram, menos a internet (fica em atraso de propósito).
    for row in page.locator(".ledger__row").all():
        text = row.inner_text()
        if any(k in text for k in ("Aluguel", "Passe", "Academia", "Streaming", "Mercado")):
            box = row.locator("input[type=checkbox]")
            if not box.is_checked():
                box.click()
                idle(page, 80)


@step("Parcelas: celular aparece de 1/10 a 10/10 e dentista de 1/3 a 3/3")
def installments(page: Page, months: list[str]):
    first = api(page, f"/months/{months[2]}")["expenses"]
    cel = next(e for e in first if e["description"].startswith("Celular"))
    assert (cel["installment_number"], cel["installment_total"]) == (1, 10)
    later = api(page, f"/months/{months[2]}")
    last_month = months[2][:5] + f"{int(months[2][5:]) + 9:02d}" if int(months[2][5:]) + 9 <= 12 else f"{int(months[2][:4]) + 1}-{int(months[2][5:]) + 9 - 12:02d}"
    tail = api(page, f"/months/{last_month}")["expenses"]
    assert any(e["description"].startswith("Celular") and e["installment_number"] == 10 for e in tail), "parcela 10/10"
    dentist = [e for m in months[4:7] for e in api(page, f"/months/{m}")["expenses"] if e["description"].startswith("Dentista")]
    assert [e["installment_number"] for e in dentist] == [1, 2, 3], dentist
    assert later


@step("Excluir com Desfazer: some na hora, volta ao desfazer, sai de vez depois")
def undo_delete(page: Page, month: str):
    open_month(page, month)
    add_expense(page, month, "Lançamento errado", 12.34, "Outros", 3)
    row = page.locator(".ledger__row", has_text="Lançamento errado")
    expect(row).to_have_count(1)
    row.get_by_role("button", name="Excluir Lançamento errado").click()
    expect(row).to_have_count(0)
    page.get_by_role("button", name="Desfazer").click()
    expect(row).to_have_count(1)
    row.get_by_role("button", name="Excluir Lançamento errado").click()
    expect(row).to_have_count(0)
    page.wait_for_timeout(6800)
    idle(page)
    data = api(page, f"/months/{month}")
    assert not any(e["description"] == "Lançamento errado" for e in data["expenses"]), "não foi excluída"


@step("Editar conta: valor do mercado corrigido")
def edit_expense(page: Page, month: str):
    open_month(page, month)
    page.locator(".ledger__row", has_text="Mercado").locator(".ledger__open").click()
    d = dialog(page)
    d.get_by_label("Valor", exact=True).fill(money(395.50))
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0)
    idle(page)
    data = api(page, f"/months/{month}")
    assert next(e for e in data["expenses"] if e["description"] == "Mercado")["amount"].startswith("395.5")


@step("Investimentos: reserva no Tesouro Selic e CDB")
def investments(page: Page):
    page.goto(f"{BASE}/investimentos")
    idle(page)
    for name, kind, inst, invested, current, reserve in (
        ("Tesouro Selic 2029", "Tesouro Direto", "Nubank", 2800, 3020.45, True),
        ("CDB liquidez diária", "Renda fixa (CDB, LCI, LCA)", "Inter", 1000, 1043.20, False),
    ):
        page.get_by_role("button", name="Novo investimento").click()
        d = dialog(page)
        d.get_by_label("Nome").fill(name)
        d.get_by_label("Tipo").select_option(label=kind)
        d.get_by_label("Instituição (opcional)").fill(inst)
        d.get_by_label("Quanto investiu").fill(money(invested))
        d.get_by_label("Valor atual").fill(money(current))
        if reserve:
            d.get_by_label("Faz parte da minha reserva de emergência").check()
        d.get_by_role("button", name="Adicionar").click()
        expect(d).to_have_count(0)
        idle(page)
    assert len(api(page, "/investments")) == 2


@step("Metas: viagem para o Nordeste com prazo e primeiro depósito")
def goals(page: Page):
    page.goto(f"{BASE}/metas")
    idle(page)
    page.get_by_role("button", name="Nova meta").first.click()
    d = dialog(page)
    d.get_by_label("Nome da meta").fill("Viagem para o Nordeste")
    d.get_by_label("Quanto quer juntar").fill(money(4000))
    target = f"{TODAY.year + 1}-07-01"
    d.get_by_label("Até quando (opcional)").fill(target)
    d.get_by_role("button", name="Criar meta").click()
    expect(d).to_have_count(0)
    idle(page)
    page.get_by_label("Valor a guardar ou retirar da meta").fill(money(600))
    page.get_by_role("button", name="Guardar").click()
    idle(page)
    goal = api(page, "/goals")[0]
    assert goal["current_amount"].startswith("600"), goal


@step("Consultor: tom correto em cada mês")
def consultant(page: Page, months: list[str]):
    seen = {}
    for month in months:
        data = api(page, f"/analysis/insights?month={month}")
        seen[month] = (data["mood"], data["headline"], data["savings_pct"])
    (OUT / "consultor-por-mes.json").write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    july = seen[months[5]]
    assert july[0] == "concern", f"mês da viagem deveria ser vermelho: {july}"
    assert seen[months[4]][0] == "attention", f"mês do dentista deveria estar no limite: {seen[months[4]]}"
    assert seen[months[6]][0] in ("good", "great"), seen[months[6]]
    current = api(page, f"/analysis/insights?month={months[-1]}")
    assert current["in_progress"] is True
    titles = [a["title"] for a in current["alerts"]]
    # Streaming (R$ 44,90) também é Lazer: 260 + 44,90 passa do limite de 300.
    assert "Limite de Lazer estourado" in titles, titles
    # Compras lançadas com data passada já entram pagas; ficam em atraso só as não pagas de propósito.
    # Ficam sem pagar de propósito: parcela do celular (dia 12), internet (15) e plano de celular (20).
    overdue = sum(1 for day in (12, 15, 20) if day < TODAY.day)
    if overdue:
        assert f"{overdue} conta(s) em atraso" in titles, titles
    else:
        assert not any("atraso" in t for t in titles), titles
    messages = [m["title"] for m in current["messages"]]
    assert "Reserva ainda pequena" in messages, messages
    # Sobra do mês (~R$ 900) cobre os ~R$ 378/mês da meta: não deve haver alerta de ritmo.
    assert not any("Viagem" in t for t in titles), titles


@step("Análise financeira: seções com navegação e conteúdo (desktop)")
def dashboard(page: Page, months: list[str]):
    page.goto(f"{BASE}/analises")
    idle(page, 600)
    expect(page.get_by_role("heading", name="Análise financeira", level=1)).to_be_visible()
    nav = page.get_by_role("navigation", name="Seções da análise")
    expect(page.get_by_text("Seu consultor", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile("^Alertas"))).to_be_visible()
    page.screenshot(path=OUT / "resumo-desktop.png", full_page=True)
    checks = {
        "Tendências": "Renda × gastos",
        "Categorias": "Limites do mês",
        "Saúde financeira": "Score financeiro",
        "Patrimônio e metas": "Metas",
    }
    for section, heading in checks.items():
        nav.get_by_role("link", name=section).click()
        idle(page, 500)
        expect(page.get_by_role("heading", name=heading, exact=True).first).to_be_visible()
        assert nav.get_by_role("link", name=section).get_attribute("aria-current") == "page"
    # Mês da viagem: o consultor muda o tom
    nav.get_by_role("link", name="Resumo").click()
    idle(page, 400)
    page.get_by_label("Mês", exact=True).fill(months[5])
    idle(page, 600)
    expect(page.get_by_role("heading", name="Este mês fechou no vermelho")).to_be_visible()


@step("Comparar meses, projeção e simulador (seções Ferramentas)")
def other_tabs(page: Page, months: list[str]):
    nav = page.get_by_role("navigation", name="Seções da análise")
    nav.get_by_role("link", name="Comparar meses").click()
    idle(page, 400)
    expect(page.locator("table")).to_be_visible()
    nav.get_by_role("link", name="Projeção").click()
    idle(page, 400)
    expect(page.locator("table").first).to_be_visible()
    nav.get_by_role("link", name="Simulador").click()
    idle(page, 400)
    expect(page.locator('input[type="range"]').first).to_be_visible()


@step("Gráfico: dica com o mouse e leitura pelo teclado (setas)")
def chart_interaction(page: Page):
    page.goto(f"{BASE}/analises?secao=tendencias")
    idle(page, 700)
    svg = page.locator("svg.chart2__svg").first
    box = svg.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2)
    expect(page.locator(".chart2__tip").first).to_be_visible()
    expect(page.locator(".chart2__tip").first).to_contain_text("Renda")
    page.mouse.move(0, 0)
    svg.focus()
    page.keyboard.press("ArrowLeft")
    expect(page.locator(".chart2__tip").first).to_contain_text("Gastos")
    page.keyboard.press("Home")
    page.keyboard.press("Escape")
    expect(page.locator(".chart2__tip")).to_have_count(0)


@step("Monte sua análise: sugestão, filtros, tipo de gráfico, comparação")
def builder(page: Page):
    page.goto(f"{BASE}/analises?secao=monte")
    idle(page, 600)
    page.get_by_role("button", name=re.compile("Onde gastei no ano")).click()
    idle(page, 700)
    panel = page.get_by_role("complementary", name="Filtros da análise")
    expect(page.locator(".hbars__row", has_text="Moradia")).to_be_visible()
    page.get_by_role("radio", name="Rosca").check(force=True)
    idle(page, 400)
    expect(page.locator("figure.donut svg")).to_be_visible()
    panel.get_by_text("Mês × categoria", exact=True).click()
    idle(page, 600)
    page.get_by_role("radio", name="Barras empilhadas").check(force=True)
    panel.get_by_text("Período anterior", exact=True).click()
    idle(page, 700)
    expect(page.locator(".chart2__legend")).to_contain_text("Período anterior")
    # Só Lazer, em linhas, 6 meses, contra a média
    panel.get_by_text("Por mês", exact=True).click()
    panel.get_by_text("Lazer", exact=True).click()
    panel.get_by_text("6 meses", exact=True).click()
    panel.get_by_text("Minha média", exact=True).click()
    page.get_by_role("radio", name="Linhas").check(force=True)
    idle(page, 700)
    expect(page.locator(".builder__title")).to_contain_text("Gastos (Lazer) por mês")
    expect(page.locator(".builder__total").first).to_be_visible()
    # Renda só pode ser vista por mês: agrupamentos por categoria ficam desativados
    panel.get_by_text("Renda", exact=True).click()
    idle(page, 500)
    assert panel.get_by_role("radio", name="Por categoria").is_disabled()
    # Tabela
    panel.get_by_text("Gastos", exact=True).click()
    page.get_by_role("radio", name="Tabela").check(force=True)
    idle(page, 500)
    expect(page.locator(".builder table")).to_be_visible()
    page.screenshot(path=OUT / "construtor-desktop.png", full_page=True)


@step("Salvar análise, fixar no Resumo, editar e excluir com Desfazer")
def saved_analyses(page: Page):
    page.goto(f"{BASE}/analises?secao=monte")
    idle(page, 600)
    page.get_by_role("button", name=re.compile("Categorias mês a mês")).click()
    idle(page, 600)
    page.get_by_role("button", name="Salvar análise").click()
    d = dialog(page)
    d.get_by_label("Nome").fill("Meus gastos por categoria")
    expect(d.get_by_label("Fixar no Resumo da Análise financeira")).to_be_checked()
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0)
    idle(page, 600)
    saved = api(page, "/analysis/saved")
    assert [s["name"] for s in saved] == ["Meus gastos por categoria"], saved
    assert saved[0]["config"]["chart"] == "stacked"
    # Aparece no Resumo
    page.goto(f"{BASE}/analises?secao=resumo")
    idle(page, 800)
    expect(page.get_by_role("heading", name="Meus gastos por categoria")).to_be_visible()
    # Editar: troca para linhas e salva alterações
    page.goto(f"{BASE}/analises?secao=monte")
    idle(page, 600)
    page.get_by_role("button", name="Editar Meus gastos por categoria").click()
    idle(page, 500)
    page.get_by_role("radio", name="Linhas").check(force=True)
    page.get_by_role("button", name="Salvar alterações").click()
    dialog(page).get_by_role("button", name="Salvar").click()
    idle(page, 600)
    assert api(page, "/analysis/saved")[0]["config"]["chart"] == "line"
    # Excluir com desfazer
    page.get_by_role("button", name="Excluir Meus gastos por categoria").click()
    page.get_by_role("button", name="Desfazer").click()
    idle(page, 300)
    expect(page.get_by_role("heading", name="Meus gastos por categoria").first).to_be_visible()
    assert len(api(page, "/analysis/saved")) == 1
    # Deixa salva (e fixada) para os prints


@step("Versão e data do update no fim do menu")
def version(page: Page):
    page.goto(f"{BASE}/orcamento")
    idle(page)
    expect(page.locator(".sidebar .app-version")).to_contain_text(re.compile(r"Versão \d+\.\d+\.\d+ · \d{2}/\d{2}/\d{4} às \d{2}:\d{2}"))


@step("Celular: deslizar troca só as abas principais, em qualquer ponto da tela")
def mobile_sections(browser):
    ctx = browser.new_context(
        storage_state=STATE["state"], viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True
    )
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)

    def swipe(x0, x1, y=300):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y}]})
        for i in range(1, 13):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / 12, "y": y + 2}]})
            page.wait_for_timeout(16)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        page.wait_for_timeout(700)

    # Na Análise financeira, deslizar vai para a próxima aba principal (não troca de seção).
    page.goto(f"{BASE}/analises?secao=tendencias")
    idle(page, 700)
    swipe(330, 60)
    assert page.url.endswith("/investimentos"), page.url
    page.goto(f"{BASE}/analises?secao=resumo")
    idle(page, 700)
    swipe(60, 330)
    assert page.url.endswith("/metas"), page.url
    # Tela curta (Metas): o gesto vale também na parte de baixo, onde não há conteúdo.
    idle(page, 500)
    swipe(330, 60, y=720)
    assert "/analises" in page.url, page.url
    # Construtor no celular: chips abrem a janela de filtros
    page.goto(f"{BASE}/analises?secao=monte")
    idle(page, 700)
    page.locator(".filter-chip", has_text="Período").click()
    d = dialog(page)
    d.get_by_text("12 meses", exact=True).click()
    d.get_by_role("button", name="Ver resultado").click()
    expect(d).to_have_count(0)
    expect(page.locator(".filter-chip", has_text="Período")).to_contain_text("12 meses")
    page.screenshot(path=OUT / "construtor-celular.png", full_page=True)
    # Título grande: some da barra no topo e aparece ao rolar
    bar_title = page.locator(".mobile-bar strong")
    assert float(bar_title.evaluate("e => getComputedStyle(e).opacity")) < 0.5
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(500)
    assert float(bar_title.evaluate("e => getComputedStyle(e).opacity")) > 0.5
    ctx.close()


@step("Histórico e relatório do mês")
def history_report(page: Page, months: list[str]):
    page.goto(f"{BASE}/historico")
    idle(page)
    expect(page.locator(".chart, table").first).to_be_visible()
    page.goto(f"{BASE}/relatorio/{months[-2]}")
    idle(page)
    expect(page.get_by_text("Aluguel").first).to_be_visible()


@step("Exportar CSV, Excel e backup JSON")
def exports(page: Page):
    page.goto(f"{BASE}/dados")
    idle(page)
    for name in ("CSV", "Excel", "Baixar backup (JSON)"):
        with page.expect_download() as info:
            page.get_by_role("button", name=name).click()
        download = info.value
        path = OUT / download.suggested_filename
        download.save_as(path)
        assert path.stat().st_size > 200, f"{name} vazio"
    # O último download é o backup: precisa ser um JSON com os lançamentos da persona.
    backup = json.loads(path.read_text(encoding="utf-8"))
    assert backup and "expenses" in json.dumps(backup), "backup sem os lançamentos"


@step("Importar extrato OFX no mês atual (prévia, importa e não duplica)")
def import_ofx(page: Page):
    ofx = OUT / "extrato.ofx"
    d = TODAY.strftime("%Y%m")
    ofx.write_text(
        f"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}03<TRNAMT>-27.90<FITID>qa1<MEMO>PADARIA PAO QUENTE</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}04<TRNAMT>-63.40<FITID>qa2<MEMO>POSTO SHELL</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""",
        encoding="latin-1",
    )
    page.goto(f"{BASE}/dados")
    idle(page)
    before = len(api(page, f"/months/{CURRENT}")["expenses"])
    page.locator('input[type="file"][accept*=".ofx"]').set_input_files(str(ofx))
    idle(page, 500)
    expect(page.get_by_text("PADARIA PAO QUENTE")).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Importar \d+ lançamento")).click()
    idle(page, 600)
    after = len(api(page, f"/months/{CURRENT}")["expenses"])
    assert after == before + 2, (before, after)
    page.locator('input[type="file"][accept*=".ofx"]').set_input_files(str(ofx))
    idle(page, 500)
    page.screenshot(path=OUT / "import-repetido.png", full_page=True)
    again = len(api(page, f"/months/{CURRENT}")["expenses"])
    assert again == after, "reimportar não pode duplicar sozinho"


@step("Segurança: ativar 2FA, sair, entrar com código, desativar")
def two_factor(page: Page):
    page.goto(f"{BASE}/seguranca")
    idle(page)
    page.get_by_role("button", name="Ativar verificação em duas etapas").click()
    idle(page)
    secret = page.locator("code").first.inner_text().replace(" ", "")
    totp = pyotp.TOTP(secret)
    page.get_by_label("Código").fill(totp.now())
    page.get_by_role("button", name="Ativar", exact=True).click()
    idle(page)
    expect(page.get_by_text("Guarde estes códigos")).to_be_visible()
    page.get_by_role("button", name="Já guardei").click()
    idle(page)
    page.get_by_role("button", name="Sair").first.click()
    page.wait_for_url("**/entrar**")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill(PASSWORD)
    page.get_by_role("button", name="Entrar").click()
    idle(page)
    # Espera o próximo código para não repetir o usado na ativação (anti-replay).
    time.sleep(31 - (time.time() % 30))
    page.get_by_label(re.compile("Código")).fill(totp.now())
    page.get_by_role("button", name=re.compile("Entrar|Confirmar|Verificar")).click()
    page.wait_for_url("**/orcamento**")
    idle(page)
    expect(page.get_by_role("region", name="Sugestão de segurança")).to_have_count(0)
    page.goto(f"{BASE}/seguranca")
    idle(page)
    page.get_by_role("button", name="Desativar 2FA").click()
    page.get_by_label("Senha", exact=True).fill(PASSWORD)
    time.sleep(31 - (time.time() % 30))
    page.get_by_label("Código do aplicativo ou de recuperação").fill(totp.now())
    page.get_by_role("button", name="Desativar", exact=True).click()
    idle(page)
    assert api(page, "/auth/me")["totp_enabled"] is False


@step("Faixa do 2FA: 'Não mostrar mais' fica salvo na conta")
def banner_never(page: Page):
    page.evaluate("sessionStorage.clear()")
    page.goto(f"{BASE}/metas")
    idle(page)
    banner = page.get_by_role("region", name="Sugestão de segurança")
    expect(banner).to_be_visible()
    banner.get_by_role("button", name="Não mostrar mais").click()
    expect(banner).to_have_count(0)
    page.wait_for_timeout(500)
    assert api(page, "/auth/me")["twofa_prompt_dismissed"] is True


@step("Celular: painel, orçamento e gesto de troca de aba")
def mobile(browser):
    ctx = browser.new_context(
        storage_state=STATE["state"], viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True
    )
    page = ctx.new_page()
    page.goto(f"{BASE}/orcamento")
    idle(page, 600)
    page.screenshot(path=OUT / "celular-orcamento.png", full_page=True)
    expect(page.locator(".teaser")).to_be_visible()
    page.locator(".teaser").click()
    page.wait_for_url("**/analises**")
    idle(page, 800)
    page.screenshot(path=OUT / "celular-painel.png", full_page=True)
    page.goto(f"{BASE}/categorias")
    idle(page)
    page.screenshot(path=OUT / "celular-categorias.png", full_page=True)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "rolagem lateral no celular"
    for path in ("/orcamento", "/metas", "/analises", "/investimentos", "/historico", "/fixas", "/dados", "/seguranca"):
        page.goto(BASE + path)
        idle(page, 300)
        wide = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert wide <= 0, f"{path}: {wide}px de rolagem lateral"
    ctx.close()


STATE = {}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=None if BROWSER == "chromium" else BROWSER, headless="--ver" not in sys.argv
        )
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True, locale="pt-BR")
        page = ctx.new_page()
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on(
            "response",
            lambda r: r.status >= 400 and "/api/" in r.url and not r.url.endswith("/auth/me") and http_errors.append(f"{r.status} {r.request.method} {r.url}"),
        )

        months = [months_back(n) for n in range(8, -1, -1)]
        login(page)
        empty_state(page)
        banner_later(page)
        limits(page)
        first_month(page, months[0])
        history(page, months)
        current_month(page, months)
        installments(page, months)
        undo_delete(page, months[-1])
        edit_expense(page, months[-1])
        investments(page)
        goals(page)
        consultant(page, months)
        dashboard(page, months)
        other_tabs(page, months)
        chart_interaction(page)
        builder(page)
        saved_analyses(page)
        version(page)
        history_report(page, months)
        exports(page)
        import_ofx(page)
        two_factor(page)
        banner_never(page)
        STATE["state"] = ctx.storage_state()
        mobile(browser)
        mobile_sections(browser)
        browser.close()

    summary = {
        "persona": "Carla, 34, BH, salário R$ 3.200 → 3.350",
        "months": months,
        "passed": sum(r["ok"] for r in results),
        "failed": sum(not r["ok"] for r in results),
        "results": results,
        "console_errors": console_errors,
        "http_errors": http_errors,
    }
    (OUT / "resultado.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{summary['passed']} ok, {summary['failed']} falhas; erros de console: {len(console_errors)}; HTTP: {len(http_errors)}")
    for e in console_errors[:10]:
        print("console:", e[:200])
    for e in http_errors[:20]:
        print("http:", e)


if __name__ == "__main__":
    main()
    sys.exit(1 if any(not r["ok"] for r in results) else 0)
