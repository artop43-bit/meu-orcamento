"""Compilador de QueryPlan composicional: combina intenção, domínio, filtros e agrupamento."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services.bot.contracts import PeriodSpec, QueryPlan
from app.services.bot.lexicon import intents
from app.services.bot.months import add_months, month_of
from app.services.bot.nlu.corrector import entry_guess, fix_typos, user_own_words
from app.services.bot.nlu.filters import UserEntityIndex, extract_filters, load_entity_index
from app.services.bot.nlu.periods import (
    default_all_time,
    default_year,
    extract_periods,
)
from app.services.bot.text_utils import normalize, plain


def _alt(terms: list[str]) -> re.Pattern[str]:
    ordered = sorted({t for t in terms if t}, key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered) + r")\b"
    )


_LOCATE_RE = _alt(intents.LOCATE_RECORD_TRIGGERS)
_NAV_HINT_RE = _alt(intents.NAVIGATE_HINT_WORDS)
_MOST_RE = _alt(intents.MOST_TRIGGERS)
_LEAST_RE = _alt(intents.LEAST_TRIGGERS)
_PERCENT_RE = re.compile(
    r"(?:%|\b(?:"
    + "|".join(
        re.escape(t).replace(r"\ ", r"\s+")
        for t in sorted(intents.PERCENT_TRIGGERS, key=len, reverse=True)
        if t != "%"
    )
    + r")\b)"
)
_COUNT_RE = _alt(intents.COUNT_TRIGGERS)
_AVG_RE = _alt(intents.AVERAGE_TRIGGERS)
_PER_DAY_RE = _alt(intents.PER_DAY_TRIGGERS)
_PER_WEEK_RE = _alt(intents.PER_WEEK_TRIGGERS)
_COMPARE_RE = _alt(intents.COMPARE_TRIGGERS)
_SERIES_RE = _alt(intents.SERIES_TRIGGERS)
_LIST_RE = _alt(intents.LIST_RECORDS_TRIGGERS)
_GREETING_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(t) for t in sorted(intents.GREETINGS, key=len, reverse=True))
    + r")$"
)
_CASUAL_GREETING_RE = re.compile(
    r"^(?:"
    + "|".join(
        re.escape(t).replace(r"\ ", r"\s+")
        for t in sorted(intents.GREETING_STARTERS, key=len, reverse=True)
    )
    + r")(?:\s+(?:"
    + "|".join(
        re.escape(t).replace(r"\ ", r"\s+")
        for t in sorted(intents.GREETING_TAIL_WORDS, key=len, reverse=True)
    )
    + r")){1,3}$"
)
_THANKS_RE = re.compile(
    r"^(?:muito\s+)?(?:"
    + "|".join(re.escape(t) for t in sorted(intents.THANKS, key=len, reverse=True))
    + r")(?:\s+mesmo|\s+demais)?$"
)

_SPEND_RE = re.compile(
    r"\bsaiu\b|\bsairam\b|\bsaid[ao]s?\b|\bgast(?:ei|ou|amos|ar|ando|aram|o|os|a)\b|"
    r"\bpaguei?\b|\bpagou\b|\bpagamos\b|\bpagar\b|\bpagando\b|\bpagaram\b|\bpago\b|\bpaga\b|"
    r"\bdespes\w*|\bcompr(?:ei|ou|amos|ar|ando|aram|a|as)\b|"
    r"\blanc(?:ei|ou|amos|ar|ando|aram|amento|amentos|ado|ada|ados|adas)\b|"
    r"\bdebit(?:o|os|ei|ou|ar)\b|\btorr(?:ei|ou|amos|ar|aram)\b|\bdesembols\w*|\bcust(?:ou|aram)\b|"
    r"\bpedi\b|\bpedimos\b"
)
_INCOME_RE = re.compile(
    r"\breceb\w*|\bsalario\w*|\brenda\w*|\breceita\w*|\bganhei\b|\bganhamos\b|\bganho\b|\bganhos\b|"
    r"\bentrou\b|\bentraram\b|\bentrada\w*|\bfatur(?:ei|ou|amos|ar|amento)\b|\bprovento\w*|\bremunerac\w*|\bfreela\w*"
)
_DOMAIN_NOUN_RE = re.compile(
    r"\b(?:orcamento|categoria|categorias|cartao|cartoes|fatura|faturas|limite|conta|contas|saldo|"
    r"transferencia|transferencias|parcela|parcelas|parcelado|financiamento|financiamentos|"
    r"emprestimo|emprestimos|divida|dividas|divisao|divisoes|meta|metas|desafio|desafios|"
    r"investimento|investimentos|investido|patrimonio|recorrencia|recorrencias|assinatura|"
    r"assinaturas|projeto|projetos|dedutivel|dedutiveis|irpf|mei|vence|vencem|vencimento|"
    r"atrasada|atrasadas|atrasado|revisar|revisao|planejado|planejados|pix|debito|credito|"
    r"boleto|dinheiro|lancamento|lancamentos|despesa|despesas|receita|receitas|renda|salario|"
    r"gasto|gastos|compra|compras|economia|economizei|poupei|guardei|sobrou|sobra|posso gastar|"
    r"pagamento|pagamentos|forma de pagamento|meio de pagamento|mais\s+pes(?:a|ou)|pes(?:a|ou)\s+(?:mais|no)|"
    r"registrei|cadastrei|anotei|disponivel|pendente|pendentes|vencido|vencida|atraso|mensalidade|mensalidades|"
    r"comprometimento|comprometido|comprometida)\b"
)
_NAV_INTENT_CUE_RE = re.compile(
    r"^(?:onde|aonde|cade|como|em que tela|qual tela|tem como|abrir|acessar|ir para)\b|"
    r"\b(?:tela|pagina|aba|menu|secao|configuracao|configuracoes|ajuste|ajustes)\b"
)
_OFF_TOPIC_RES = [re.compile(p) for p in intents.OFF_TOPIC_PATTERNS]

_GROUPING_RES = {dim: _alt(terms) for dim, terms in intents.GROUPING_TRIGGERS.items()}
_WEEKDAY_RE = _GROUPING_RES["weekday"]

_GROUP_ORDER = [
    "weekday",
    "quarter",
    "semester",
    "year",
    "month",
    "week",
    "day",
    "category",
    "place",
    "payment_method",
    "card",
    "account",
    "project",
    "person",
    "status",
]


def _detect_grouping(text: str, rest: str, weekday_hit: bool, filters: Any) -> str | None:
    if weekday_hit:
        return "weekday"

    def _allowed(dim: str) -> bool:
        dim_terms = "|".join(re.escape(t) for t in intents.GROUPING_TRIGGERS[dim])
        explicit_ask = bool(
            re.search(
                rf"\b(?:qual|quais|por|cada)\s+(?:o\s+|a\s+|os\s+|as\s+)?(?:{dim_terms})\b", text
            )
        )
        if dim == "card" and filters.card_ids and not explicit_ask:
            return False
        if dim == "account" and filters.account_ids and not explicit_ask:
            return False
        if dim == "project" and filters.project_ids and not explicit_ask:
            return False
        if dim == "category" and filters.category_ids and not explicit_ask:
            return False
        if dim == "payment_method" and filters.payment_methods and not explicit_ask:
            return False
        return True

    for dim in _GROUP_ORDER:
        if _allowed(dim) and _GROUPING_RES[dim].search(rest):
            return dim
    for dim in _GROUP_ORDER:
        if dim not in {"year", "quarter", "semester", "month", "week", "day"}:
            if _allowed(dim) and _GROUPING_RES[dim].search(text):
                return dim
    return None


def _is_rank_question(text: str, rest: str, grouping: str | None) -> bool:
    if not grouping:
        return False
    if grouping in {"year", "month", "week", "day", "quarter", "semester"}:
        dim_terms = "|".join(re.escape(t) for t in intents.GROUPING_TRIGGERS[grouping])
        if re.search(
            rf"\b(?:qual|quais|que|em que|em qual)\s+(?:foi\s+)?(?:o\s+|a\s+|os\s+|as\s+)?(?:pior\s+|melhor\s+|maior\s+|menor\s+)?(?:{dim_terms})\b",
            text,
        ) and (_MOST_RE.search(text) or _LEAST_RE.search(text)):
            return True
        if re.search(
            rf"\b(?:{dim_terms})\s+(?:em\s+)?(?:que|onde|com)\s+(?:eu\s+)?(?:mais|menos|maior|menor)\b",
            text,
        ):
            return True
        if re.search(rf"\b(?:pior|melhor|maior|menor)\s+(?:{dim_terms})\b", text):
            return True
        return False
    if re.search(r"\b(?:qual|quais|em que|em qual)\b", text) and (
        _MOST_RE.search(text) or _LEAST_RE.search(text)
    ):
        return True
    if grouping == "weekday" and (_MOST_RE.search(text) or _LEAST_RE.search(text)):
        return True
    if grouping in {"place", "category", "card", "account", "payment_method", "project"} and (
        re.search(r"\bonde\s+(?:eu\s+)?(?:mais|menos)\b", text)
        or re.search(r"\b(?:com o que|em que)\s+(?:eu\s+)?(?:mais|menos)\b", text)
    ):
        return True
    return False


def _detect_limit(text: str) -> int:
    if m := re.search(r"\btop\s+(\d{1,2})\b", text):
        return max(1, min(int(m[1]), 20))
    if m := re.search(
        r"\b(\d{1,2})\s+(?:maiores|menores|ultimos|ultimas|primeiros|primeiras)\b", text
    ):
        return max(1, min(int(m[1]), 20))
    return 5


def _sanitize_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    sanitized = dict(context)
    for field in ("intent", "domain", "grouping", "order"):
        if field in sanitized and not isinstance(sanitized[field], str):
            sanitized.pop(field)
    for field in (
        "category_names",
        "card_names",
        "account_names",
        "project_names",
        "payment_methods",
        "text_terms",
    ):
        value = sanitized.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            sanitized.pop(field, None)
    return sanitized


def _apply_followup_context(context: dict[str, Any], filters: Any, index: UserEntityIndex) -> None:
    if filters.period is None and context.get("period"):
        filters.period = PeriodSpec.load(context["period"])
    if filters.has_data_filters():
        return
    for name_key, id_key, entities in (
        ("category_names", "category_ids", index.categories),
        ("card_names", "card_ids", index.cards),
        ("account_names", "account_ids", index.accounts),
        ("project_names", "project_ids", index.projects),
    ):
        if context.get(name_key) and not getattr(filters, name_key):
            id_map = {e.name: e.id for e in entities}
            names = list(context[name_key])
            setattr(filters, name_key, names)
            setattr(filters, id_key, [id_map[n] for n in names if n in id_map])
    if context.get("payment_methods") and not filters.payment_methods:
        filters.payment_methods = list(context["payment_methods"])
    if context.get("text_terms") and not filters.text_terms:
        filters.text_terms = list(context["text_terms"])


def _match_locate_or_navigate(
    norm_full: str,
    corrected: str,
    filters: Any,
    has_domain_signal: bool,
    spends: bool,
    earns: bool,
    context: dict[str, Any] | None,
    matched_rules: list[str],
    make_plan: Any,
) -> tuple[QueryPlan, UserEntityIndex] | None:
    is_rank_where = bool(
        re.search(
            r"\bonde\s+(?:eu\s+)?(?:mais|menos)\b|\bonde\s+(?:eu\s+)?(?:gastei|paguei|comprei|recebi)\s+(?:mais|menos)\b",
            norm_full,
        )
    )
    has_locate_cue = not is_rank_where and (
        bool(_LOCATE_RE.search(norm_full))
        or bool(
            re.match(
                r"^(?:onde|aonde|cade|localiz[aeo]|localizar|ach[ae]|procur[ae]|encontr[ae]|busc[ae]|busque)\b",
                norm_full,
            )
        )
    )
    if has_locate_cue:
        has_record_words = bool(
            re.search(
                r"\b(?:lancamento|gasto|compra|despesa|receita|pagamento|transferencia|boleto|aquele|aquela)\b",
                norm_full,
            )
        )
        has_specific_data = (
            filters.amount.target_amount is not None
            or filters.amount.min_amount is not None
            or filters.amount.max_amount is not None
            or bool(filters.text_terms)
            or bool(filters.people)
            or bool(filters.card_ids)
            or bool(filters.project_ids)
            or bool(filters.payment_methods)
            or filters.period is not None
        )
        has_nav_hint = bool(_NAV_HINT_RE.search(norm_full))
        is_ui_nav_phrase = bool(
            re.match(
                r"^(?:onde\s+(?:encontro|vejo|fica|ficam|mudo|altero|troco|configuro|cadastro|exporto|importo|instalo|peco|crio|divido|abro|acesso))\b",
                norm_full,
            )
        )
        if (
            (
                has_record_words
                or has_specific_data
                or re.match(
                    r"^(?:cade|onde esta|onde lancei|onde cadastrei|onde registrei|em qual mes|localiz[aeo]|localizar|ach[ae]|procur[ae]|encontr[ae]|busc[ae]|busque)\b",
                    norm_full,
                )
            )
            and not has_nav_hint
            and not (is_ui_nav_phrase and not has_record_words and not has_specific_data)
        ):
            if has_domain_signal or has_record_words or has_specific_data:
                matched_rules.append("route:locate_record")
                return make_plan("locate_record", dom="all")
        if not has_specific_data and not has_record_words:
            from app.services.bot.engine.specials import navigate as _nav_check

            if _nav_check(corrected) is not None:
                matched_rules.append("route:navigate")
                return make_plan("navigate", dom="entity")

    if re.search(r"\b(?:mais\s+proxim[oa]|perto\s+de)\b", norm_full):
        if filters.amount.target_amount is not None:
            filters.amount.tolerance_pct = max(filters.amount.tolerance_pct, Decimal("0.35"))
            matched_rules.append("route:locate_by_closest_amount")
            return make_plan("locate_record", dom="all")
        if not context:
            matched_rules.append("route:unknown_vague_amount")
            return make_plan("fallback", dom="entity")

    if (
        re.match(r"^(?:como|em que tela|qual tela|tem como)\b", norm_full)
        and not spends
        and not earns
        and (
            not filters.has_data_filters()
            or re.match(
                r"^como\s+(?:cadastro|crio|configuro|adiciono|mudo|altero|troco)\b", norm_full
            )
        )
        and not re.match(
            r"^como (?:esta|estao|anda|andam|vai|vao|foi|foram|fiquei|ficou)\b", norm_full
        )
    ):
        from app.services.bot.engine.specials import navigate as _nav_check

        if _nav_check(corrected) is not None:
            matched_rules.append("route:navigate_how")
            return make_plan("navigate", dom="entity")
    return None


def _match_special_route(
    norm_full: str,
    corrected: str,
    filters: Any,
    spends: bool,
    earns: bool,
    matched_rules: list[str],
    make_plan: Any,
) -> tuple[QueryPlan, UserEntityIndex] | None:
    if re.search(r"\bmelhor dia\b", norm_full) and re.search(r"\bcart|\bfatura", norm_full):
        matched_rules.append("route:cards_best_day")
        return make_plan("cards", dom="entity")

    if re.search(
        r"\bposso gastar\b|\bdisponivel hoje\b|\blivre hoje\b|\borcamento diario\b|"
        r"\btenho para gastar\b|\bsobra para gastar\b|\bqual meu disponivel\b|\bsaldo livre\b",
        norm_full,
    ) and not re.search(r"\bcart|\bfatura", norm_full):
        matched_rules.append("route:can_spend")
        return make_plan("can_spend", dom="entity")

    if (
        filters.period is not None
        and filters.period.day_start is not None
        and not filters.has_data_filters()
        and re.search(
            r"\b(?:lancei|lancado|registrei|cadastrei)\s+algo\b|"
            r"\bo que (?:eu )?(?:lancei|foi lancado|registrei|cadastrei|anotei)\b",
            norm_full,
        )
    ):
        matched_rules.append("route:logged")
        return make_plan("logged", dom="all")

    if (
        filters.needs_review is True
        and not _MOST_RE.search(norm_full)
        and not _COUNT_RE.search(norm_full)
    ):
        matched_rules.append("route:review_pending")
        return make_plan("review_pending", dom="expense")

    if filters.deductible is not None and not _LIST_RE.search(norm_full):
        matched_rules.append("route:tax_deductible")
        return make_plan("tax_deductible", dom="expense")

    if filters.mei is True and not _LIST_RE.search(norm_full):
        matched_rules.append("route:mei")
        return make_plan("mei", dom="income")

    if re.search(
        r"\bme dev|\bquem (?:me )?deve\b|\bemprestei\b|\bdevo (?:pr[oa]|ao)\b|\bdivis(?:ao|oes)\b|\bracha\b|"
        r"\blucr\w* com (?:os |meus )?emprestimo|\bjuros (?:que )?(?:ja )?(?:recebi|ganhei)\b|"
        r"\brendeu (?:os |meus )?emprestimo",
        norm_full,
    ) or (
        filters.people
        and (
            not spends
            or re.search(r"\b(?:me pagar|emprestimo|falta|deve|devendo|divisao)\b", norm_full)
        )
    ):
        matched_rules.append("route:friend_loans")
        return make_plan("friend_loans", dom="entity")

    simple_rules: list[tuple[str, bool, str, str, str]] = [
        (
            "route:transfers",
            bool(re.search(r"\btransferenc|\btransferi\b", norm_full)) and not filters.category_ids,
            "transfers",
            "entity",
            "",
        ),
        (
            "route:net_worth",
            bool(re.search(r"\bpatrimonio\b|\bbens e dividas\b", norm_full)),
            "net_worth",
            "entity",
            "",
        ),
        ("route:challenges", bool(re.search(r"\bdesafio", norm_full)), "challenges", "entity", ""),
        (
            "route:goals",
            bool(re.search(r"\bmeta|\bobjetivo|\bquanto falta para\b", norm_full))
            and not re.search(r"\bparcela", norm_full),
            "goals",
            "entity",
            "",
        ),
        (
            "route:planned",
            bool(
                re.search(
                    r"\bplanejad|\bgasto previsto|\bdespesa prevista|\bprevisto para\b", norm_full
                )
            ),
            "planned",
            "entity",
            "",
        ),
        (
            "route:investments",
            bool(
                re.search(
                    r"\binvest|\baplicad|\baplicac|\bacao\b|\bacoes\b|\bcdb\b|\btesouro\b|\bticker\b",
                    norm_full,
                )
            ),
            "investments",
            "entity",
            "",
        ),
        (
            "route:loans",
            bool(
                re.search(
                    r"\bfinanciament|\bemprestimo|\bdivida|\bsaldo devedor\b|\boutra divida",
                    norm_full,
                )
            )
            and not re.search(r"\bcart", norm_full),
            "loans",
            "entity",
            "",
        ),
        (
            "route:invoices",
            bool(re.search(r"\bfatura", norm_full))
            and not _COUNT_RE.search(norm_full)
            and not _SERIES_RE.search(norm_full),
            "invoices",
            "entity",
            "",
        ),
        (
            "route:cards",
            bool(
                re.search(
                    r"\blimite\b|\bcartoes\b|\bdevo no cartao\b|\busei do cartao\b|\bdisponivel no cartao\b",
                    norm_full,
                )
            )
            and not _MOST_RE.search(norm_full)
            and not _LEAST_RE.search(norm_full)
            and not spends,
            "cards",
            "entity",
            "",
        ),
        (
            "route:installments",
            bool(re.search(r"\bparcela|\bparcelad", norm_full))
            and not _MOST_RE.search(norm_full)
            and not _COUNT_RE.search(norm_full)
            and not spends,
            "installments",
            "expense",
            "",
        ),
        (
            "route:due_overdue",
            filters.overdue is True
            and not _COUNT_RE.search(norm_full)
            and not _MOST_RE.search(norm_full),
            "due",
            "expense",
            "",
        ),
        (
            "route:due",
            bool(
                re.search(
                    r"\bvenc|\ba pagar\b|\bpra pagar\b|\bpara pagar\b|\bpendente|\bem atraso\b",
                    norm_full,
                )
            )
            and "fatura" not in norm_full
            and not _COUNT_RE.search(norm_full),
            "due",
            "expense",
            "",
        ),
        (
            "route:recurring",
            bool(
                re.search(
                    r"\bassinatura|\brecorren|\bdespesas? fixas?\b|\bcontas? fixas?\b|\bmensalidade",
                    norm_full,
                )
            )
            and not re.search(r"\bquanto (?:eu )?(?:gastei|paguei)\b", norm_full)
            and not _COUNT_RE.search(norm_full),
            "recurring",
            "entity",
            "",
        ),
        (
            "route:projects",
            bool(re.search(r"\bprojeto", norm_full))
            and not spends
            and not _MOST_RE.search(norm_full)
            and not _COUNT_RE.search(norm_full),
            "projects",
            "entity",
            "",
        ),
        (
            "route:salary",
            bool(re.search(r"\bsalario\b", norm_full))
            and not spends
            and not _PERCENT_RE.search(corrected)
            and not _COUNT_RE.search(norm_full)
            and not _MOST_RE.search(norm_full)
            and not _LEAST_RE.search(norm_full),
            "salary",
            "income",
            "",
        ),
    ]
    for rule_tag, cond, intent_name, dom, _ in simple_rules:
        if cond:
            matched_rules.append(rule_tag)
            return make_plan(intent_name, dom=dom)

    if (
        re.search(r"\bsaldo\b|\bcontas bancarias\b|\bsaldo das contas\b", norm_full)
        and not spends
        and not earns
    ):
        if re.search(r"\bconta|\bbanc|\bcarteira|\bpoupanca", norm_full):
            matched_rules.append("route:accounts")
            return make_plan("accounts", dom="entity")
        matched_rules.append("route:balance")
        return make_plan("balance", dom="balance")

    if re.search(
        r"\bsobr|\bfaltou|\bbalanco|\bfechei|\beconom|\bpoupei|\bguardei|\bresultado do mes\b|\bcomo fiquei\b",
        norm_full,
    ):
        matched_rules.append("route:balance")
        return make_plan("balance", dom="balance")

    if re.search(r"\bquanto devo\b", norm_full) and not spends:
        matched_rules.append("route:loans_general")
        return make_plan("loans", dom="entity")

    return None


def _match_analytic_route(
    norm_full: str,
    corrected: str,
    rest: str,
    filters: Any,
    grouping: str | None,
    current: date,
    spends: bool,
    earns: bool,
    has_explicit_filter: bool,
    has_domain_noun: bool,
    followup: bool,
    context: dict[str, Any] | None,
    target_domain: str,
    matched_rules: list[str],
    make_plan: Any,
) -> tuple[QueryPlan, UserEntityIndex]:
    explicit_least_phrase = bool(
        re.search(
            r"\bmais\s+(?:barat[oa]s?|baix[oa]s?|leves?|enxut[oa]s?|economic[oa]s?|tranquil[oa]s?)\b",
            norm_full,
        )
    )
    order = (
        "least"
        if explicit_least_phrase or (_LEAST_RE.search(norm_full) and not _MOST_RE.search(norm_full))
        else "most"
    )

    if _PERCENT_RE.search(corrected):
        matched_rules.append("route:percent")
        of_income = (
            earns or "renda" in norm_full or "salario" in norm_full or "compromet" in norm_full
        )
        return make_plan("percent", dom="expense", grp="of_income" if of_income else "of_expense")

    if earns and spends and not _COUNT_RE.search(norm_full) and not _SERIES_RE.search(norm_full):
        matched_rules.append("route:balance_both")
        return make_plan("balance", dom="balance")

    if _COUNT_RE.search(norm_full):
        matched_rules.append("route:count")
        return make_plan("count")

    if _SERIES_RE.search(norm_full):
        grp = grouping or "month"
        matched_rules.append(f"route:series({grp})")
        return make_plan("series", grp=grp)

    if _PER_DAY_RE.search(norm_full):
        matched_rules.append("route:avg_per_day")
        return make_plan("avg", grp="day")

    if _PER_WEEK_RE.search(norm_full):
        matched_rules.append("route:avg_per_week")
        return make_plan("avg", grp="week")

    if _AVG_RE.search(norm_full):
        matched_rules.append("route:avg")
        return make_plan("avg", grp=grouping or "month")

    if _is_rank_question(norm_full, normalize(rest), grouping):
        if grouping == "year" and filters.period is None:
            filters.period = default_all_time(current)
        elif grouping == "month" and filters.period is None:
            filters.period = default_year(current)
        elif grouping == "weekday" and filters.period is None:
            filters.period = PeriodSpec(
                add_months(current, -2), current, "nos últimos 3 meses", explicit=False
            )
        matched_rules.append(f"route:rank_group({grouping},{order})")
        return make_plan("rank_group", grp=grouping, order=order)

    if (
        re.search(
            r"\bo que mais\b|\bcom o que (?:eu )?mais\b|\bpesou mais\b|\bpesa mais\b|\bo que menos\b|"
            r"\bonde (?:eu )?(?:mais|menos) gast|\bem que (?:eu )?(?:mais|menos) gast|\bem que (?:eu )?gasto mais\b|"
            r"\b(?:com o que|em que|onde)\s+(?:eu\s+)?(?:gastei|gasto|paguei|comprei)\s+(?:mais|menos)\b",
            norm_full,
        )
        and not filters.category_ids
        and not filters.text_terms
    ):
        matched_rules.append("route:rank_group_category")
        return make_plan("rank_group", grp="category", order=order)

    if (
        re.search(
            r"\b(?:maior|maiores|menor|menores|mais car[oa]|mais barat[oa]|mais alt[oa]|mais baix[oa])\s+(?:gasto|gastos|despesa|despesas|compra|compras|lancamento|lancamentos|pix|receita|receitas|entrada|entradas|saida|saidas|debito|debitos)\b",
            norm_full,
        )
        or re.search(
            r"\b(?:gasto|despesa|compra|lancamento|receita)s?\s+mais\s+(?:car|barat|alt|baix)",
            norm_full,
        )
        or re.search(r"\bquando\b.*\b(?:mais|menos)\b", norm_full)
        or (
            re.search(r"\b(?:maior|menor|top\s+\d+)\b", norm_full)
            and (spends or earns or filters.has_data_filters())
        )
    ):
        if filters.period is None:
            filters.period = (
                default_year(current) if "ano" in norm_full else default_all_time(current)
            )
        matched_rules.append(f"route:extreme_item({order})")
        return make_plan("extreme_item", order=order)

    if re.search(
        r"\bultim[oa]s?\s+(?:vez|compra|gasto|despesa|lancamento|pagamento|saida|receita|salario|entrada|recebimento|pix|transferencia)\b",
        norm_full,
    ):
        matched_rules.append("route:latest_item")
        return make_plan("latest_item")

    if (
        _LIST_RE.search(norm_full)
        or filters.amount.min_amount is not None
        or filters.amount.max_amount is not None
    ) and not re.search(r"\bquanto\b", norm_full):
        matched_rules.append("route:list_records")
        return make_plan("list_records")

    if followup and context and context.get("intent"):
        prev_intent = str(context["intent"])
        if prev_intent in {
            "sum",
            "count",
            "avg",
            "extreme_item",
            "rank_group",
            "series",
            "percent",
            "balance",
            "list_records",
            "locate_record",
            "incomes",
        }:
            matched_rules.append(f"route:followup({prev_intent})")
            return make_plan(
                prev_intent,
                dom=str(context.get("domain") or target_domain),
                grp=context.get("grouping"),
                order=str(context.get("order") or order),
            )

    if (
        spends
        or earns
        or has_explicit_filter
        or (has_domain_noun and norm_full.startswith("quanto"))
    ):
        matched_rules.append("route:sum")
        return make_plan("sum")

    matched_rules.append("route:unknown_fallback")
    return make_plan("fallback", dom="entity")


def build_plan(
    db: Session,
    user: User,
    question: str,
    today: date,
    context: dict[str, Any] | None = None,
    entity_index: UserEntityIndex | None = None,
) -> tuple[QueryPlan, UserEntityIndex]:
    index = entity_index or load_entity_index(db, user.id)
    context = _sanitize_context(context)
    current = month_of(today, user.month_start_day)
    raw_plain = plain(question[:300])
    cleaned = re.sub(r"\s+", " ", re.sub(r"[?!.,;:]+", " ", raw_plain)).strip()

    if not cleaned or _GREETING_RE.fullmatch(cleaned) or _CASUAL_GREETING_RE.fullmatch(cleaned):
        return (
            QueryPlan(
                intent="help",
                normalized_question=cleaned,
                corrected_question=cleaned,
                matched_rules=["greeting_or_empty"],
            ),
            index,
        )

    if _THANKS_RE.fullmatch(cleaned):
        return (
            QueryPlan(
                intent="thanks",
                normalized_question=cleaned,
                corrected_question=cleaned,
                matched_rules=["thanks"],
            ),
            index,
        )

    fixed_raw = fix_typos(raw_plain, lambda: user_own_words(db, user.id))
    if entry_kind := entry_guess(fixed_raw):
        return (
            QueryPlan(
                intent="entry_redirect",
                domain=entry_kind,
                normalized_question=cleaned,
                corrected_question=fixed_raw,
                matched_rules=[f"entry_guess:{entry_kind}"],
            ),
            index,
        )

    corrected = fix_typos(cleaned, lambda: user_own_words(db, user.id))
    weekday_hit = bool(_WEEKDAY_RE.search(corrected))
    text_no_weekday = " ".join(
        (_WEEKDAY_RE.sub(" ", corrected) if weekday_hit else corrected).split()
    )

    p1, p2, rest = extract_periods(text_no_weekday, current, today, user.month_start_day)
    filters, _, matched_rules = extract_filters(corrected, rest, index)
    filters.period = p1
    filters.period2 = p2
    if p1:
        matched_rules.append(f"period:{p1.label}")
    if p2:
        matched_rules.append(f"period2:{p2.label}")

    followup = isinstance(context, dict) and bool(re.match(r"^e\b", corrected))
    if followup and context:
        matched_rules.append("followup_context")
        _apply_followup_context(context, filters, index)

    norm_full = normalize(corrected)
    spends = bool(_SPEND_RE.search(norm_full))
    earns = bool(_INCOME_RE.search(norm_full))
    limit = _detect_limit(norm_full)
    grouping = _detect_grouping(norm_full, normalize(rest), weekday_hit, filters)

    if any(pat.search(norm_full) or pat.search(raw_plain) for pat in _OFF_TOPIC_RES):
        matched_rules.append("route:out_of_scope_explicit")
        return (
            QueryPlan(
                intent="out_of_scope",
                domain="entity",
                normalized_question=cleaned,
                corrected_question=corrected,
                matched_rules=matched_rules,
            ),
            index,
        )

    dict_only_category = any(r.startswith("category_dict:") for r in matched_rules) and not any(
        r.startswith(
            (
                "category:",
                "category_prefix:",
                "card:",
                "account:",
                "project:",
                "person:",
                "payment:",
                "text_terms:",
                "amount:",
            )
        )
        for r in matched_rules
    )
    has_domain_noun = bool(_DOMAIN_NOUN_RE.search(norm_full))
    has_explicit_filter = filters.has_data_filters() and not dict_only_category
    has_budget_time_rank = bool(
        grouping in {"year", "month", "week", "day", "weekday", "quarter", "semester"}
        and _is_rank_question(norm_full, normalize(rest), grouping)
        and re.search(
            r"\b(?:car[oa]s?|barat[oa]s?|pior(?:es)?|gast\w*|receb\w*|despes\w*|compr\w*|pes\w*)\b",
            norm_full,
        )
    )
    has_domain_signal = (
        spends
        or earns
        or has_domain_noun
        or has_explicit_filter
        or has_budget_time_rank
        or (followup and context is not None)
    )
    if dict_only_category and not (spends or earns or has_domain_noun):
        filters.category_ids.clear()
        filters.category_names.clear()
        matched_rules = [r for r in matched_rules if not r.startswith("category_dict:")]

    target_domain = (
        "balance" if (earns and spends) else ("income" if earns and not spends else "expense")
    )

    def make_plan(
        intent: str, *, dom: str | None = None, grp: str | None = None, order: str = "most"
    ) -> tuple[QueryPlan, UserEntityIndex]:
        return (
            QueryPlan(
                intent=intent,
                domain=dom or target_domain,
                grouping=grp,
                order=order,
                limit=limit,
                filters=filters,
                normalized_question=cleaned,
                corrected_question=corrected,
                matched_rules=matched_rules,
                followup=followup,
            ),
            index,
        )

    if (
        re.search(r"^(?:o que|com o que)\s+(?:mais|menos)\b", norm_full)
        and filters.unresolved_subject
        and not spends
        and not earns
        and not has_domain_noun
    ):
        matched_rules.append("route:clarify_vague")
        return make_plan("clarify", dom="entity")

    if nav_or_loc := _match_locate_or_navigate(
        norm_full,
        corrected,
        filters,
        has_domain_signal,
        spends,
        earns,
        context,
        matched_rules,
        make_plan,
    ):
        return nav_or_loc

    if p2 is not None or _COMPARE_RE.search(norm_full):
        matched_rules.append("route:compare")
        return make_plan("compare")

    if special := _match_special_route(
        norm_full, corrected, filters, spends, earns, matched_rules, make_plan
    ):
        return special

    if not has_domain_signal:
        if _NAV_INTENT_CUE_RE.search(norm_full):
            from app.services.bot.engine.specials import navigate as _nav_check

            if _nav_check(corrected) is not None:
                matched_rules.append("route:navigate_direct")
                return make_plan("navigate", dom="entity")
        matched_rules.append("route:unknown_no_signal")
        return make_plan("fallback", dom="entity")

    return _match_analytic_route(
        norm_full,
        corrected,
        rest,
        filters,
        grouping,
        current,
        spends,
        earns,
        has_explicit_filter,
        has_domain_noun,
        followup,
        context,
        target_domain,
        matched_rules,
        make_plan,
    )
