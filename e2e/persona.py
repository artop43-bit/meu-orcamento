"""QA da persona: usa o Meu Orçamento pela interface, como uma pessoa de verdade (Playwright).

Roda no CI a cada PR e localmente:
    uv run --with playwright --with pyotp python e2e/persona.py
Variáveis: QA_BASE_URL (padrão http://localhost:5173), QA_CREDENTIALS (arquivo com e-mail e
senha gerado por `python -m app.cli seed-demo --credentials-file`), QA_OUT (pasta dos prints),
QA_BROWSER (chromium ou msedge). Precisa de uma conta de demonstração VAZIA.

Persona: Carla, 34 anos, assistente administrativa em Belo Horizonte.
Salário líquido de R$ 3.200 (perto do rendimento médio do trabalho no Brasil, IBGE/PNAD),
aluguel, contas da casa, transporte público, mercado e lazer moderado. Celular novo
parcelado, dentista parcelado, uma viagem que deixa um mês no vermelho, trabalhos de freelance
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


def br_date(iso: str) -> str:
    """AAAA-MM-DD → dd/mm/aaaa (os campos de data do app são digitados nesse formato)."""
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


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
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    expect(d).to_be_visible()
    d.get_by_label("Descrição").fill(desc)
    if kind == "installments":
        d.get_by_label("Parcelada").check()
        # Aqui o valor informado é o de cada parcela.
        d.get_by_label("Valor da parcela").check()
    elif kind in ("recurring", "recurring_quarterly"):
        d.get_by_label("Recorrente").check()
        if kind == "recurring_quarterly":
            d.get_by_label("Frequência").select_option(label="A cada 3 meses")
    d.get_by_role("textbox", name=re.compile(r"^Valor")).fill(money(amount))
    if day:
        d.get_by_placeholder("dd/mm/aaaa").first.fill(br_date(f"{month}-{day:02d}"))
    d.get_by_label("Categoria").select_option(label=cat)
    if parcelas:
        d.get_by_label("Número de parcelas").fill(str(parcelas))
    d.get_by_role("button", name="Adicionar despesa").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page, 50)


def add_income(page: Page, desc: str, amount: float, every_month: bool = False):
    page.get_by_role("button", name="Nova receita", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill(desc)
    d.get_by_label("Valor", exact=True).fill(money(amount))
    if every_month:
        d.get_by_label("Todo mês", exact=True).check()
    d.get_by_role("button", name="Adicionar receita").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page, 50)


def pay_all(page: Page, month: str | None = None):
    """Marca todas as contas da tela como pagas, confirmando cada clique.

    Num servidor lento, um clique pode cair enquanto a lista se atualiza: por isso cada
    marcação é conferida e, no fim, o total pendente é checado na API (com nova tentativa).
    """
    for attempt in range(3):
        boxes = page.locator(".ledger__row input[type=checkbox]:not(:checked)")
        for _ in range(40):
            if boxes.count() == 0:
                break
            label = boxes.first.get_attribute("aria-label")
            boxes.first.click()
            try:
                expect(page.locator(f'input[aria-label="{label}"]').first).to_be_checked(timeout=5000)
            except AssertionError:
                pass  # conferido de novo abaixo
            idle(page, 120)
        if month is None:
            return
        pending = api(page, f"/months/{month}")["summary"]["pending_total"]
        if pending in ("0.00", "0"):
            return
        page.reload()
        idle(page, 300)
    raise AssertionError(f"{month}: contas não ficaram pagas (pendente {pending})")


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


@step("Conta nova: configuração inicial guiada aparece e todas as etapas podem ser puladas")
def onboarding(page: Page):
    d = dialog(page)
    expect(d).to_contain_text("Configuração inicial")
    page.screenshot(path=OUT / "v08-configuracao-inicial.png")
    d.get_by_role("button", name="Começar").click()
    for _ in range(4):
        expect(d.get_by_role("list", name="Etapas")).to_be_visible()
        d.get_by_role("button", name="Pular etapa").click()
    expect(d).to_contain_text("Configuração concluída")
    d.get_by_role("button", name="Ir para o orçamento").click()
    expect(page.locator("dialog[open]")).to_have_count(0)
    idle(page, 400)
    assert api(page, "/auth/me")["onboarded_at"], "configuração inicial não ficou registrada"
    page.reload()
    idle(page, 400)
    expect(page.locator("dialog[open]")).to_have_count(0)


@step("Conta nova: orçamento vazio mostra orientação")
def empty_state(page: Page):
    expect(page.get_by_role("heading", name="Nenhuma despesa no mês")).to_be_visible()
    page.goto(f"{BASE}/analises")
    idle(page)
    expect(page.get_by_role("heading", name="Sem lançamentos no período")).to_be_visible()
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
        add_income(page, "Freelance (planilhas)", 400)
    if index == 4:
        add_expense(page, month, "Dentista (canal)", 200, "Saúde", 15, kind="installments", parcelas=3)
    if index == 6:
        add_income(page, "Freelance (site)", 450)
    if not current:
        pay_all(page, month)


@step("Lançar 8 meses completos (variáveis, parcelas, freelance) e marcar tudo como pago")
def history(page: Page, months: list[str]):
    for index, month in enumerate(months[:-1]):
        fill_month(page, index, month, current=False)
        summary = api(page, f"/months/{month}")["summary"]
        assert summary["pending_total"] in ("0.00", "0"), f"{month}: pendente {summary['pending_total']}"


@step("Mês atual: aumento de salário em Recorrências (R$ 3.350) e gastos até hoje")
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


@step("Excluir com Desfazer: some na hora, volta ao desfazer, sai de vez depois e vale mesmo recarregando")
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
    # Excluir e recarregar (ou fechar) antes do fim do prazo do Desfazer: a exclusão tem de valer.
    add_expense(page, month, "Excluir e recarregar", 7.77, "Outros", 4)
    page.locator(".ledger__row", has_text="Excluir e recarregar").get_by_role("button", name="Excluir Excluir e recarregar").click()
    page.wait_for_timeout(800)
    page.reload()
    idle(page, 1500)
    data = api(page, f"/months/{month}")
    assert not any(e["description"] == "Excluir e recarregar" for e in data["expenses"]), "voltou depois de recarregar"


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


@step("Comprovante: anexar foto na despesa, ver no lançamento e remover")
def receipts(page: Page, month: str):
    open_month(page, month)
    page.locator(".ledger__row", has_text="Mercado").locator(".ledger__open").click()
    d = dialog(page)
    d.get_by_test_id("receipt-input").set_input_files(
        {"name": "nota.png", "mimeType": "image/png", "buffer": png_bytes(200, 300, (240, 240, 230))}
    )
    expect(d.get_by_role("img", name="Comprovante 1")).to_be_visible()
    page.keyboard.press("Escape")
    expect(d).to_have_count(0)
    idle(page)
    expense = next(e for e in api(page, f"/months/{month}")["expenses"] if e["description"] == "Mercado")
    assert len(expense["receipt_ids"]) == 1, expense
    expect(page.locator(".ledger__row", has_text="Mercado").get_by_text("comprovante")).to_be_visible()
    status = page.evaluate(
        "async (id) => (await fetch(`/api/files/${id}`, {credentials: 'omit', cache: 'no-store'})).status", expense["receipt_ids"][0]
    )
    assert status in (401, 403, 404), f"comprovante aberto sem sessão ({status})"
    page.locator(".ledger__row", has_text="Mercado").locator(".ledger__open").click()
    d = dialog(page)
    d.get_by_role("button", name="Remover comprovante 1").click()
    expect(d.get_by_role("img", name="Comprovante 1")).to_have_count(0)
    page.keyboard.press("Escape")
    idle(page)
    expense = next(e for e in api(page, f"/months/{month}")["expenses"] if e["description"] == "Mercado")
    assert expense["receipt_ids"] == [], expense


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
            d.get_by_label("Compõe a reserva de emergência").check()
        d.get_by_role("button", name="Adicionar").click()
        expect(d).to_have_count(0)
        idle(page)
    assert len(api(page, "/investments")) == 2


@step("Metas: objetivo de viagem com motivação, imagem, prazo, projeção e primeiro depósito")
def goals(page: Page):
    page.goto(f"{BASE}/metas")
    idle(page)
    expect(page.get_by_role("heading", name="Nenhuma meta cadastrada")).to_be_visible()
    page.get_by_role("button", name="Nova meta").first.click()
    d = dialog(page)
    d.locator(".goal-kind", has_text="Viagem").click()
    expect(d.get_by_label("Viagem", exact=True)).to_be_checked()
    d.get_by_label("Nome da meta").fill("Viagem para o Nordeste")
    d.get_by_label(re.compile("^Motivação")).fill("Conhecer Salvador com a família")
    d.get_by_label("Escolher imagem do objetivo").set_input_files(
        {"name": "praia.png", "mimeType": "image/png", "buffer": png_bytes(320, 180, (40, 140, 200))}
    )
    expect(d.get_by_role("img", name="Imagem do objetivo")).to_be_visible()
    d.get_by_role("button", name="Continuar").click()
    d.get_by_label("Valor total").fill(money(4000))
    d.get_by_label("Tenho uma data").check()
    target = f"{TODAY.year + 1}-07-01"
    d.get_by_label("Data desejada").fill(br_date(target))
    expect(d.locator(".summary-box")).to_contain_text("por mês")
    page.screenshot(path=OUT / "v08-meta-form.png")
    d.get_by_role("button", name="Criar meta").click()
    expect(d).to_have_count(0)
    idle(page)
    card = page.locator(".goal-card", has_text="Viagem para o Nordeste")
    expect(card.locator(".goal-card__motivation")).to_contain_text("Salvador")
    assert image_loaded(page, ".goal-card__image"), "imagem da meta não carregou"
    page.get_by_label("Valor a guardar ou retirar da meta").fill(money(600))
    page.get_by_role("button", name="Guardar").click()
    idle(page)
    goal = api(page, "/goals")[0]
    assert goal["current_amount"].startswith("600"), goal
    assert goal["is_main"] and goal["kind"] == "travel", goal
    assert goal["projection"]["status"] in ("on_track", "ahead", "behind", "estimate"), goal["projection"]
    expect(card.locator(".goal-status")).to_be_visible()
    page.screenshot(path=OUT / "v08-metas.png", full_page=True)
    # Imagem da meta é só do dono: sem sessão, o arquivo não abre.
    status = page.evaluate(
        "async (id) => (await fetch(`/api/files/${id}`, {credentials: 'omit', cache: 'no-store'})).status", goal["image_id"]
    )
    assert status in (401, 403, 404), f"imagem da meta aberta sem sessão ({status})"


@step("Orçamento: quadro da meta principal com projeção e sugestão de aporte")
def goal_teaser(page: Page, month: str):
    open_month(page, month)
    teaser = page.locator(".goal-teaser")
    expect(teaser).to_contain_text("Viagem para o Nordeste")
    expect(teaser.locator(".goal-status")).to_be_visible()
    tip = api(page, "/goals/suggestion")
    region = teaser.get_by_role("region", name="Sugestão de aporte")
    if tip:
        expect(region).to_be_visible()
        region.get_by_role("button", name="Agora não").click()
        expect(region).to_have_count(0)
        page.reload()
        idle(page)
        expect(page.locator(".goal-teaser").get_by_role("region", name="Sugestão de aporte")).to_have_count(0)
    else:
        expect(region).to_have_count(0)


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
    assert "Limite de Lazer excedido" in titles, titles
    # Compras lançadas com data passada já entram pagas; ficam em atraso só as não pagas de propósito.
    # Ficam sem pagar de propósito: parcela do celular (dia 12), internet (15) e plano de celular (20).
    overdue = sum(1 for day in (12, 15, 20) if day < TODAY.day)
    if overdue:
        assert f"{overdue} despesa(s) em atraso" in titles, titles
    else:
        assert not any("atraso" in t for t in titles), titles
    messages = [m["title"] for m in current["messages"]]
    assert "Reserva abaixo da referência" in messages, messages
    # Sobra do mês (~R$ 900) cobre os ~R$ 378/mês da meta: não deve haver alerta de ritmo.
    assert not any("Viagem" in t for t in titles), titles


@step("Insights: seções com navegação e conteúdo (desktop)")
def dashboard(page: Page, months: list[str]):
    page.goto(f"{BASE}/analises")
    idle(page, 600)
    expect(page.get_by_role("heading", name="Insights", level=1)).to_be_visible()
    nav = page.get_by_role("navigation", name="Seções da análise")
    expect(page.get_by_text("Insights do mês", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile("^Alertas"))).to_be_visible()
    page.screenshot(path=OUT / "resumo-desktop.png", full_page=True)
    checks = {
        "Tendências": "Receitas × despesas",
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
    page.get_by_label("Mês", exact=True).fill(f"{months[5][5:]}/{months[5][:4]}")
    idle(page, 600)
    expect(page.get_by_role("heading", name="Resultado negativo no mês")).to_be_visible()


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
    expect(page.locator(".chart2__tip").first).to_contain_text("Receitas")
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
    panel.get_by_text("Receitas", exact=True).click()
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
    expect(d.get_by_label("Fixar no Resumo de Insights")).to_be_checked()
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


def month_plus(month: str, count: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:]) - 1 + count
    return f"{index // 12}-{index % 12 + 1:02d}"


@step("v0.5: renda variável, sugestão de categoria, parcela pelo total, frequência e 'este e os próximos'")
def flexible_entries(page: Page, months: list[str]):
    month = months[-1]
    open_month(page, month)
    # Renda variável, agrupada à parte.
    page.get_by_role("button", name="Nova receita", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Freelance (logo)")
    d.get_by_label("Variável").check()
    d.get_by_label("Valor no mês").fill(money(380))
    d.get_by_label("Dia do recebimento").fill("25")
    d.get_by_role("button", name="Adicionar receita").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    income = next(i for i in api(page, f"/months/{month}")["incomes"] if i["description"] == "Freelance (logo)")
    assert (income["income_type"], income["day"]) == ("variable", 25), income
    expect(page.get_by_text("Variáveis", exact=True)).to_be_visible()

    # Categoria sugerida pelo nome; forma de pagamento; "Salvar e adicionar outro".
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Uber para o trabalho")
    expect(d.locator(".suggest-chip")).to_contain_text("Transporte", timeout=6000)
    assert d.get_by_label("Categoria").evaluate("e => e.options[e.selectedIndex].text") == "Transporte"
    d.get_by_role("textbox", name="Valor", exact=True).fill(money(23.50))
    d.get_by_label("Pix").check()
    d.get_by_role("button", name="Salvar e adicionar outro").click()
    expect(d.get_by_text("1 despesa(s) salva(s)")).to_be_visible(timeout=8000)
    expect(d.get_by_label("Descrição")).to_have_value("")
    # Parcelada informando o total: 3x de R$ 1.000.
    d.get_by_label("Descrição").fill("Geladeira")
    d.get_by_label("Parcelada").check()
    d.get_by_label("Número de parcelas").fill("3")
    # O padrão da parcelada é o total da compra.
    d.get_by_label("Valor total da compra").fill(money(3000))
    expect(d.locator(".summary-box")).to_contain_text("3x de R$")
    d.get_by_label("Categoria").select_option(label="Moradia")
    d.get_by_role("button", name="Adicionar despesa").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    uber = next(e for e in api(page, f"/months/{month}")["expenses"] if e["description"] == "Uber para o trabalho")
    assert uber["payment_method"] == "pix", uber
    parcels = [
        e["amount"]
        for m in (month, month_plus(month, 1), month_plus(month, 2))
        for e in api(page, f"/months/{m}")["expenses"]
        if e["description"] == "Geladeira"
    ]
    assert [p.split(".")[0] for p in parcels] == ["1000"] * 3, parcels

    # Conta a cada 3 meses (IPTU).
    add_expense(page, month, "IPTU", 120, "Moradia", 10, kind="recurring_quarterly")
    names = lambda m: [e["description"] for e in api(page, f"/months/{m}")["expenses"]]  # noqa: E731
    assert "IPTU" in names(month)
    assert "IPTU" not in names(month_plus(month, 1))
    assert "IPTU" in names(month_plus(month, 3))

    # Editar "este e os próximos": a internet sobe a partir deste mês.
    open_month(page, month)
    page.locator(".ledger__row", has_text="Internet").locator(".ledger__open").click()
    d = dialog(page)
    d.get_by_role("textbox", name="Valor", exact=True).fill(money(109.90))
    d.get_by_label("Este mês e os seguintes").check()
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    internet = lambda m: next(e for e in api(page, f"/months/{m}")["expenses"] if e["description"] == "Internet")["amount"]  # noqa: E731
    assert internet(month).startswith("109.9"), internet(month)
    assert internet(month_plus(month, 2)).startswith("109.9")
    assert internet(months[-2]).startswith("99.9"), "mês passado não pode mudar"

    # Busca e filtro na lista.
    open_month(page, month)
    page.get_by_placeholder("Buscar no mês").fill("geladeira")
    expect(page.locator(".ledger__row")).to_have_count(1)
    page.get_by_role("button", name="Limpar filtros").click()
    page.screenshot(path=OUT / "v05-orcamento.png", full_page=True)


@step("Calendário: despesa prevista entra na projeção e é confirmada com um toque")
def calendar(page: Page):
    page.goto(f"{BASE}/calendario")
    idle(page)
    expect(page.locator("h1")).to_be_visible()
    page.get_by_role("button", name="Agendar despesa prevista").first.click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Presente da Júlia")
    d.get_by_label("Valor previsto").fill(money(150))
    day = min(TODAY.day + 2, 28)
    d.get_by_label("Data", exact=True).fill(br_date(f"{CURRENT}-{day:02d}"))
    d.get_by_role("button", name=re.compile("Agendar")).last.click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    planned = api(page, f"/planned?month={CURRENT}")
    assert [p["description"] for p in planned] == ["Presente da Júlia"], planned
    projection = api(page, f"/analysis/projection?start={CURRENT}&months=1")[0]
    assert float(projection["planned"]) >= 150, projection
    page.screenshot(path=OUT / "v05-calendario.png", full_page=True)
    page.locator(".ev-btn:visible", has_text="Presente da Júlia").first.click()
    d = dialog(page)
    d.get_by_role("button", name="Lançar já paga").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    expense = next(e for e in api(page, f"/months/{CURRENT}")["expenses"] if e["description"] == "Presente da Júlia")
    assert expense["paid"] is True and expense["due_date"] == f"{CURRENT}-{day:02d}", expense
    assert api(page, f"/planned?month={CURRENT}")[0]["expense_id"] == expense["id"]


@step("Investimentos → Cotações: aviso fixo, abas e simulador; Central de ajuda e apresentação")
def market_and_help(page: Page):
    page.goto(f"{BASE}/investimentos?secao=cotacoes")
    idle(page, 500)
    expect(page.get_by_role("link", name="Cotações")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("note").filter(has_text="não é recomendação")).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile("Simulador de renda fixa"))).to_be_visible()
    page.screenshot(path=OUT / "v07-cotacoes.png", full_page=True)
    page.goto(f"{BASE}/ajustes/ajuda")
    idle(page)
    expect(page.get_by_role("heading", name="Calendário")).to_be_visible()
    page.get_by_role("button", name="Ver apresentação").click()
    d = dialog(page)
    expect(d).to_contain_text("Apresentação")
    d.get_by_role("button", name="Próximo").click()
    expect(d).to_contain_text("Orçamento")
    d.get_by_role("button", name="Pular").click()
    expect(d).to_have_count(0)


@step("v0.6: lançar numa frase (campo rápido e Ctrl+K), lote, vencidas e quanto posso gastar")
def quick_and_bulk(page: Page):
    open_month(page, CURRENT)
    page.get_by_placeholder(re.compile("mercado 120")).fill("padaria 18,50 pix hoje")
    page.get_by_role("button", name="Lançar", exact=True).click()
    expect(page.locator(".toast")).to_contain_text("Padaria", timeout=8000)
    idle(page)
    padaria = next(e for e in api(page, f"/months/{CURRENT}")["expenses"] if e["description"] == "Padaria")
    assert (padaria["amount"], padaria["payment_method"], padaria["paid"]) == ("18.50", "pix", True), padaria
    # Ctrl+K: frase com renda.
    page.keyboard.press("Control+k")
    d = dialog(page)
    d.get_by_role("combobox").fill("+ consultoria avulsa 150")
    expect(d.get_by_role("option").first).to_contain_text("Lançar receita")
    page.keyboard.press("Enter")
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    extra = next(i for i in api(page, f"/months/{CURRENT}")["incomes"] if i["description"].startswith("Consultoria"))
    assert (extra["amount"], extra["income_type"]) == ("150.00", "variable"), extra
    # Ctrl+Z desfaz o último lançamento rápido.
    page.keyboard.press("Control+z")
    page.wait_for_timeout(800)
    assert not any(i["description"].startswith("Consultoria") for i in api(page, f"/months/{CURRENT}")["incomes"])

    # Disponível hoje.
    expect(page.get_by_text("Disponível hoje", exact=True)).to_be_visible()

    # Lote: seleciona 2 contas e muda a categoria.
    page.get_by_role("button", name="Selecionar", exact=True).click()
    page.get_by_role("checkbox", name="Selecionar Padaria").check()
    page.get_by_role("checkbox", name=re.compile("^Selecionar Uber para o trabalho")).check()
    page.get_by_label("Nova categoria").select_option(label="Lazer")
    page.get_by_role("button", name="Aplicar").click()
    idle(page)
    lazer = next(c["id"] for c in api(page, "/categories") if c["name"] == "Lazer")
    cats = {e["description"]: e["category_id"] for e in api(page, f"/months/{CURRENT}")["expenses"]}
    assert cats["Padaria"] == lazer and cats["Uber para o trabalho"] == lazer, cats

    # Vencidas: marcar todas como pagas (a internet ficou em atraso de propósito).
    bar = page.get_by_role("button", name="Marcar todas como pagas")
    if bar.count():
        bar.click()
        idle(page)
        today = TODAY.isoformat()
        late = [e for e in api(page, f"/months/{CURRENT}")["expenses"] if not e["paid"] and e["due_date"] and e["due_date"] < today]
        assert late == [], late
    page.screenshot(path=OUT / "v06-orcamento.png", full_page=True)


@step("v0.6: cartão de crédito — compra cai na fatura certa e a fatura é paga")
def credit_card(page: Page):
    page.goto(f"{BASE}/cartoes")
    idle(page)
    page.get_by_role("button", name="Novo cartão").first.click()
    d = dialog(page)
    d.get_by_label("Nome do cartão").fill("Roxinho")
    d.get_by_label("Limite (opcional)").fill(money(2500))
    d.get_by_label("Dia do fechamento").fill("3")
    d.get_by_label("Dia do vencimento").fill("10")
    d.get_by_role("button", name="Adicionar cartão").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    [card] = api(page, "/cards")
    assert card["best_day"] == 3

    open_month(page, CURRENT)
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Tênis de corrida")
    d.get_by_label("Parcelada").check()
    d.get_by_label("Número de parcelas").fill("2")
    d.get_by_label("Valor total da compra").fill(money(400))
    d.get_by_label("Crédito").check()
    expect(d.get_by_role("combobox", name=re.compile("^Cartão"))).to_have_value(card["card"]["id"])
    purchase = f"{CURRENT}-05"
    d.get_by_label("Data da compra").fill(br_date(purchase))
    expect(d.get_by_text(re.compile("Fatura de .*, vencimento em"))).to_be_visible()
    d.get_by_role("button", name="Adicionar despesa").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    invoices = {i["month"]: i for i in api(page, f"/cards/{card['card']['id']}/invoices")}
    # Compra no dia 5 (depois do fechamento dia 3): 1ª parcela na fatura que vence no mês seguinte.
    first = month_plus(CURRENT, 1)
    assert invoices[first]["total"] == "200.00", invoices[first]
    assert invoices[month_plus(CURRENT, 2)]["total"] == "200.00"

    page.goto(f"{BASE}/cartoes")
    idle(page)
    page.locator(".invoice-chip").first.click()
    d = dialog(page)
    d.get_by_role("button", name="Marcar fatura como paga").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    assert api(page, f"/cards/{card['card']['id']}/invoices/{first}")[0]["paid"] is True
    page.screenshot(path=OUT / "v06-cartoes.png", full_page=True)


@step("v0.6: regra de categoria, assinaturas, privacidade e preferências")
def rules_privacy_feedback(page: Page):
    page.goto(f"{BASE}/categorias")
    idle(page)
    page.get_by_label("Texto da regra").fill("cinema")
    page.get_by_label("Categoria da regra").select_option(label="Lazer")
    page.get_by_role("button", name="Criar regra").click()
    idle(page)
    assert [r["pattern"] for r in api(page, "/rules")] == ["cinema"]
    found = api(page, "/suggest/category?description=Cinema%20com%20a%20Ju")
    assert (found["name"], found["source"]) == ("Lazer", "rule"), found

    page.goto(f"{BASE}/fixas")
    idle(page)
    expect(page.get_by_role("heading", name=re.compile("Assinaturas e recorrências"))).to_be_visible()

    open_month(page, CURRENT)
    page.locator("body").press("p")
    expect(page.locator(".kpi").first).to_contain_text("R$ ••••")
    page.locator("body").press("p")
    expect(page.locator(".kpi").first).not_to_contain_text("R$ ••••")

    page.goto(f"{BASE}/preferencias")
    idle(page)
    page.get_by_label("Escuro").check()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.get_by_label("Automático (sistema)").check()



# ---------------------------------------------------------------- v0.7.5


def png_bytes(width: int = 32, height: int = 24, rgb: tuple[int, int, int] = (31, 122, 98)) -> bytes:
    """PNG de verdade, gerado sem bibliotecas (o e2e não depende de Pillow)."""
    import struct
    import zlib

    row = b"\x00" + bytes(rgb) * width
    raw = row * height

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def image_loaded(page: Page, selector: str, timeout: int = 10000) -> bool:
    """Espera a imagem terminar de baixar (as miniaturas carregam sob demanda)."""
    try:
        page.locator(selector).first.scroll_into_view_if_needed()
        page.wait_for_function(
            "sel => { const img = document.querySelector(sel); return !!img && img.complete && img.naturalWidth > 0; }",
            arg=selector,
            timeout=timeout,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


@step("v0.7.5: solicitação com print, resposta da administração e aviso de resposta nova")
def support_requests(page: Page):
    open_month(page, CURRENT)
    page.keyboard.press("Control+k")
    d = dialog(page)
    d.get_by_role("combobox").fill("solicitação")
    page.keyboard.press("Enter")
    d = page.locator("dialog[open]", has_text="Nova solicitação")
    d.get_by_label("Problema").check()
    d.get_by_label("Assunto").fill("Gráfico de Insights não carrega")
    d.get_by_label("Mensagem").fill("Ao abrir Insights › Tendências o gráfico fica em branco. Segue o print.")
    d.locator("[data-testid=image-input]").set_input_files(
        [{"name": "print.png", "mimeType": "image/png", "buffer": png_bytes(320, 200)}]
    )
    expect(d.get_by_role("img", name="Prévia: print.png")).to_be_visible()
    d.get_by_role("button", name="Enviar solicitação").click()
    expect(d).to_contain_text("Solicitação enviada", timeout=8000)
    d.get_by_role("button", name="Acompanhar solicitação").click()
    page.wait_for_url("**/ajustes/solicitacoes/**")
    idle(page)
    expect(page.get_by_role("heading", name="Gráfico de Insights não carrega")).to_be_visible()
    expect(page.get_by_role("img", name="Imagem anexada 1")).to_be_visible()
    assert image_loaded(page, ".attachments img"), "a imagem enviada não abriu"
    [thread] = api(page, "/support/threads")
    assert (thread["status"], thread["kind"]) == ("open", "bug"), thread

    # Administração: aba Solicitações, abre a conversa e responde.
    page.goto(f"{BASE}/admin?aba=solicitacoes")
    idle(page)
    page.get_by_role("button", name=re.compile("Gráfico de Insights não carrega")).click()
    idle(page)
    expect(page.get_by_role("heading", name="Gráfico de Insights não carrega")).to_be_visible()
    page.get_by_label("Mensagem", exact=True).fill("Corrigido na próxima versão. Obrigado pelo print.")
    page.get_by_role("button", name="Enviar mensagem").click()
    expect(page.locator(".bubble--mine")).to_contain_text("Corrigido na próxima versão", timeout=8000)
    expect(page.get_by_label("Status")).to_have_value("answered")
    # Visões: por usuário e por status.
    page.get_by_role("tab", name="Por status").click()
    idle(page)
    expect(page.get_by_role("button", name=re.compile(r"Respondida \(1\)"))).to_be_visible()
    page.get_by_role("tab", name="Por usuário").click()
    idle(page)
    expect(page.locator(".thread-list__item").first).to_contain_text("1 solicitação(ões)")
    page.get_by_role("tab", name="Recentes").click()
    page.get_by_placeholder("Buscar por assunto, mensagem ou e-mail").fill("print")
    page.wait_for_timeout(700)
    expect(page.locator(".thread-list__item")).to_have_count(1)
    page.screenshot(path=OUT / "v075-admin-solicitacoes.png", full_page=True)

    # Usuário: aviso de resposta nova em Ajustes; ao abrir, fica lida.
    assert api(page, "/support/unread")["unread"] == 1
    page.goto(f"{BASE}/ajustes")
    idle(page)
    expect(page.get_by_text("1 resposta(s) nova(s)")).to_be_visible()
    page.locator(".settings-list").get_by_role("link", name=re.compile("Minhas solicitações")).click()
    idle(page)
    page.get_by_role("link", name=re.compile("Gráfico de Insights não carrega")).click()
    idle(page)
    expect(page.locator(".bubble--other")).to_contain_text("Corrigido na próxima versão")
    assert api(page, "/support/unread")["unread"] == 0
    page.screenshot(path=OUT / "v075-minhas-solicitacoes.png", full_page=True)


@step("v0.7.5: perfil com foto, dados opcionais, resumo e retrospectiva com imagem para baixar")
def profile(page: Page):
    page.goto(f"{BASE}/ajustes/perfil")
    idle(page)
    page.get_by_role("button", name="Adicionar foto").click()
    d = dialog(page)
    d.locator("[data-testid=avatar-input]").set_input_files(
        [{"name": "foto.png", "mimeType": "image/png", "buffer": png_bytes(600, 400, (200, 80, 60))}]
    )
    expect(d.get_by_label("Zoom")).to_be_visible()
    d.get_by_label("Zoom").fill("1.4")
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    assert api(page, "/profile")["avatar_id"], "a foto não foi salva"
    assert image_loaded(page, ".profile-hero__avatar img"), "a foto não aparece no perfil"

    page.get_by_role("button", name="Editar perfil").click()
    d = dialog(page)
    d.get_by_label("Nome de exibição").fill("Carla Souza")
    d.get_by_label("Cidade").fill("Belo Horizonte")
    d.get_by_label("Profissão").fill("Assistente administrativa")
    d.get_by_label("Média de receitas").uncheck()
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    expect(page.get_by_role("heading", name="Carla Souza")).to_be_visible()
    expect(page.locator(".profile-stats")).not_to_contain_text("Média de receitas")
    expect(page.locator(".profile-stats")).to_contain_text("Taxa de poupança")
    expect(page.locator(".sidebar__profile")).to_contain_text("Carla Souza")

    page.get_by_role("button", name="Ver retrospectiva").click()
    story = page.locator("dialog.story[open]")
    expect(story).to_be_visible(timeout=8000)
    expect(story).to_contain_text("Retrospectiva")
    for _ in range(12):
        page.keyboard.press("ArrowRight")
    with page.expect_download() as download:
        story.get_by_role("button", name="Baixar feed (1:1)").click()
    file = download.value
    assert file.suggested_filename.endswith("-feed.png"), file.suggested_filename
    path = OUT / "v075-retrospectiva-feed.png"
    file.save_as(path)
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and path.stat().st_size > 5000
    page.keyboard.press("Escape")
    expect(story).to_have_count(0)
    page.screenshot(path=OUT / "v075-perfil.png", full_page=True)


@step("v0.7.5: cartão de débito (sem limite e sem fatura) e crédito sem a opção 'Sem cartão'")
def debit_card(page: Page):
    page.goto(f"{BASE}/cartoes")
    idle(page)
    page.get_by_role("button", name="Novo cartão").first.click()
    d = dialog(page)
    d.get_by_label("Nome do cartão").fill("Débito Inter")
    d.get_by_label("Débito", exact=True).check()
    expect(d.get_by_text("Dia do fechamento")).to_have_count(0)
    d.get_by_role("button", name="Adicionar cartão").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    cards = {c["card"]["name"]: c for c in api(page, "/cards")}
    debit = cards["Débito Inter"]
    assert debit["card"]["kind"] == "debit" and debit["open_invoice"] is None, debit
    used_before = {name: c["used"] for name, c in cards.items()}

    open_month(page, CURRENT)
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Farmácia Araujo")
    d.get_by_role("textbox", name="Valor", exact=True).fill(money(35.90))
    d.get_by_label("Débito").check()
    expect(d.get_by_label("Cartão de débito")).to_have_value(debit["card"]["id"])
    d.get_by_role("button", name="Adicionar despesa").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    bought = next(e for e in api(page, f"/months/{CURRENT}")["expenses"] if e["description"] == "Farmácia Araujo")
    assert bought["paid"] is True and bought["debit_card_id"] == debit["card"]["id"] and bought["card_id"] is None, bought
    used_after = {c["card"]["name"]: c["used"] for c in api(page, "/cards")}
    assert used_after == used_before, (used_before, used_after)

    # Crédito: só os cartões de crédito, sem a opção vazia.
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    d.get_by_label("Crédito").check()
    options = d.get_by_label("Cartão de crédito").locator("option").all_inner_texts()
    assert options and not any("Sem cartão" in o for o in options) and "Débito Inter" not in options, options
    page.keyboard.press("Escape")


@step("v0.7.5: data que não existe, dia 31 de fevereiro e campo obrigatório bloqueiam o salvar")
def validation(page: Page):
    open_month(page, CURRENT)
    page.get_by_role("button", name="Nova despesa", exact=True).click()
    d = dialog(page)
    # Campo obrigatório vazio: mensagem do app junto do campo (sem balão do navegador).
    d.get_by_role("button", name="Adicionar despesa").click()
    expect(d.locator(".field-error").first).to_contain_text("Preencha o campo")
    d.get_by_label("Descrição").fill("Teste de data")
    d.get_by_role("textbox", name="Valor", exact=True).fill(money(10))
    d.get_by_placeholder("dd/mm/aaaa").first.fill("30/02/2027")
    expect(d.get_by_text("Fevereiro de 2027 tem 28 dias.")).to_be_visible()
    d.get_by_role("button", name="Adicionar despesa").click()
    page.wait_for_timeout(600)
    expect(d).to_be_visible()
    assert not any(e["description"] == "Teste de data" for e in api(page, f"/months/{CURRENT}")["expenses"])
    page.keyboard.press("Escape")

    page.goto(f"{BASE}/orcamento/2027-02")
    idle(page)
    page.get_by_role("button", name="Nova receita", exact=True).click()
    d = dialog(page)
    d.get_by_label("Descrição").fill("Bônus")
    d.get_by_label("Valor", exact=True).fill(money(100))
    d.get_by_label("Dia do recebimento").fill("31")
    expect(d.get_by_text("Fevereiro de 2027 tem 28 dias. Use um dia entre 1 e 28.")).to_be_visible()
    d.get_by_role("button", name="Adicionar receita").click()
    page.wait_for_timeout(600)
    expect(d).to_be_visible()
    assert not any(i["description"] == "Bônus" for i in api(page, "/months/2027-02")["incomes"])
    # Que se repete: 31 vale (nos meses curtos cai no último dia).
    d.get_by_label("Todo mês", exact=True).check()
    expect(d.get_by_text("Em meses mais curtos, cai no último dia do mês.")).to_be_visible()
    page.keyboard.press("Escape")


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
    assert page.url.endswith("/calendario"), page.url
    # O gesto vale também na parte de baixo da tela.
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


@step("Exportar: recorte com contagem ao vivo, Excel, CSV, relatório anual e backup")
def exports(page: Page):
    page.goto(f"{BASE}/ajustes/dados?aba=exportar")
    idle(page, 500)
    counter = page.locator("[aria-live]", has_text="no recorte")
    expect(counter).to_contain_text(re.compile(r"\d+ lançamento"))
    page.get_by_role("button", name="12 meses").click()
    idle(page, 400)
    total = int(re.search(r"(\d+) lançamento", counter.inner_text())[1])
    page.get_by_label("Só despesas").check()
    idle(page, 400)
    only = int(re.search(r"(\d+) lançamento", counter.inner_text())[1])
    assert 0 < only < total, (only, total)
    page.get_by_label("Receitas e despesas").check()
    idle(page, 300)
    page.screenshot(path=OUT / "v08-exportar.png", full_page=True)
    for name in ("Baixar Excel", "Baixar CSV", "Baixar backup"):
        with page.expect_download() as info:
            page.get_by_role("button", name=name).click()
        download = info.value
        path = OUT / download.suggested_filename
        download.save_as(path)
        assert path.stat().st_size > 200, f"{name} vazio"
    # O último download é o backup: precisa ser um JSON com os lançamentos da persona.
    backup = json.loads(path.read_text(encoding="utf-8"))
    assert backup and "expenses" in json.dumps(backup), "backup sem os lançamentos"
    page.get_by_role("link", name="Abrir resumo anual").click()
    page.wait_for_url("**/relatorio/ano/**")
    idle(page, 500)
    expect(page.get_by_role("heading", name=re.compile(r"Resumo anual de \d{4}"))).to_be_visible()
    page.screenshot(path=OUT / "v08-resumo-anual.png", full_page=True)


def import_file(page: Page, path: pathlib.Path):
    page.goto(f"{BASE}/ajustes/dados")
    idle(page)
    page.get_by_test_id("import-input").set_input_files(str(path))
    idle(page, 500)


@step("Importar: PDF recusado com orientação")
def import_pdf(page: Page):
    pdf = OUT / "extrato.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    import_file(page, pdf)
    expect(page.get_by_text(re.compile("PDF não é aceito: cada banco"))).to_be_visible()


@step("Importar planilha CSV: colunas identificadas, prévia, importa e desfaz o lote")
def import_csv(page: Page):
    csv_file = OUT / "planilha.csv"
    d = TODAY.strftime("%d/%m/%Y")
    csv_file.write_text(
        f"Data;Histórico;Valor\n{d};FARMACIA PAGUE MENOS;-48,90\n{d};UBER TRIP;-23,50\n{d};PIX RECEBIDO FREELA;350,00\n",
        encoding="utf-8",
    )
    import_file(page, csv_file)
    expect(page.get_by_role("list", name="Etapas da importação")).to_be_visible()
    expect(page.locator(".mapping-grid select").first).to_have_value("0")
    expect(page.locator("th.is-mapped").first).to_be_visible()
    page.screenshot(path=OUT / "v08-importar-colunas.png", full_page=True)
    page.get_by_role("button", name="Continuar").click()
    idle(page, 500)
    expect(page.get_by_text("FARMACIA PAGUE MENOS")).to_be_visible()
    page.screenshot(path=OUT / "v08-importar-previa.png", full_page=True)
    before = api(page, f"/months/{CURRENT}")
    page.get_by_role("button", name=re.compile(r"^Importar 3 lançamento")).click()
    idle(page, 600)
    expect(page.get_by_role("button", name="Desfazer esta importação")).to_be_visible()
    after = api(page, f"/months/{CURRENT}")
    assert len(after["expenses"]) == len(before["expenses"]) + 2, (len(before["expenses"]), len(after["expenses"]))
    assert len(after["incomes"]) == len(before["incomes"]) + 1
    page.get_by_role("button", name="Desfazer esta importação").click()
    idle(page, 600)
    expect(page.get_by_text(re.compile("Importação desfeita"))).to_be_visible()
    undone = api(page, f"/months/{CURRENT}")
    assert len(undone["expenses"]) == len(before["expenses"]), "desfazer não removeu as despesas"
    expect(page.get_by_role("heading", name="Importações recentes")).to_be_visible()


@step("Importar extrato OFX no mês atual (prévia, importa e marca repetidos)")
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
    before = len(api(page, f"/months/{CURRENT}")["expenses"])
    import_file(page, ofx)
    expect(page.get_by_text("PADARIA PAO QUENTE")).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Importar 2 lançamento")).click()
    idle(page, 600)
    after = len(api(page, f"/months/{CURRENT}")["expenses"])
    assert after == before + 2, (before, after)
    import_file(page, ofx)
    expect(page.get_by_text("já importado").first).to_be_visible()
    page.screenshot(path=OUT / "import-repetido.png", full_page=True)
    expect(page.get_by_role("button", name=re.compile(r"^Importar 0 lançamento"))).to_be_disabled()
    again = len(api(page, f"/months/{CURRENT}")["expenses"])
    assert again == after, "reimportar não pode duplicar sozinho"


@step("Avisos por e-mail: lembrete de vencimentos, antecedência e resumo do mês")
def email_notices(page: Page):
    page.goto(f"{BASE}/ajustes/preferencias")
    idle(page)
    expect(page.get_by_role("heading", name="Avisos por e-mail")).to_be_visible()
    page.get_by_label("7 dias").check()
    page.get_by_label("Ocultar valores nos e-mails").check()
    idle(page, 400)
    prefs = api(page, "/notifications/prefs")
    assert prefs["notify_due_days"] == 7 and prefs["notify_hide_values"] is True, prefs
    page.get_by_label(re.compile("^Lembrete de vencimentos")).uncheck()
    idle(page, 400)
    expect(page.get_by_label("7 dias")).to_have_count(0)
    assert api(page, "/notifications/prefs")["notify_due"] is False
    page.get_by_label(re.compile("^Lembrete de vencimentos")).check()
    page.get_by_label("Ocultar valores nos e-mails").uncheck()
    idle(page, 400)
    assert api(page, "/notifications/prefs")["notify_due"] is True


@step("Notas da versão em Ajustes, com atalho para enviar sugestão")
def release_notes(page: Page):
    page.goto(f"{BASE}/ajustes")
    idle(page)
    page.get_by_role("link", name=re.compile("Notas da versão")).click()
    page.wait_for_url("**/ajustes/notas")
    idle(page)
    current = page.locator(".release--current")
    expect(current).to_contain_text(re.compile(r"Versão \d+\.\d+\.\d+"))
    head = page.locator(".release__head").nth(1)
    head.click()
    expect(head).to_have_attribute("aria-expanded", "true")
    page.get_by_role("button", name="Enviar sugestão").first.click()
    d = dialog(page)
    expect(d).to_contain_text("Nova solicitação")
    expect(d).to_contain_text(re.compile(r"Referente a: Versão \d+\.\d+\.\d+"))
    page.keyboard.press("Escape")
    expect(d).to_have_count(0)


@step("v0.9: caixa de Mensagens com a resposta da solicitação e recado da administração")
def inbox_and_announcement(page: Page):
    # A resposta dada em Administração › Solicitações também chegou na caixa (já lida, pois a
    # conversa foi aberta).
    page.goto(f"{BASE}/mensagens")
    idle(page)
    reply = page.locator(".inbox-item", has_text="Gráfico de Insights não carrega")
    expect(reply).to_have_count(1)
    # Recado global: escreve, revisa e envia.
    page.goto(f"{BASE}/admin?aba=recados")
    idle(page)
    expect(page.get_by_text(re.compile(r"\d+ destinatário"))).to_be_visible()
    page.get_by_label("Título").fill("Manutenção programada")
    page.get_by_label("Mensagem", exact=True).fill("No sábado, às 22h, o app fica fora do ar por cerca de 10 minutos.")
    page.get_by_label(re.compile("^Importante")).check()
    page.get_by_role("button", name="Revisar e enviar").click()
    d = dialog(page)
    expect(d).to_contain_text("Manutenção programada")
    d.get_by_role("button", name=re.compile(r"^Enviar para \d+ usuário")).click()
    expect(d).to_have_count(0)
    expect(page.locator(".alert--success")).to_contain_text(re.compile(r"Recado enviado para \d+ usuário"))
    expect(page.locator(".item", has_text="Manutenção programada")).to_contain_text("lido por 0")
    page.screenshot(path=OUT / "v09-admin-recados.png", full_page=True)
    # Menu: contador de não lidas em Mensagens; o importante fica no topo.
    page.goto(f"{BASE}/orcamento")
    idle(page)
    expect(page.locator(".sidebar").get_by_role("link", name=re.compile("Mensagens")).locator(".nav-badge")).to_have_text("1")
    page.locator(".sidebar").get_by_role("link", name=re.compile("Mensagens")).click()
    page.wait_for_url("**/mensagens")
    idle(page)
    first = page.locator(".inbox-item").first
    expect(first).to_contain_text("Manutenção programada")
    expect(first).to_contain_text("Importante")
    assert api(page, "/inbox/unread")["unread"] == 1
    first.locator(".inbox-item__head").click()
    expect(first.locator(".inbox-item__text")).to_contain_text("sábado")
    idle(page)
    page.screenshot(path=OUT / "v09-mensagens.png", full_page=True)
    assert api(page, "/inbox/unread")["unread"] == 0, "abrir a mensagem deveria marcar como lida"
    first.get_by_role("button", name="Marcar como não lida").click()
    idle(page)
    assert api(page, "/inbox/unread")["unread"] == 1
    page.get_by_role("button", name="Marcar todas como lidas").click()
    idle(page)
    assert api(page, "/inbox/unread")["unread"] == 0
    # A cópia por e-mail vai para o painel de e-mails enviados.
    emails = api(page, "/admin/emails")
    assert any("Manutenção programada" in e["subject"] for e in emails), "recado sem cópia por e-mail"


@step("v0.9: tema escuro pelo botão rápido, salvo na conta e aplicado em outro aparelho")
def theme_on_account(page: Page):
    page.goto(f"{BASE}/orcamento")
    idle(page)
    tool = page.locator(".sidebar").get_by_role("button", name=re.compile("^Tema:"))
    expect(tool).to_have_attribute("aria-label", re.compile("Tema: Automático"))
    tool.click()  # Claro
    tool.click()  # Escuro
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.wait_for_timeout(400)
    assert api(page, "/auth/me")["theme"] == "dark"
    page.screenshot(path=OUT / "v09-escuro-orcamento.png", full_page=True)
    # Outro "aparelho" (sem nada salvo no navegador): o tema vem da conta.
    other = page.context.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    mobile = other.new_page()
    mobile.goto(f"{BASE}/entrar")
    mobile.get_by_label("E-mail").fill(EMAIL)
    mobile.get_by_label("Senha").fill(PASSWORD)
    mobile.get_by_role("button", name="Entrar").click()
    mobile.wait_for_url("**/orcamento**")
    expect(mobile.locator("html")).to_have_attribute("data-theme", "dark")
    # No celular, o tema também se troca pelo menu "Mais".
    mobile.locator(".tabbar").get_by_role("button", name="Mais").click()
    menu = mobile.locator("dialog[open]")
    menu.get_by_label("Automático").check()
    expect(mobile.locator("html")).not_to_have_attribute("data-theme", "dark")
    mobile.screenshot(path=OUT / "v09-celular-menu-tema.png")
    mobile.wait_for_timeout(400)
    other.close()
    assert api(page, "/auth/me")["theme"] == "system"
    page.reload()
    idle(page)
    expect(page.locator("html")).not_to_have_attribute("data-theme", "dark")


@step("v0.9: começar do zero — escolher áreas, backup, senha e frase; zera só as análises salvas")
def start_over(page: Page):
    page.goto(f"{BASE}/ajustes/perfil")
    idle(page)
    page.get_by_role("button", name="Começar do zero").click()
    d = dialog(page)
    with page.expect_download() as info:
        d.get_by_role("button", name="Baixar backup").click()
    assert info.value.suggested_filename.endswith(".json")
    d.get_by_label("Selecionar tudo").check()
    expect(d.get_by_role("button", name="Apagar tudo")).to_be_disabled()
    expect(d).to_contain_text("a configuração inicial guiada aparece de novo")
    page.screenshot(path=OUT / "v09-comecar-do-zero.png")
    d.get_by_label("Selecionar tudo").uncheck()
    d.get_by_label(re.compile("^Análises salvas")).check()
    d.get_by_label("Sua senha").fill(PASSWORD)
    d.get_by_label(re.compile("Para confirmar")).fill("começar do zero")
    d.get_by_role("button", name=re.compile("Apagar 1 área")).click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    assert api(page, "/analysis/saved") == []
    assert len(api(page, f"/months/{CURRENT}")["expenses"]) > 0, "lançamentos não podiam ser apagados"
    emails = api(page, "/admin/emails")
    assert any(e["subject"] == "Dados apagados da sua conta" for e in emails)


@step("v1.0: financiamento com taxa anual e SAC, parcelas no orçamento, amortização extra e tabela")
def debts(page: Page):
    page.goto(f"{BASE}/dividas")
    idle(page)
    assert api(page, "/debts")["loans"] == []
    page.get_by_role("button", name="Novo financiamento").first.click()
    d = dialog(page)
    d.get_by_label("Tipo").select_option("vehicle")
    d.get_by_label("Nome").fill("Financiamento do carro")
    d.get_by_label("Instituição (opcional)").fill("Banco do Brasil")
    d.get_by_label("Valor financiado", exact=True).fill(money(30000))
    d.get_by_label(re.compile("^Taxa de juros")).fill("18,5")
    d.get_by_label("Ao ano").check()
    d.get_by_label("SAC (parcelas que caem)").check()
    d.get_by_label("Número de parcelas").fill("36")
    first_due = f"{TODAY.year}-{TODAY.month:02d}-15"
    d.get_by_label("Vencimento da 1ª parcela").fill(br_date(first_due))
    expect(d.locator(".summary-box")).to_contain_text("caindo até")
    page.screenshot(path=OUT / "v10-financiamento-form.png")
    d.get_by_role("button", name="Cadastrar").click()
    expect(d).to_have_count(0, timeout=8000)
    idle(page)
    [loan] = api(page, "/debts")["loans"]
    assert loan["installments"] == 36 and loan["system"] == "sac", loan
    assert 1.3 < loan["monthly_rate"] < 1.5, loan["monthly_rate"]
    card = page.locator(".loan-card", has_text="Financiamento do carro")
    expect(card).to_contain_text("0 de 36 parcelas")
    # A 1ª parcela entrou no orçamento do mês.
    month = api(page, f"/months/{CURRENT}")
    assert any(e["description"] == "Financiamento do carro (1/36)" for e in month["expenses"])
    # Amortização extra: reduz o prazo e mostra a economia.
    card.get_by_role("button", name="Simular amortização extra").click()
    d = dialog(page)
    d.get_by_label("Valor a amortizar").fill(money(5000))
    d.get_by_role("button", name="Simular").click()
    expect(d.locator(".summary-box")).to_contain_text("Economia de")
    expect(d.locator(".summary-box")).to_contain_text("Prazo cai de 36")
    page.keyboard.press("Escape")
    # Outra dívida com saldo manual.
    page.get_by_role("button", name="Adicionar").click()
    d = dialog(page)
    d.get_by_label("Nome").fill("Acordo com a loja")
    d.get_by_label("Saldo devedor").fill(money(900))
    d.get_by_label(re.compile("^Pagamento por mês")).fill(money(150))
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0)
    idle(page)
    data = api(page, "/debts")
    assert data["others"][0]["balance"] == "900.00" and len(data["history"]) == 1
    page.screenshot(path=OUT / "v10-dividas.png", full_page=True)
    # Tabela de parcelas para imprimir.
    card.get_by_role("link", name="Tabela de parcelas").click()
    page.wait_for_url("**/dividas/**/tabela")
    idle(page)
    expect(page.locator(".loan-table tbody tr")).to_have_count(36)
    with page.expect_download() as info:
        page.get_by_role("button", name="Baixar planilha").click()
    assert info.value.suggested_filename.endswith(".csv")
    page.screenshot(path=OUT / "v10-tabela.png", full_page=True)


@step("v1.0: calculadoras em Insights (juros compostos, à vista ou parcelado, reserva)")
def calculators(page: Page):
    page.goto(f"{BASE}/analises?secao=calculadoras")
    idle(page)
    result = page.locator(".calc-result")
    expect(result).to_contain_text("Em 5 ano(s)")
    page.get_by_role("button", name="À vista ou parcelado").click()
    expect(result).to_contain_text(re.compile("sai mais barato"))
    page.get_by_role("button", name="Reserva de emergência").click()
    page.get_by_label(re.compile("^Gastos essenciais")).fill(money(2500))
    expect(result).to_contain_text("R$ 15.000,00")
    page.screenshot(path=OUT / "v10-calculadoras.png", full_page=True)


@step("v1.0: mês financeiro pelo dia do salário (período no Orçamento e volta ao dia 1)")
def financial_month(page: Page):
    page.goto(f"{BASE}/ajustes/preferencias")
    idle(page)
    page.get_by_label("Começa no dia").select_option("5")
    idle(page, 500)
    assert api(page, "/auth/me")["month_start_day"] == 5
    expect(page.get_by_text(re.compile(r"Este mês: \d+/\d+ a \d+/\d+"))).to_be_visible()
    page.goto(f"{BASE}/orcamento")
    idle(page)
    expect(page.locator(".page-header")).to_contain_text(re.compile(r"\d+/\d+ a \d+/\d+"))
    page.screenshot(path=OUT / "v10-mes-financeiro.png")
    # Volta ao mês do calendário para os passos seguintes.
    page.goto(f"{BASE}/ajustes/preferencias")
    idle(page)
    page.get_by_label("Começa no dia").select_option("1")
    idle(page, 500)
    assert api(page, "/auth/me")["month_start_day"] == 1


@step("v1.0: alerta de gasto fora do padrão no Orçamento")
def month_alerts(page: Page):
    open_month(page, CURRENT)
    add_expense(page, CURRENT, "Notebook novo", 4200, "Compras", 3)
    idle(page, 500)
    alerts = api(page, f"/alerts?month={CURRENT}")
    assert any("Notebook novo" in a["title"] for a in alerts), alerts
    page.reload()
    idle(page)
    expect(page.locator(".month-alerts")).to_contain_text("Notebook novo")
    page.screenshot(path=OUT / "v10-alertas.png", full_page=True)


@step("v1.0: dividir despesa, placar de quem deve a quem e acerto de contas")
def split_expenses(page: Page):
    open_month(page, CURRENT)
    page.locator(".ledger__row", has_text="Notebook novo").locator(".ledger__open").click()
    d = dialog(page)
    d.get_by_role("button", name="Dividir com outras pessoas").click()
    s = page.locator("dialog[open]", has_text="Como dividir")
    s.get_by_label("Nome da pessoa 1").fill("Bia")
    s.get_by_role("button", name="Adicionar pessoa").click()
    s.get_by_label("Nome da pessoa 2").fill("Caio")
    expect(s.locator(".summary-box")).to_contain_text("R$ 2.800,00")
    s.get_by_role("button", name="Dividir", exact=True).click()
    expect(s).to_have_count(0, timeout=8000)
    page.keyboard.press("Escape")
    idle(page)
    board = api(page, "/splits")
    assert board["owed_to_me"] == "2800.00", board
    page.goto(f"{BASE}/divisoes")
    idle(page)
    bia = page.locator(".split-person", has_text="Bia")
    expect(bia).to_contain_text("te deve R$ 1.400,00")
    page.get_by_role("button", name="Nova anotação").click()
    d = dialog(page)
    d.get_by_label("Eu devo à pessoa").check()
    d.get_by_label("Pessoa", exact=True).fill("Bia")
    d.get_by_label("Valor").fill(money(200))
    d.get_by_label("Descrição").fill("Ingresso do show")
    d.get_by_role("button", name="Salvar").click()
    expect(d).to_have_count(0)
    idle(page)
    expect(bia).to_contain_text("te deve R$ 1.200,00")
    page.screenshot(path=OUT / "v10-divisoes.png", full_page=True)
    incomes_before = len(api(page, f"/months/{CURRENT}")["incomes"])
    bia.get_by_role("button", name="Acertar contas").click()
    d = dialog(page)
    expect(d.get_by_label("Lançar o reembolso como receita deste mês")).to_be_checked()
    d.get_by_role("button", name="Acertar contas").click()
    expect(d).to_have_count(0)
    idle(page)
    incomes = api(page, f"/months/{CURRENT}")["incomes"]
    assert len(incomes) == incomes_before + 1
    assert any(i["description"] == "Reembolso de Bia" and i["amount"] == "1200.00" for i in incomes)
    expect(page.locator(".split-person", has_text="Bia")).to_have_count(0)


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
    expect(page.get_by_role("button", name="Ativar verificação em duas etapas")).to_be_visible()
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
    for path in ("/orcamento", "/calendario", "/metas", "/analises", "/investimentos", "/investimentos?secao=cotacoes", "/historico", "/ajustes", "/ajustes/recorrencias", "/ajustes/dados", "/ajustes/dados?aba=exportar", "/ajustes/notas", "/mensagens", "/dividas", "/divisoes", "/analises?secao=calculadoras", "/ajustes/seguranca", "/ajustes/ajuda", "/ajustes/atalhos", "/cartoes", "/contas", "/revisar", "/busca", "/ajustes/preferencias"):
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
        onboarding(page)
        empty_state(page)
        banner_later(page)
        limits(page)
        first_month(page, months[0])
        history(page, months)
        current_month(page, months)
        installments(page, months)
        undo_delete(page, months[-1])
        edit_expense(page, months[-1])
        receipts(page, months[-1])
        investments(page)
        goals(page)
        goal_teaser(page, months[-1])
        consultant(page, months)
        dashboard(page, months)
        other_tabs(page, months)
        chart_interaction(page)
        builder(page)
        saved_analyses(page)
        flexible_entries(page, months)
        calendar(page)
        market_and_help(page)
        quick_and_bulk(page)
        credit_card(page)
        rules_privacy_feedback(page)
        support_requests(page)
        profile(page)
        debit_card(page)
        validation(page)
        version(page)
        history_report(page, months)
        exports(page)
        import_pdf(page)
        import_csv(page)
        import_ofx(page)
        email_notices(page)
        release_notes(page)
        inbox_and_announcement(page)
        theme_on_account(page)
        start_over(page)
        debts(page)
        calculators(page)
        financial_month(page)
        month_alerts(page)
        split_expenses(page)
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
