"""Testes do novo motor composicional local do Tire sua dúvida (`app.services.bot`).

Cobre:
- Saudações casuais ("OI MANO", "oi tudo bem") vs guarda de finalidade ("EU SÓ FALEI OI",
  assuntos externos, travas de dicionário como operadora "Oi" -> Serviços).
- Extração multi-filtro combinável (período, categoria, cartão, conta, projeto, forma de pagamento,
  faixa de valor, flags de status/essencial/dedutível IR/MEI).
- Localizador universal BM25/fuzzy ("onde está X lançamento?").
- Bateria completa de perguntas reais + 1.000 cenários aleatórios e adversariais (com latência).
"""

from __future__ import annotations

import random
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.api.analysis import AskOut
from app.models import (
    Category,
    Challenge,
    CreditCard,
    Expense,
    Goal,
    Income,
    Investment,
    Loan,
    LoanInstallment,
    MoneyAccount,
    NetWorthSnapshot,
    OtherDebt,
    PersonalLoan,
    PlannedExpense,
    Project,
    RecurringItem,
    SplitShare,
    Transfer,
    User,
)
from app.services import ask
from app.services.bot.nlu.corrector import entry_guess
from app.services.bot.nlu.planner import build_plan

LAB_TODAY = date(2026, 11, 17)


