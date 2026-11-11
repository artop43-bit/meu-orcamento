"""Entendimento por partes (v1.7.6), em cima do núcleo de linguagem (`lexicon.py`).

Três serviços para o Tire sua dúvida, todos locais e por regras:

- `fix_typos`: abreviações e erros de digitação comuns ("qto gastey no mes pasado").
- `entry_guess`: a frase é um lançamento ("gastei 50 no mercado", "uber 23 pix")? O bot não
  registra nada: ele encaminha para o Lançamento rápido.
- `parse`: separa a pergunta em partes (medida, agrupamento, direção, receita ou despesa), que
  o bot combina. É o que faz "qual ano mais gastei", "qual dia da semana gasto menos" e
  "quantos % da renda eu gastei" funcionarem sem uma regra escrita para cada frase.
"""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from app.services import lexicon
from app.services.category_words import WORDS


def _alt(terms: list[str]) -> str:
    """Alternativa de regex com os termos (os mais longos primeiro; espaço casa com espaços)."""
    ordered = sorted({t for t in terms if t}, key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)


# ---------------------------------------------------------------- correção de digitação

# Palavras comuns do português que não são erro de nada (não entram na correção).
_COMMON = set(
    """
    sobre entre desde contra durante depois antes agora ainda sempre nunca talvez quase muito pouco
    mesmo mesma outros outras outro outra todos todas todo toda cada qualquer nenhum nenhuma algum alguma
    minha minhas nossos nossas nosso nossa dele dela deles delas esse essa esses essas este esta estes estas
    aquele aquela aquilo isso isto aqui ali la onde quando como porque quanto quem qual quais
    fazer feito fazendo posso pode podem poder quero queria querer preciso precisa precisar gostaria
    tenho tinha temos tiver estou estava estao estamos fiquei ficou ficar foram fomos seria sendo
    saber sabia dizer disse falar falou olhar olhou achar achei acho pensar pensei mostrar ajudar ajuda
    coisa coisas pessoa pessoas gente tempo vezes parte lugar forma jeito tipo modo caso exemplo
    primeiro primeira segundo terceiro ultimo ultima proximo proxima grande pequeno pequena melhor pior
    certo certa errado errada verdade claro certeza problema duvida pergunta resposta motivo
    casa trabalho empresa familia amigo amiga amigos filho filha filhos esposa marido namorada namorado
    cidade estado brasil brasileiro pais mundo viagem semana manha tarde noite hora horas minuto
    dinheiro valor valores preco precos conta contas banco bancos nota notas numero numeros
    total geral final inicio comeco durante periodo passado futuro presente atual recente
    pagar pagando pagou ganhar ganhando gastar gastando comprar comprando vender vendendo
    janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro
    segunda terca quarta quinta sexta sabado domingo
    obrigado obrigada valeu beleza otimo legal perfeito tchau
    lancei lancou lancamos registrei registrou cadastrei cadastrou anotei anotou adicionei adicionou
    inclui incluiu inseri inseriu coloquei colocou salvei salvou marquei marcou criei criou
    recebia ganhava gastava pagava comprava vendia devia devendo sobrando faltando restando
    economizar economizando economizou poupar poupando guardar guardando investir investindo
    venceu vencendo vencida vencidas vencido vencidos atrasou atrasando fechou fechando fechamento
    """.split()
)


def _build_targets() -> tuple[set[str], dict[tuple[str, int], list[str]]]:
    known = set(lexicon.concept_words()) | _COMMON | set(lexicon.ABBREVIATIONS)
    targets = {word for word in lexicon.concept_words() if len(word) >= 6}
    for term in WORDS:
        if " " in term or "&" in term:
            known.update(term.split())
            continue
        known.add(term)
        if len(term) >= 7 and term.isalpha():
            targets.add(term)
    buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
    for word in targets:
        buckets[(word[0], len(word))].append(word)
    return known, buckets


_KNOWN, _BUCKETS = _build_targets()


def register_known(words: set[str]) -> None:
    """Palavras que outras regras já entendem (não são erro de digitação)."""
    _KNOWN.update(words)


