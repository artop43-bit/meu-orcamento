"""Extrator multi-filtro: lê todos os parâmetros presentes na frase de forma combinável."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    CreditCard,
    Expense,
    Goal,
    Income,
    Investment,
    Loan,
    MoneyAccount,
    PersonalLoan,
    Project,
    RecurringItem,
    SplitShare,
)
from app.services.bot.contracts import AmountFilter, QueryFilters
from app.services.bot.lexicon import core, domain, intents
from app.services.bot.text_utils import normalize

_FILTER_NOISE = (
    core.COMMON_STOPWORDS
    | set(core.QUESTION_STARTERS)
    | set(core.ASK_VERBS)
    | set(core.PAYMENT_TERMS)
    | set(intents.MOST_TRIGGERS)
    | set(intents.LEAST_TRIGGERS)
    | set(intents.NAVIGATE_HINT_WORDS)
    | {
        "pix",
        "debito",
        "credito",
        "boleto",
        "dinheiro",
        "especie",
        "cash",
        "recorrente",
        "recorrentes",
        "assinatura",
        "assinaturas",
        "parcelado",
        "parcelados",
        "parcelada",
        "parceladas",
        "parcela",
        "parcelas",
        "pago",
        "pagos",
        "paga",
        "pagas",
        "quitado",
        "quitados",
        "pendente",
        "pendentes",
        "atrasado",
        "atrasados",
        "atrasada",
        "atrasadas",
        "aberto",
        "abertos",
        "revisar",
        "revisao",
        "conferir",
        "essencial",
        "essenciais",
        "superfluo",
        "dedutivel",
        "dedutiveis",
        "imposto",
        "renda",
        "irpf",
        "mei",
        "faturamento",
        "receita",
        "receitas",
        "salario",
        "salarios",
        "transferencia",
        "transferencias",
        "investimento",
        "investimentos",
        "financiamento",
        "financiamentos",
        "emprestimo",
        "emprestimos",
        "divida",
        "dividas",
        "divisao",
        "divisoes",
        "meta",
        "metas",
        "desafio",
        "desafios",
        "planejado",
        "planejados",
        "patrimonio",
        "fatura",
        "faturas",
        "limite",
        "vence",
        "vencem",
        "vencimento",
        "vencimentos",
        "recebi",
        "recebeu",
        "recebido",
        "recebimentos",
        "ganhei",
        "entrou",
        "entrada",
        "entradas",
        "sobrou",
        "sobra",
        "saldo",
        "balanco",
        "percentual",
        "porcentagem",
        "porcento",
        "proporcao",
        "comprometimento",
        "comprometido",
        "vezes",
        "pedi",
        "evolucao",
        "dia",
        "semana",
        "mes",
        "ano",
        "trimestre",
        "semestre",
        "aquele",
        "aquela",
        "esses",
        "essas",
        "onde",
        "cade",
        "aonde",
        "fica",
        "ficam",
        "encontra",
        "encontro",
        "localiza",
        "procura",
        "busca",
        "acha",
        "achar",
        "reais",
        "real",
        "disso",
        "disto",
        "daquilo",
        "nisso",
        "nisto",
        "naquilo",
        "proximo",
        "proxima",
        "x",
        "vai",
        "vao",
        "vem",
        "veio",
        "saiu",
        "sairam",
        "diario",
        "diaria",
        "diarios",
        "diarias",
        "semanal",
        "semanais",
        "mensal",
        "mensais",
        "anual",
        "anuais",
        "estao",
        "meu",
        "minha",
        "meus",
        "minhas",
        "falta",
        "faltam",
    }
)


@dataclass
class UserEntityIndex:
    categories: list[Category] = field(default_factory=list)
    cards: list[CreditCard] = field(default_factory=list)
    accounts: list[MoneyAccount] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    investments: list[Investment] = field(default_factory=list)
    loans: list[Loan] = field(default_factory=list)
    expense_descriptions: list[str] = field(default_factory=list)
    income_descriptions: list[str] = field(default_factory=list)
    recurring_descriptions: list[str] = field(default_factory=list)


def load_entity_index(db: Session, user_id: uuid.UUID) -> UserEntityIndex:
    people_set: set[str] = set()
    for p in db.scalars(select(PersonalLoan.person).where(PersonalLoan.user_id == user_id)):
        if p:
            people_set.add(p)
    for p in db.scalars(select(SplitShare.person).where(SplitShare.user_id == user_id)):
        if p:
            people_set.add(p)

    return UserEntityIndex(
        categories=list(db.scalars(select(Category).where(Category.user_id == user_id))),
        cards=list(db.scalars(select(CreditCard).where(CreditCard.user_id == user_id))),
        accounts=list(db.scalars(select(MoneyAccount).where(MoneyAccount.user_id == user_id))),
        projects=list(db.scalars(select(Project).where(Project.user_id == user_id))),
        people=sorted(people_set),
        goals=list(db.scalars(select(Goal).where(Goal.user_id == user_id))),
        investments=list(db.scalars(select(Investment).where(Investment.user_id == user_id))),
        loans=list(db.scalars(select(Loan).where(Loan.user_id == user_id))),
        expense_descriptions=list(
            db.scalars(
                select(Expense.description).where(Expense.user_id == user_id).distinct().limit(4000)
            )
        ),
        income_descriptions=list(
            db.scalars(
                select(Income.description).where(Income.user_id == user_id).distinct().limit(1000)
            )
        ),
        recurring_descriptions=list(
            db.scalars(
                select(RecurringItem.description).where(RecurringItem.user_id == user_id).distinct()
            )
        ),
    )


def _parse_money_str(raw: str) -> Decimal | None:
    cleaned = raw.strip().lower().replace("r$", "").strip()
    mult = Decimal("1")
    if cleaned.endswith("mil"):
        cleaned = cleaned[:-3].strip()
        mult = Decimal("1000")
    elif cleaned.endswith("k"):
        cleaned = cleaned[:-1].strip()
        mult = Decimal("1000")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") == 1 and len(cleaned.split(".")[1]) == 3 and mult == 1:
        cleaned = cleaned.replace(".", "")
    try:
        return (Decimal(cleaned) * mult).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


_MONEY_NUM = r"(?:r\$\s*)?(\d+(?:[.,]\d+)?(?:\s*(?:k|mil))?)"


def extract_amount_filter(text: str) -> tuple[AmountFilter, str]:
    """Extrai restrições de valor (entre A e B, acima de, abaixo de, perto de, de X reais)."""
    af = AmountFilter()

    def cut(m: re.Match[str]) -> str:
        return " ".join((text[: m.start()] + " " + text[m.end() :]).split())

    # 1. Entre X e Y [reais]
    if m := re.search(
        rf"\bentre\s+{_MONEY_NUM}\s+e\s+{_MONEY_NUM}(?:\s*reais)?\b",
        text,
    ):
        v1, v2 = _parse_money_str(m[1]), _parse_money_str(m[2])
        if v1 is not None and v2 is not None:
            lo, hi = min(v1, v2), max(v1, v2)
            return AmountFilter(min_amount=lo, max_amount=hi, raw_expr=m[0]), cut(m)

    # 2. Acima de / maior que / a partir de / > X
    if m := re.search(
        rf"\b(?:acima de|mais de|mais que|maior que|maiores que|a partir de|pelo menos)\s+{_MONEY_NUM}(?:\s*reais)?\b",
        text,
    ):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(min_amount=val, raw_expr=m[0]), cut(m)
    if m := re.search(rf"(?:>=|>)\s*{_MONEY_NUM}\b", text):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(min_amount=val, raw_expr=m[0]), cut(m)

    # 3. Abaixo de / menos de / menor que / ate / <= / < X
    if m := re.search(
        rf"\b(?:abaixo de|menos de|menos que|menor que|menores que|no maximo|ate)\s+{_MONEY_NUM}(?:\s*reais)?\b",
        text,
    ):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(max_amount=val, raw_expr=m[0]), cut(m)
    if m := re.search(rf"(?:<=|<)\s*{_MONEY_NUM}\b", text):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(max_amount=val, raw_expr=m[0]), cut(m)

    # 4. Aproximado / exato: "perto de 150", "mais proximo de 150", "~150", "de R$ 89,90", "de 150 reais"
    if m := re.search(
        rf"\b(?:mais\s+proxim[oa]\s+de|proxim[oa]\s+de|perto de|cerca de|aproximadamente|por volta de|em torno de|uns|umas|no valor de|valor de)\s+{_MONEY_NUM}(?:\s*reais)?\b",
        text,
    ):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(
                target_amount=val, tolerance_pct=Decimal("0.15"), raw_expr=m[0]
            ), cut(m)

    if m := re.search(r"~\s*(\d+(?:[.,]\d+)?(?:\s*(?:k|mil))?)", text):
        val = _parse_money_str(m[1])
        if val is not None:
            return AmountFilter(
                target_amount=val, tolerance_pct=Decimal("0.15"), raw_expr=m[0]
            ), cut(m)

    if m := re.search(
        r"(?:\br\$\s*(\d+(?:[.,]\d+)?(?:\s*(?:k|mil))?)|\b(?:de\s+)?(\d+(?:[.,]\d+)?)\s+reais\b|\bde\s+(\d+(?:,\d{2}))\b)",
        text,
    ):
        raw_val = m[1] or m[2] or m[3]
        val = _parse_money_str(raw_val)
        if val is not None:
            return AmountFilter(
                target_amount=val, tolerance_pct=Decimal("0.05"), raw_expr=m[0]
            ), cut(m)

    # "gasto de 150" / "lancamento de 150" (sem 'reais', sem 'top 5', sem '2025')
    if m := re.search(
        r"\b(?:gasto|gastos|compra|compras|despesa|despesas|lancamento|pix|boleto|receita|transferencia)\s+de\s+(?:uns\s+)?(\d+(?:[.,]\d+)?)\b",
        text,
    ):
        val = _parse_money_str(m[1])
        if val is not None and not (2000 <= val <= 2100 and "," not in m[1]):
            return AmountFilter(
                target_amount=val, tolerance_pct=Decimal("0.08"), raw_expr=m[0]
            ), cut(m)

    return af, text


def _contains_phrase(phrase: str, term: str) -> bool:
    return f" {term} " in f" {phrase} "


def _strip_phrase(text: str, term: str) -> str:
    pattern = rf"\b{re.escape(term)}\b"
    return " ".join(re.sub(pattern, " ", text).split())


def _extract_payment_methods(
    work_norm: str, filters: QueryFilters, matched_rules: list[str]
) -> str:
    debit_as_expense = bool(
        re.search(
            r"\b(?:maior|maiores|menor|menores|ultimo|ultima|ultimos|ultimas)\s+debit[oa]s?\b",
            work_norm,
        )
    )
    for term in sorted(core.PAYMENT_TERMS, key=len, reverse=True):
        if term == "debito" and debit_as_expense:
            continue
        if _contains_phrase(work_norm, term):
            method = core.PAYMENT_TERMS[term]
            if method not in filters.payment_methods:
                filters.payment_methods.append(method)
                matched_rules.append(f"payment:{method}")
            if term not in {"cartao", "cartoes"}:
                work_norm = _strip_phrase(work_norm, term)
    return work_norm


def _extract_status_flags(work_norm: str, filters: QueryFilters, matched_rules: list[str]) -> None:
    def match_any(terms: list[str]) -> str | None:
        for t in sorted(terms, key=len, reverse=True):
            if _contains_phrase(work_norm, t):
                return t
        return None

    if m := match_any(domain.STATUS_TRIGGERS["paid_false"]):
        filters.paid = False
        matched_rules.append(f"paid=False({m})")
    elif m := match_any(domain.STATUS_TRIGGERS["paid_true"]):
        filters.paid = True
        matched_rules.append(f"paid=True({m})")

    for trigger_key, attr, rule_label in (
        ("overdue_true", "overdue", "overdue=True"),
        ("needs_review_true", "needs_review", "needs_review=True"),
        ("installment_true", "is_installment", "installment=True"),
        ("recurring_true", "is_recurring", "recurring=True"),
        ("mei_true", "mei", "mei=True"),
    ):
        if m := match_any(domain.STATUS_TRIGGERS[trigger_key]):
            setattr(filters, attr, True)
            matched_rules.append(f"{rule_label}({m})")

    if m := match_any(domain.STATUS_TRIGGERS["essential_false"]):
        filters.is_essential = False
        matched_rules.append(f"essential=False({m})")
    elif m := match_any(domain.STATUS_TRIGGERS["essential_true"]):
        filters.is_essential = True
        matched_rules.append(f"essential=True({m})")

    for ded_kind, terms in domain.DEDUCTIBLE_TERMS.items():
        if match_any(terms) and any(
            _contains_phrase(work_norm, cue)
            for cue in ("dedutivel", "dedutiveis", "imposto de renda", "irpf")
        ):
            filters.deductible = ded_kind
            matched_rules.append(f"deductible={ded_kind}")
            break
    if filters.deductible is None and match_any(domain.ENTITY_TERMS["tax_deductible"]):
        filters.deductible = "any"
        matched_rules.append("deductible=any")


def _extract_projects(
    work_norm: str, index: UserEntityIndex, filters: QueryFilters, matched_rules: list[str]
) -> str:
    for project in sorted(index.projects, key=lambda p: -len(p.name)):
        pname = normalize(project.name)
        if not pname or not (
            _contains_phrase(work_norm, pname)
            or any(len(tok) >= 5 and tok in work_norm.split() for tok in pname.split())
        ):
            continue
        if (
            _contains_phrase(work_norm, pname)
            or _contains_phrase(work_norm, f"projeto {pname}")
            or any(
                _contains_phrase(work_norm, f"projeto {tok}")
                for tok in pname.split()
                if len(tok) >= 4
            )
        ):
            filters.project_ids.append(project.id)
            filters.project_names.append(project.name)
            work_norm = _strip_phrase(work_norm, pname)
            matched_rules.append(f"project:{project.name}")
        elif len(pname.split()) >= 2:
            for tok in pname.split():
                if len(tok) >= 5 and tok in work_norm.split() and tok not in _FILTER_NOISE:
                    filters.project_ids.append(project.id)
                    filters.project_names.append(project.name)
                    work_norm = _strip_phrase(work_norm, tok)
                    matched_rules.append(f"project:{project.name}")
                    break
    return work_norm


def _extract_cards_accounts_people(
    text: str,
    work_norm: str,
    index: UserEntityIndex,
    filters: QueryFilters,
    matched_rules: list[str],
) -> str:
    explicit_card = bool(re.search(r"\b(?:cartao|fatura|credito|limite)\b", normalize(text)))
    explicit_account = bool(
        re.search(
            r"\b(?:conta|saldo|transferencia|transferi|poupanca|carteira|corrente)\b",
            normalize(text),
        )
    )

    matched_card_tokens: set[str] = set()
    for card in sorted(index.cards, key=lambda c: -len(c.name)):
        cname = normalize(card.name)
        c_tokens = [
            t
            for t in cname.split()
            if len(t) >= 3 and t not in {"cartao", "credito", "debito", "banco"}
        ]
        hit = _contains_phrase(work_norm, cname) or any(t in work_norm.split() for t in c_tokens)
        if not hit:
            continue
        same_name_account = any(
            normalize(a.name) == cname or any(t in normalize(a.name).split() for t in c_tokens)
            for a in index.accounts
        )
        if not same_name_account or explicit_card or not explicit_account:
            filters.card_ids.append(card.id)
            filters.card_names.append(card.name)
            matched_card_tokens.update(cname.split())
            matched_rules.append(f"card:{card.name}")

    for account in sorted(index.accounts, key=lambda a: -len(a.name)):
        aname = normalize(account.name)
        a_tokens = [
            t for t in aname.split() if len(t) >= 4 and t not in {"conta", "corrente", "banco"}
        ]
        hit = _contains_phrase(work_norm, aname) or any(t in work_norm.split() for t in a_tokens)
        if not hit:
            continue
        already_card = bool(matched_card_tokens & set(aname.split())) and not explicit_account
        if not already_card:
            filters.account_ids.append(account.id)
            filters.account_names.append(account.name)
            matched_rules.append(f"account:{account.name}")

    for tok in matched_card_tokens | {
        t for an in filters.account_names for t in normalize(an).split()
    }:
        if len(tok) >= 3:
            work_norm = _strip_phrase(work_norm, tok)

    for person in sorted(index.people, key=lambda p: -len(p)):
        pnorm = normalize(person)
        ptoks = [t for t in pnorm.split() if len(t) >= 3]
        if _contains_phrase(work_norm, pnorm) or any(t in work_norm.split() for t in ptoks):
            filters.people.append(person)
            matched_rules.append(f"person:{person}")
            for t in ptoks:
                work_norm = _strip_phrase(work_norm, t)
    return work_norm


def _extract_categories_and_terms(
    work_norm: str, index: UserEntityIndex, filters: QueryFilters, matched_rules: list[str]
) -> None:
    words = [w for w in work_norm.split() if w and w not in _FILTER_NOISE and not w.isdigit()]
    phrase = " ".join(words)

    cat_by_norm = {normalize(c.name): c for c in index.categories}
    matched_cat_words: set[str] = set()
    for cname, cat in sorted(cat_by_norm.items(), key=lambda kv: -len(kv[0])):
        c_parts = cname.split()
        if _contains_phrase(phrase, cname):
            filters.category_ids.append(cat.id)
            filters.category_names.append(cat.name)
            matched_cat_words.update(c_parts)
            matched_rules.append(f"category:{cat.name}")
        elif any(
            len(w) >= 4
            and any(
                cw.startswith(w) or (w.startswith(cw) and len(w) - len(cw) <= 2) for cw in c_parts
            )
            for w in words
        ):
            filters.category_ids.append(cat.id)
            filters.category_names.append(cat.name)
            for w in words:
                if len(w) >= 4 and any(cw.startswith(w) or w.startswith(cw) for cw in c_parts):
                    matched_cat_words.add(w)
            matched_rules.append(f"category_prefix:{cat.name}")

    remaining_words = [w for w in words if w not in matched_cat_words and len(w) >= 2]
    all_desc_norm = [
        normalize(d)
        for d in (
            *index.expense_descriptions,
            *index.income_descriptions,
            *index.recurring_descriptions,
        )
    ]
    all_desc_tokens = [d.split() for d in all_desc_norm]

    def _desc_matches_word(word: str) -> bool:
        for toks in all_desc_tokens:
            if word in toks:
                return True
            if len(word) >= 4 and any(tok.startswith(word) for tok in toks):
                return True
            if len(word) >= 6 and any(word in tok for tok in toks):
                return True
        return False

    matched_desc_terms: list[str] = []
    if remaining_words:
        rem_phrase = " ".join(remaining_words)
        if len(rem_phrase) >= 3 and any(f" {rem_phrase} " in f" {d} " for d in all_desc_norm):
            matched_desc_terms.append(rem_phrase)
        else:
            for w in sorted(remaining_words, key=len, reverse=True):
                if len(w) >= 3 and _desc_matches_word(w):
                    matched_desc_terms.append(w)

    if matched_desc_terms:
        filters.text_terms = matched_desc_terms
        matched_rules.append(f"text_terms:{','.join(matched_desc_terms)}")
    elif remaining_words and not filters.category_ids:
        rem_phrase = " ".join(remaining_words)
        std_cat = core.keyword_category(rem_phrase)
        for candidate in (std_cat, core.FALLBACK.get(std_cat or "")):
            if candidate and normalize(candidate) in cat_by_norm:
                cat = cat_by_norm[normalize(candidate)]
                filters.category_ids.append(cat.id)
                filters.category_names.append(cat.name)
                matched_rules.append(f"category_dict:{cat.name}")
                break
        if not filters.category_ids and not filters.has_data_filters():
            filters.unresolved_subject = rem_phrase


def extract_filters(
    text: str,
    rest_after_period: str,
    index: UserEntityIndex,
) -> tuple[QueryFilters, str, list[str]]:
    """Extrai todos os filtros combináveis sem que um anule o outro."""
    matched_rules: list[str] = []
    filters = QueryFilters()

    af, work = extract_amount_filter(rest_after_period)
    filters.amount = af
    if af.raw_expr:
        matched_rules.append(f"amount:{af.raw_expr}")

    work_norm = _extract_payment_methods(normalize(work), filters, matched_rules)
    _extract_status_flags(work_norm, filters, matched_rules)
    work_norm = _extract_projects(work_norm, index, filters, matched_rules)
    work_norm = _extract_cards_accounts_people(text, work_norm, index, filters, matched_rules)
    _extract_categories_and_terms(work_norm, index, filters, matched_rules)

    return filters, work_norm, matched_rules