def _seed_rich_user(db: Session) -> User:
    user = User(
        email=f"bot-v2-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-used-in-unit-tests",
        display_name="Teste Bot",
        month_start_day=1,
        mei=True,
    )
    db.add(user)
    db.flush()

    cats = {
        "Alimentação": Category(
            user_id=user.id, name="Alimentação", is_essential=True, monthly_limit=Decimal("1800.00")
        ),
        "Transporte": Category(
            user_id=user.id, name="Transporte", is_essential=True, monthly_limit=Decimal("700.00")
        ),
        "Moradia": Category(
            user_id=user.id, name="Moradia", is_essential=True, monthly_limit=Decimal("2600.00")
        ),
        "Saúde": Category(user_id=user.id, name="Saúde", is_essential=True, deductible="saude"),
        "Educação": Category(
            user_id=user.id, name="Educação", is_essential=True, deductible="educacao"
        ),
        "Lazer": Category(user_id=user.id, name="Lazer", is_essential=False),
        "Assinaturas": Category(user_id=user.id, name="Assinaturas", is_essential=False),
        "Compras": Category(user_id=user.id, name="Compras", is_essential=False),
        "Pets": Category(user_id=user.id, name="Pets", is_essential=True),
        "Serviços": Category(user_id=user.id, name="Serviços", is_essential=True),
    }
    db.add_all(cats.values())
    db.flush()

    acc_nubank = MoneyAccount(
        user_id=user.id, name="Conta Nubank", kind="checking", initial_balance=Decimal("4200.00")
    )
    acc_itau = MoneyAccount(
        user_id=user.id, name="Itaú Poupança", kind="savings", initial_balance=Decimal("12500.00")
    )
    db.add_all([acc_nubank, acc_itau])
    db.flush()

    card_nubank = CreditCard(
        user_id=user.id,
        name="Nubank",
        kind="credit",
        limit_amount=Decimal("8000.00"),
        closing_day=10,
        due_day=17,
        account_id=acc_nubank.id,
    )
    card_inter = CreditCard(
        user_id=user.id,
        name="Inter",
        kind="credit",
        limit_amount=Decimal("5000.00"),
        closing_day=5,
        due_day=12,
    )
    db.add_all([card_nubank, card_inter])
    db.flush()

    proj_reforma = Project(user_id=user.id, name="Reforma Cozinha", budget=Decimal("5000.00"))
    proj_viagem = Project(user_id=user.id, name="Viagem Bahia", budget=Decimal("4500.00"))
    db.add_all([proj_reforma, proj_viagem])
    db.flush()

    rec_netflix = RecurringItem(
        user_id=user.id,
        kind="expense",
        description="Netflix",
        amount=Decimal("55.90"),
        category_id=cats["Assinaturas"].id,
        due_day=8,
        start_month=date(2024, 1, 1),
        payment_method="credit",
    )
    rec_aluguel = RecurringItem(
        user_id=user.id,
        kind="expense",
        description="Aluguel",
        amount=Decimal("2200.00"),
        category_id=cats["Moradia"].id,
        due_day=5,
        start_month=date(2024, 1, 1),
        payment_method="pix",
    )
    db.add_all([rec_netflix, rec_aluguel])
    db.flush()

    def exp(
        month: date,
        desc: str,
        val: str,
        cat: str,
        *,
        when: date | None = None,
        pay: str = "pix",
        card: CreditCard | None = None,
        account: MoneyAccount | None = acc_nubank,
        project: Project | None = None,
        paid: bool = True,
        notes: str | None = None,
        needs_review: bool = False,
        inst_group: uuid.UUID | None = None,
        inst_num: int | None = None,
        inst_tot: int | None = None,
        rec: RecurringItem | None = None,
    ) -> None:
        d = when or date(month.year, month.month, 10)
        db.add(
            Expense(
                user_id=user.id,
                month=month,
                description=desc,
                amount=Decimal(val),
                category_id=cats[cat].id,
                due_date=d,
                purchase_date=d,
                paid=paid,
                payment_method=pay,
                card_id=card.id if card else None,
                account_id=account.id if account and not card else None,
                project_id=project.id if project else None,
                notes=notes,
                needs_review=needs_review,
                installment_group_id=inst_group,
                installment_number=inst_num,
                installment_total=inst_tot,
                recurring_id=rec.id if rec else None,
            )
        )

    # 2024, 2025 e 2026 (2025 é o ano de maior gasto)
    exp(date(2024, 6, 1), "Aluguel", "2000.00", "Moradia", when=date(2024, 6, 5), rec=rec_aluguel)
    exp(
        date(2025, 1, 1),
        "IPVA 2025",
        "1850.00",
        "Transporte",
        when=date(2025, 1, 15),
        pay="boleto",
    )
    exp(
        date(2025, 7, 1),
        "Passagens Aéreas Salvador",
        "3900.00",
        "Lazer",
        when=date(2025, 7, 12),
        pay="credit",
        card=card_nubank,
        project=proj_viagem,
    )
    exp(
        date(2025, 8, 1),
        "Supermercado Assaí",
        "680.00",
        "Alimentação",
        when=date(2025, 8, 14),
        pay="pix",
    )
    exp(
        date(2025, 11, 1),
        "Drogasil",
        "138.00",
        "Saúde",
        when=date(2025, 11, 10),
        pay="debit",
        notes="Compra do antibiótico prescrito",
    )

    # 2026: vários meses com combinações de cartões, projetos, formas de pagamento e flags
    for m in (1, 2, 3, 9, 10, 11):
        exp(
            date(2026, m, 1),
            "Aluguel",
            "2200.00",
            "Moradia",
            when=date(2026, m, 5),
            rec=rec_aluguel,
        )
    exp(
        date(2026, 2, 1),
        "Leroy Merlin",
        "1950.00",
        "Moradia",
        when=date(2026, 2, 18),
        pay="credit",
        card=card_nubank,
        project=proj_reforma,
    )
    exp(
        date(2026, 3, 1),
        "Marcenaria Armário",
        "1300.00",
        "Moradia",
        when=date(2026, 3, 20),
        pay="pix",
        project=proj_reforma,
    )
    exp(
        date(2026, 9, 1),
        "Mercado Extra",
        "540.00",
        "Alimentação",
        when=date(2026, 9, 12),
        pay="debit",
    )
    exp(
        date(2026, 10, 1),
        "Cobasi Ração",
        "245.00",
        "Pets",
        when=date(2026, 10, 14),
        pay="credit",
        card=card_inter,
    )
    exp(
        date(2026, 10, 1),
        "Droga Raia",
        "152.00",
        "Saúde",
        when=date(2026, 10, 18),
        pay="pix",
    )
    exp(
        date(2026, 10, 1),
        "Mercado Extra",
        "698.30",
        "Alimentação",
        when=date(2026, 10, 10),
        pay="debit",
    )
    exp(
        date(2026, 10, 1),
        "Uber",
        "42.50",
        "Transporte",
        when=date(2026, 10, 21),
        pay="credit",
        card=card_nubank,
    )
    exp(
        date(2026, 10, 1),
        "Faculdade Mensalidade",
        "1908.00",
        "Educação",
        when=date(2026, 10, 8),
        pay="boleto",
    )
    exp(
        date(2026, 11, 1),
        "Internet",
        "99.90",
        "Serviços",
        when=date(2026, 11, 15),
        pay="boleto",
        paid=True,
    )
    exp(
        date(2026, 11, 1),
        "iFood Pizza",
        "78.90",
        "Alimentação",
        when=LAB_TODAY,
        pay="credit",
        card=card_nubank,
        paid=False,
    )
    exp(
        date(2026, 11, 1),
        "Padaria",
        "18.00",
        "Alimentação",
        when=LAB_TODAY - timedelta(days=1),
        pay="cash",
        paid=True,
    )
    exp(
        date(2026, 11, 1),
        "Cinema",
        "65.00",
        "Lazer",
        when=date(2026, 11, 9),
        pay="credit",
        card=card_inter,
        paid=False,
        needs_review=True,
    )
    exp(
        date(2026, 11, 1),
        "Conta de Luz",
        "180.00",
        "Moradia",
        when=LAB_TODAY + timedelta(days=3),
        pay="boleto",
        paid=False,
    )
    exp(
        date(2026, 11, 1),
        "Condomínio Atrasado",
        "450.00",
        "Moradia",
        when=LAB_TODAY - timedelta(days=4),
        pay="boleto",
        paid=False,
    )
    exp(
        date(2026, 11, 1),
        "Netflix",
        "55.90",
        "Assinaturas",
        when=date(2026, 11, 8),
        pay="credit",
        card=card_nubank,
        rec=rec_netflix,
        paid=False,
    )

    inst_group = uuid.uuid4()
    for n, m_off in enumerate((0, 1, 2), start=1):
        m_dt = date(2026 + (11 + m_off - 1) // 12, (11 + m_off - 1) % 12 + 1, 1)
        exp(
            m_dt,
            f"Notebook ({n}/3)",
            "900.00",
            "Compras",
            when=date(m_dt.year, m_dt.month, 10),
            pay="credit",
            card=card_nubank,
            paid=False,
            inst_group=inst_group,
            inst_num=n,
            inst_tot=3,
        )

    # Receitas (inclui MEI)
    db.add_all(
        [
            Income(
                user_id=user.id,
                month=date(2025, 6, 1),
                description="Freela Web",
                amount=Decimal("2500.00"),
                account_id=acc_nubank.id,
                mei=True,
            ),
            Income(
                user_id=user.id,
                month=date(2026, 10, 1),
                description="Salário",
                amount=Decimal("6500.00"),
                day=5,
                account_id=acc_nubank.id,
            ),
            Income(
                user_id=user.id,
                month=date(2026, 11, 1),
                description="Salário",
                amount=Decimal("6500.00"),
                day=5,
                account_id=acc_nubank.id,
            ),
            Income(
                user_id=user.id,
                month=date(2026, 11, 1),
                description="Freela Consultoria",
                amount=Decimal("7200.00"),
                day=12,
                account_id=acc_nubank.id,
                mei=True,
            ),
        ]
    )

    # Demais entidades: transferência, meta, desafio, investimento, dívidas, divisões e planejado
    db.add(
        Transfer(
            user_id=user.id,
            from_account_id=acc_nubank.id,
            to_account_id=acc_itau.id,
            amount=Decimal("1000.00"),
            date=date(2026, 10, 15),
            notes="Reserva mensal",
        )
    )
    db.add(
        Goal(
            user_id=user.id,
            name="Reserva de Emergência",
            target_amount=Decimal("20000.00"),
            current_amount=Decimal("12000.00"),
            is_main=True,
        )
    )
    db.add(
        Challenge(
            user_id=user.id,
            title="Semana sem delivery",
            kind="no_spend",
            category_id=cats["Alimentação"].id,
            start_date=date(2026, 11, 1),
            days=7,
        )
    )
    db.add(
        Investment(
            user_id=user.id,
            name="Tesouro Selic",
            kind="fixed",
            institution="Nubank",
            invested_amount=Decimal("10000.00"),
            current_value=Decimal("11250.00"),
            is_emergency_reserve=True,
        )
    )
    db.add(
        Loan(
            user_id=user.id,
            kind="vehicle",
            name="Financiamento Carro",
            institution="Banco Itaú",
            principal=Decimal("36000.00"),
            rate=Decimal("1.2000"),
            rate_period="monthly",
            system="price",
            installments=36,
            first_due=date(2025, 1, 10),
            paid_before=12,
        )
    )
    db.add(OtherDebt(user_id=user.id, name="Acordo Cartão Antigo", balance=Decimal("1200.00")))
    db.add(
        NetWorthSnapshot(
            user_id=user.id,
            month=date(2026, 10, 1),
            assets=Decimal("28000.00"),
            debts=Decimal("25200.00"),
        )
    )
    db.add(
        PlannedExpense(
            user_id=user.id,
            date=LAB_TODAY + timedelta(days=10),
            description="Revisão do carro",
            amount=Decimal("650.00"),
            category_id=cats["Transporte"].id,
        )
    )

    pl = PersonalLoan(
        user_id=user.id,
        person="João",
        description="Empréstimo emergencial",
        direction="owes_me",
        principal=Decimal("1000.00"),
        mode="total",
        rate=Decimal("10.0000"),
        frequency="month",
        count=2,
        first_due=date(2026, 10, 10),
    )
    db.add(pl)
    db.flush()
    db.add_all(
        [
            LoanInstallment(
                loan_id=pl.id,
                number=1,
                due_date=date(2026, 10, 10),
                amount=Decimal("550.00"),
                interest=Decimal("50.00"),
                principal_part=Decimal("500.00"),
                received_at=date(2026, 10, 10),
                received_amount=Decimal("550.00"),
            ),
            LoanInstallment(
                loan_id=pl.id,
                number=2,
                due_date=date(2026, 11, 10),
                amount=Decimal("550.00"),
                interest=Decimal("50.00"),
                principal_part=Decimal("500.00"),
            ),
        ]
    )
    db.add(
        SplitShare(
            user_id=user.id,
            person="Maria",
            description="Jantar churrasco",
            amount=Decimal("120.00"),
            direction="owes_me",
        )
    )
    db.commit()
    return user


@pytest.fixture
def rich_user(db: Session) -> tuple[Session, User]:
    return db, _seed_rich_user(db)


def test_saudacao_casual_e_bloqueio_da_operadora_oi(rich_user: tuple[Session, User]) -> None:
    db, user = rich_user
    # Regressão do print: "OI MANO" é saudação amigável, nunca gasto com Serviços/Internet!
    for greeting in ("OI MANO", "oi cara", "oi tudo bem", "bom dia pessoal", "olá galera"):
        out = ask.answer(db, user, greeting, today=LAB_TODAY)
        assert out["intent"] == "help", (greeting, out)
        assert "Serviços" not in out["answer"] and "99,90" not in out["answer"]

    # "EU SÓ FALEI OI" não deve cair em Serviços/Internet (guarda de finalidade)
    only_oi = ask.answer(db, user, "EU SÓ FALEI OI", today=LAB_TODAY)
    assert only_oi["intent"] == "out_of_scope", only_oi
    assert "Serviços" not in only_oi["answer"] and "99,90" not in only_oi["answer"]
    assert "finalidade" in only_oi["answer"].lower()

    # Com verbo financeiro explícito, "quanto gastei com oi" consulta Serviços normalmente
    explicit_oi = ask.answer(db, user, "quanto gastei com oi?", today=LAB_TODAY)
    assert explicit_oi["intent"] == "sum"
    assert "99,90" in explicit_oi["answer"]


def test_multiplos_filtros_simultaneos_e_faixa_de_valor(rich_user: tuple[Session, User]) -> None:
    db, user = rich_user
    plan, _ = build_plan(
        db,
        user,
        "Quanto gastei no pix em alimentação acima de 500 em 2025?",
        LAB_TODAY,
    )
    assert plan.intent == "sum"
    assert plan.filters.payment_methods == ["pix"]
    assert plan.filters.category_names == ["Alimentação"]
    assert plan.filters.amount.min_amount == Decimal("500.00")
    assert plan.filters.period is not None and plan.filters.period.start == date(2025, 1, 1)

    out = ask.answer(
        db, user, "Quanto gastei no pix em alimentação acima de 500 em 2025?", today=LAB_TODAY
    )
    assert out["intent"] == "sum" and "680,00" in out["answer"]

    plan_range, _ = build_plan(
        db, user, "Quais compras entre 100 e 1000 no cartão Nubank?", LAB_TODAY
    )
    assert plan_range.filters.card_names == ["Nubank"]
    assert plan_range.filters.amount.min_amount == Decimal("100.00")
    assert plan_range.filters.amount.max_amount == Decimal("1000.00")

    assert entry_guess("onde esta o gasto de 150 no mercado?") is None
    assert entry_guess("gastos acima de 200") is None


def test_localizador_universal_em_varias_tabelas(rich_user: tuple[Session, User]) -> None:
    db, user = rich_user
    cobasi = ask.answer(db, user, "Onde está o lançamento da Cobasi?", today=LAB_TODAY)
    assert cobasi["intent"] == "locate_record" and "Cobasi" in cobasi["answer"]
    assert cobasi["items"][0]["link"] == "/orcamento/2026-10"

    raia = ask.answer(db, user, "Cadê aquele gasto de 150 na farmácia?", today=LAB_TODAY)
    assert raia["intent"] == "locate_record"
    assert any("Droga Raia" in i["label"] for i in raia["items"])

    nota = ask.answer(db, user, "Onde lancei a compra do antibiótico?", today=LAB_TODAY)
    assert nota["intent"] == "locate_record"
    assert any("Drogasil" in i["label"] for i in nota["items"])

    emp = ask.answer(db, user, "Onde está o empréstimo do João?", today=LAB_TODAY)
    assert emp["intent"] == "locate_record"
    assert any("/divisoes" in (i["link"] or "") for i in emp["items"])

    prox = ask.answer(db, user, "Qual valor mais próximo de 150?", today=LAB_TODAY)
    assert prox["intent"] == "locate_record"
    assert any("Droga Raia" in i["label"] for i in prox["items"])


def test_entidades_completas_ir_mei_projetos_cartoes_contas(
    rich_user: tuple[Session, User],
) -> None:
    db, user = rich_user
    proj = ask.answer(db, user, "Quanto gastei no projeto Reforma Cozinha?", today=LAB_TODAY)
    assert proj["intent"] == "sum" and "3.250,00" in proj["answer"]

    ir = ask.answer(
        db, user, "Quanto paguei de despesas dedutíveis no IR em 2026?", today=LAB_TODAY
    )
    assert ir["intent"] == "tax_deductible" and "2.060,00" in ir["answer"]

    mei = ask.answer(db, user, "Como está meu faturamento MEI em 2026?", today=LAB_TODAY)
    assert mei["intent"] == "mei" and "7.200,00" in mei["answer"]

    assert ask.answer(db, user, "Qual o saldo das contas?", today=LAB_TODAY)["intent"] == "accounts"
    assert (
        ask.answer(db, user, "Quais transferências fiz entre contas?", today=LAB_TODAY)["intent"]
        == "transfers"
    )
    review = ask.answer(db, user, "O que falta revisar?", today=LAB_TODAY)
    assert review["intent"] == "review_pending"
    assert (
        ask.answer(db, user, "Qual cartão gastei mais em 2026?", today=LAB_TODAY)["intent"]
        == "card_max"
    )
    assert (
        ask.answer(db, user, "Qual forma de pagamento mais uso em 2025?", today=LAB_TODAY)["intent"]
        == "payment_method_max"
    )


def test_guarda_de_finalidade_em_assuntos_externos(rich_user: tuple[Session, User]) -> None:
    db, user = rich_user
    for q in (
        "O rato roeu a roupa do rei de roma?",
        "Receita de bolo de chocolate",
        "Vai chover hoje?",
        "Quem ganhou o jogo ontem?",
    ):
        out = ask.answer(db, user, q, today=LAB_TODAY, debug=True)
        assert out["intent"] == "out_of_scope", (q, out)
        assert "finalidade" in out["answer"].lower()
        assert "meu orçamento" in out["answer"].lower()


def test_bateria_1000_cenarios_aleatorios_e_adversariais(
    rich_user: tuple[Session, User],
) -> None:
    db, user = rich_user
    rng = random.Random(20261117)

    random_words = [
        "banana",
        "foguete",
        "montanha",
        "oceano",
        "rato",
        "rei",
        "roma",
        "roupa",
        "cachorro",
        "gato",
        "livro",
        "guitarra",
        "nuvem",
        "cadeira",
        "janela",
        "sol",
        "lua",
        "pedra",
        "vento",
        "flor",
        "planeta",
        "elefante",
        "tigre",
        "abacaxi",
        "dragao",
        "castelo",
        "floresta",
        "praia",
        "sapato",
        "camisa",
        "bolo",
        "violao",
        "navio",
        "estrela",
        "galaxia",
    ]
    gibberish = [
        "asdfgh",
        "qwertyuiop",
        "zxcvbnm",
        "blablabla",
        "kkk",
        "xpto999",
        "SELECT * FROM expenses;",
        "<script>alert(1)</script>",
        "123456789",
        "EU SÓ FALEI OI",
    ]
    off_topic = [
        "O rato roeu a roupa do rei de roma?",
        "Vai chover {period_trap}?",
        "Qual a previsão do tempo {period_trap}?",
        "Quem ganhou o jogo do Flamengo {period_trap}?",
        "Qual a capital da França?",
        "Receita de bolo de chocolate {period_trap}",
        "Quanto pesa um {animal}?",
        "Quanto é {n1} + {n2}?",
        "Qual o melhor filme de {year}?",
        "Me conta uma piada sobre {animal}",
        "Escreve um código em python para ordenar lista",
        "Você é uma inteligência artificial?",
        "Onde fica a torre eiffel?",
        "Como tocar guitarra melhor?",
        "Qual o sentido da vida?",
    ]
    valid_intents = {
        "sum",
        "incomes",
        "empty",
        "count",
        "average",
        "per_day",
        "per_week",
        "biggest",
        "smallest",
        "list_records",
        "percent",
        "balance",
        "compare",
        "year_max",
        "year_min",
        "month_max",
        "month_min",
        "day_max",
        "weekday_max",
        "top_categories",
        "category_max",
        "card_max",
        "payment_method_max",
        "project_max",
        "month_list",
        "year_list",
        "can_spend",
        "due",
        "cards",
        "invoices",
        "installments",
        "loans",
        "friend_loans",
        "recurring",
        "goals",
        "investments",
        "accounts",
        "transfers",
        "projects",
        "tax_deductible",
        "mei",
        "net_worth",
        "review_pending",
        "locate_record",
    }
    cases: list[tuple[str, str, set[str]]] = []
    for i in range(250):
        q = (
            rng.choice(gibberish)
            if i % 5 == 0
            else " ".join(rng.sample(random_words, rng.randint(1, 5)))
        )
        expected = (
            {"out_of_scope"} if "planeta" in q.split() or q == "EU SÓ FALEI OI" else {"fallback"}
        )
        cases.append(("gibberish", q, expected))
    for _ in range(250):
        q = rng.choice(off_topic).format(
            period_trap=rng.choice(["hoje", "ontem", "este mês", "em 2025"]),
            animal=rng.choice(["elefante", "cachorro", "rato"]),
            year=rng.choice(["2024", "2025", "2026"]),
            n1=rng.randint(2, 99),
            n2=rng.randint(2, 99),
        )
        cases.append(("off_topic", q, {"out_of_scope"}))
    for i in range(250):
        if i % 3 == 0:
            q = (
                " ".join(
                    p
                    for p in [
                        "Quanto gastei",
                        rng.choice(["", "no pix", "no crédito", "no débito", "no boleto"]),
                        rng.choice(["", "no cartão Nubank", "no cartão Inter"]),
                        rng.choice(
                            ["", "em alimentação", "em transporte", "em saúde", "em moradia"]
                        ),
                        rng.choice(["", "acima de 100", "entre 50 e 500"]),
                        rng.choice(["", "em 2025", "em 2026", "em outubro", "este mês"]),
                    ]
                    if p
                )
                + "?"
            )
        elif i % 3 == 1:
            q = rng.choice(
                [
                    "Qual ano mais gastei?",
                    "Qual foi meu maior gasto em 2025?",
                    "Qual categoria pesou mais este mês?",
                    "Qual cartão gastei mais em 2026?",
                    "Qual forma de pagamento mais uso em 2025?",
                    "Quanto posso gastar hoje?",
                    "O que vence nos próximos dias?",
                    "Qual fatura vence primeiro?",
                    "Quantas parcelas faltam?",
                    "Quanto o João ainda me deve?",
                    "Quanto paguei de despesas dedutíveis no IR em 2026?",
                    "Como está meu faturamento MEI em 2026?",
                    "Qual o saldo das contas?",
                    "O que falta revisar?",
                    "Comparar outubro com setembro",
                ]
            )
        else:
            q = rng.choice(
                [
                    "Quanto gastei no projeto Reforma Cozinha?",
                    "Quanto recebi em 2026?",
                    "Quanto sobrou em outubro?",
                    "Quanto gastei com Uber em 2026?",
                    "Gastos mês a mês em 2026",
                ]
            )
        cases.append(("valid", q, valid_intents))
    for i in range(150):
        if i % 3 == 0:
            q = rng.choice(
                [
                    "Onde encontro as recorrências?",
                    "Onde mudo minha senha?",
                    "Onde mudo a cor do tema?",
                    "Onde fica meu perfil?",
                    "Como exporto meus dados?",
                    "Onde fica o simulador?",
                ]
            )
            cases.append(("navigate", q, {"navigate"}))
        else:
            prefix = rng.choice(["Onde está o", "Cadê o", "Onde lancei o", "Localiza o"])
            target = rng.choice(
                [
                    "lançamento da Cobasi",
                    "gasto de 150 na farmácia",
                    "compra do antibiótico",
                    "empréstimo do João",
                    "lançamento do IPVA",
                    "transferência de 1000",
                    "gasto da Leroy Merlin",
                ]
            )
            cases.append(("locate", f"{prefix} {target}?", {"locate_record"}))
    for _ in range(100):
        q = rng.choice(
            [
                " ".join(rng.sample(random_words, 3)),
                "O rato roeu a roupa do rei de roma?",
                "Receita de bolo de chocolate",
            ]
        )
        expected = (
            {"out_of_scope"}
            if "planeta" in q.split()
            or q in {"O rato roeu a roupa do rei de roma?", "Receita de bolo de chocolate"}
            else {"fallback"}
        )
        cases.append(("derail", q, expected))

    assert len(cases) == 1000
    valid_ctx = ask.answer(db, user, "Quanto gastei em setembro?", today=LAB_TODAY)["context"]
    failures: list[str] = []
    t0 = time.perf_counter()
    for idx, (bucket, question, expected) in enumerate(cases, start=1):
        ctx = valid_ctx if bucket == "derail" else None
        out = ask.answer(db, user, question, today=LAB_TODAY, context=ctx, debug=True)
        AskOut.model_validate(out)
        ok = out["intent"] in expected
        if (
            bucket in {"gibberish", "off_topic", "derail"}
            and out["intent"] == "out_of_scope"
            and "finalidade" not in out["answer"].lower()
        ):
            ok = False
        if out["intent"] == "fallback" and "não tenho certeza" not in out["answer"].lower():
            ok = False
        if not ok:
            rules = out["debug"]["matched_rules"]
            failures.append(
                f"[{idx} {bucket}] {question!r} -> {out['intent']} (esp {expected}) {rules}"
            )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert not failures, f"{len(failures)} falhas em 1000:\n" + "\n".join(failures[:15])
    assert elapsed_ms / len(cases) < 35.0, f"Latência média alta: {elapsed_ms / len(cases):.2f} ms"