def _within_one(a: str, b: str) -> bool:
    """Uma letra trocada, sobrando, faltando ou duas vizinhas invertidas."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]]
            and a[diff[1]] == b[diff[0]]
        )
    short, long = (a, b) if la < lb else (b, a)
    i = 0
    while i < len(short) and short[i] == long[i]:
        i += 1
    return short[i:] == long[i + 1 :]


def fix_typos(text: str, protected: Callable[[], set[str]] | None = None) -> str:
    """Troca abreviações e conserta erros de uma letra em palavras do núcleo. `protected` devolve
    as palavras do próprio usuário (descrições e categorias): essas nunca são corrigidas."""
    words = text.split()
    own: set[str] | None = None
    out: list[str] = []
    for word in words:
        if word in lexicon.ABBREVIATIONS:
            out.append(lexicon.ABBREVIATIONS[word])
            continue
        if len(word) < 6 or not word.isalpha() or word in _KNOWN:
            out.append(word)
            continue
        found = [
            candidate
            for size in (len(word) - 1, len(word), len(word) + 1)
            for candidate in _BUCKETS.get((word[0], size), ())
            if _within_one(word, candidate)
        ]
        if len(found) != 1:
            out.append(word)
            continue
        if protected is not None:
            if own is None:
                own = protected()
            if word in own:
                out.append(word)
                continue
        out.append(found[0])
    return " ".join(out)


# ---------------------------------------------------------------- é um lançamento?

_STARTERS = re.compile(rf"^(?:{_alt(lexicon.QUESTION_STARTERS)})\b")
_ASK = re.compile(rf"^(?:{_alt(lexicon.ASK_VERBS)})\b")
_ANALYTIC = re.compile(rf"\b(?:{_alt([*lexicon.ANALYTIC_WORDS, 'top', 'ranking'])})\b")
_QUERY_WORDS = re.compile(r"\b(?:meus?|minhas?|todos|todas|lista|resumo|relatorio|extrato)\b")
_POLITE = re.compile(
    r"^(?:por favor|favor|quero|queria|preciso|vou|pode|poderia|bora|vamos|gostaria de)\s+"
)
_COMMAND = re.compile(rf"^(?:{_alt(lexicon.ENTRY_COMMANDS)})\b")
_STRONG = re.compile(rf"^(?:{_alt([*lexicon.ENTRY_VERBS, *lexicon.INCOME_VERBS])})\b")
_SOFT = re.compile(rf"^(?:{_alt(lexicon.ENTRY_SOFT_VERBS)})\b")
_ENTRY_THING = re.compile(
    r"\b(?:despesa|despesas|gasto|gastos|receita|receitas|renda|compra|compras|lancamento|lancamentos|"
    r"pagamento|entrada|saida|conta)\b"
)
_NEW_THING = re.compile(
    r"^(?:nova|novo)\s+(?:despesa|receita|renda|compra|conta|lancamento|gasto)\b"
)
# Números que não são valor: datas, parcelas, anos e quantidades de tempo.
_NOT_AMOUNT = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\bdia\s+\d{1,2}\b|\b\d{1,3}\s*x\b|\b(?:em|de|desde|ate|ano)\s+20\d\d\b|"
    r"\b(?:ultim[oa]s?|proxim[oa]s?)\s+\d+\b|\b\d+\s*(?:dias?|meses|mes|semanas?|anos?|vezes|parcelas?|horas?)\b|"
    r"\b\d+\s*[oa]\b"
)
_AMOUNT = re.compile(r"(?<![\w/])(?:r\$\s*)?(\d+(?:[.,]\d+)*)(?:\s*(?:k|mil))?(?![\w/])")
_BEFORE_SUBJECT = {
    "com",
    "no",
    "na",
    "nos",
    "nas",
    "em",
    "de",
    "do",
    "da",
    "pro",
    "pra",
    "para",
    "ao",
}


def entry_guess(raw: str) -> str | None:
    """A frase (minúsculas, sem acento, com a pontuação original) é um lançamento?

    Devolve "amount" (tem valor: dá para preencher o Lançamento rápido), "command" (pede para
    registrar, sem valor) ou None (é uma pergunta)."""
    if "?" in raw:
        return None
    text = re.sub(r"[!;:]+", " ", raw)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if not text or re.match(r"e\b", text):
        return None
    plus = text.startswith("+")
    text = text.lstrip("+ ").strip()
    body = _POLITE.sub("", text)
    if _STARTERS.match(body) or _STARTERS.match(text):
        return None
    masked = _NOT_AMOUNT.sub(" ", body)
    amounts = list(_AMOUNT.finditer(masked))
    # "gastos com 99" ou "meus gastos no 99": o número é o assunto, não o valor.
    real = []
    for match in amounts:
        before = masked[: match.start()].split()
        if before and before[-1] in _BEFORE_SUBJECT and match.end() >= len(masked.rstrip()):
            continue
        real.append(match)
    has_amount = bool(real)
    command = _COMMAND.match(body) is not None
    if command and (has_amount or _ENTRY_THING.search(body)):
        return "amount" if has_amount else "command"
    if _NEW_THING.match(body):
        return "amount" if has_amount else "command"
    if not has_amount or _ANALYTIC.search(body):
        return None
    if plus or _STRONG.match(body):
        return "amount"
    if _ASK.match(body) or _QUERY_WORDS.search(body):
        return None
    if _SOFT.match(body):
        return "amount"
    # "mercado 120 pix ontem": descrição e valor, sem verbo.
    words = body.split()
    described = any(w.isalpha() and len(w) >= 2 for w in words)
    return "amount" if described and len(words) <= 8 else None


# ---------------------------------------------------------------- partes da pergunta

SPEND = (
    r"\bsaiu\b|\bsairam\b|\bgast|\bpague|\bdespes|\bcompr|\blancament|\bsaid[ao]s?\b|\bdebit|"
    r"\btorr(?:ei|ou|ar)\b|\bdesembols|\bcust(?:o|os|ou|aram)\b|\bconsum"
)
INCOME = r"\breceb|\bsalario|\brenda|\breceita|\bganh|\bentrou|\bentraram|\bentrada|\bfatur(?:ei|amento)\b|\bprovento|\bremunerac"
_PERCENT = re.compile(
    rf"(?:%|\b(?:{_alt([t for t in lexicon.CONCEPTS['percent'] if t != '%'])})\b)"
)
_COUNT = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['count'])})\b")
_SMALLEST = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['smallest'])})\b")
_LIST = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['list'])})\b")
_PER_DAY = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['per_day'])})\b")
_PER_WEEK = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['per_week'])})\b")
_WEEKDAY = re.compile(rf"\b(?:{_alt(lexicon.CONCEPTS['group_weekday'])})\b")
_PLACE = _alt(lexicon.CONCEPTS["group_place"])
_LEAST = re.compile(
    r"\bmenos\b|\bmenor(?:es)?\b|\bbarat|\bmelhor(?:es)?\b|\bbaix[oa]s?\b|\beconomi|\bleves?\b|\bminim"
)
_MOST = re.compile(
    r"\bmais\b|\bmaior(?:es)?\b|\bpior(?:es)?\b|\bcar[oa]s?\b|\balt[oa]s?\b|\bpesad|\brecorde|\bpico\b|\bauge\b|\bestour"
)
_TIME = r"dias?|datas?|semanas?|mes|meses|anos?"
_ASKING = r"(?:qual|quais|que|em que|em qual|em quais|quando foi)"
_ARTICLE = r"(?:(?:foi|foram|e|sao|eh)\s+)?(?:(?:o|a|os|as)\s+)?(?:(?:meu|minha|meus|minhas)\s+)?(?:(?:pior|melhor|maior|menor)\s+)?"
_RANK_TIME = [
    re.compile(rf"\b{_ASKING}\s+{_ARTICLE}({_TIME})\b"),
    re.compile(
        rf"\b({_TIME})\s+(?:em\s+)?(?:que|onde|com|de)\s+(?:eu\s+|a gente\s+)?(?:mais|menos|maior|menor)\b"
    ),
    re.compile(rf"\b({_TIME})\s+(?:mais|menos)\s+\w+"),
    re.compile(rf"\b(?:pior|melhor|maior|menor)(?:es)?\s+({_TIME})\b"),
]
_RANK_PLACE = [
    re.compile(rf"\b{_ASKING}\s+{_ARTICLE}({_PLACE})\b"),
    re.compile(
        rf"\b({_PLACE})\s+(?:em\s+)?(?:que|onde|com|de)\s+(?:eu\s+|a gente\s+)?(?:mais|menos|maior|menor)\b"
    ),
    re.compile(rf"\b({_PLACE})\s+(?:mais|menos)\s+\w+"),
]
# Assuntos com regra própria: "melhor dia de compra do cartão" não é ranking de dias.
_OTHER_TOPIC = re.compile(
    r"\bcart[ao]|\bfatura|\bvenc|\bfecha|\bmeta\b|\bmetas\b|\binvest|\bparcela|\bjuros\b|\bcdi\b|\bselic\b"
)
_COMPARE = re.compile(r"\bcompar|\bversus\b|\bvs\b|\bdo que\b|\bmais que\b|\bmenos que\b")
_GROUP_OF = {
    "dia": "day",
    "dias": "day",
    "data": "day",
    "datas": "day",
    "semana": "week",
    "semanas": "week",
}
_GROUP_OF |= {"mes": "month", "meses": "month", "ano": "year", "anos": "year"}
_LIST_GROUP = [("ano", "year"), ("semana", "week"), ("dia", "day"), ("mes", "month")]


@dataclass
class Parts:
    """O que a pergunta pede, em partes."""

    intent: str | None = None  # rank, percent, count, smallest, per, list
    grouping: str | None = None  # day, weekday, week, month, year, place
    order: str = "most"  # most, least
    domain: str = "expense"  # expense, income
    weekday: bool = False

    def dump(self) -> dict[str, str | None]:
        return {
            "intent": self.intent,
            "grouping": self.grouping,
            "order": self.order,
            "domain": self.domain,
        }

    @staticmethod
    def load(data: object) -> "Parts | None":
        if not isinstance(data, dict) or data.get("intent") not in {
            "rank",
            "percent",
            "count",
            "smallest",
            "per",
            "list",
        }:
            return None
        grouping = data.get("grouping")
        return Parts(
            str(data["intent"]),
            grouping if grouping in {"day", "weekday", "week", "month", "year", "place"} else None,
            "least" if data.get("order") == "least" else "most",
            "income" if data.get("domain") == "income" else "expense",
        )


def cut_weekday(text: str) -> tuple[str, bool]:
    """Tira "dia da semana" antes de procurar o período ("da semana" pareceria "nesta semana")."""
    match = _WEEKDAY.search(text)
    if not match:
        return text, False
    return (text[: match.start()] + " diasemana " + text[match.end() :]).strip(), True


def parse(text: str, rest: str, weekday: bool = False) -> Parts:
    """`text` é a pergunta inteira; `rest`, a pergunta sem o período."""
    spends = re.search(SPEND, text) is not None
    earns = re.search(INCOME, text) is not None
    domain = "income" if earns and not spends else "expense"
    least = _LEAST.search(text) is not None
    most = _MOST.search(text) is not None
    order = "least" if least else "most"
    if domain == "income":  # "melhor mês" de receita é o maior; de despesa, o menor
        order = "least" if re.search(r"\bmenos\b|\bmenor|\bpior|\bbaix", text) else "most"
    other = _OTHER_TOPIC.search(text) is not None

    if _PERCENT.search(text) and not other:
        return Parts(
            "percent", None, order, "income" if earns or "compromet" in text else "expense"
        )
    if _COUNT.search(text) and not re.search(r"\bparcela", text):
        return Parts("count", None, order, domain)
    if not _COMPARE.search(text):
        ranked = (least or most) and (
            spends or earns or re.search(r"\bcar[oa]s?\b|\bbarat|\bpior|\bmelhor|\bpesad", text)
        )
        if ranked and not other:
            if weekday or "diasemana" in rest:
                return Parts("rank", "weekday", order, domain, True)
            for pattern in _RANK_TIME:
                if match := pattern.search(rest):
                    return Parts("rank", _GROUP_OF[match[1]], order, domain)
            for pattern in _RANK_PLACE:
                if pattern.search(rest):
                    return Parts("rank", "place", order, domain)
    if match := _LIST.search(text):
        if not other:
            phrase = match[0]
            grouping = next((group for word, group in _LIST_GROUP if word in phrase), "month")
            return Parts("list", grouping, order, domain)
    if (spends or earns or re.search(r"\bmedi[oa]\b", text)) and not other:
        if _PER_DAY.search(text):
            return Parts("per", "day", order, domain)
        if _PER_WEEK.search(text):
            return Parts("per", "week", order, domain)
    if _SMALLEST.search(text) and not other:
        return Parts("smallest", None, "least", domain)
    return Parts(None, None, order, domain)


def mixed(text: str) -> bool:
    """A pergunta fala de receita e de despesa ao mesmo tempo."""
    return re.search(SPEND, text) is not None and re.search(INCOME, text) is not None
