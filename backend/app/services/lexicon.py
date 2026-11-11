"""Núcleo de linguagem (v1.7.6): o vocabulário que o Lançamento rápido e o Tire sua dúvida dividem.

Uma fonte só para as palavras que os dois precisam reconhecer: formas de pagamento, verbos de
registrar e de perguntar, datas faladas, medidas ("soma", "média", "percentual"), agrupamentos
("por dia", "por ano") e abreviações comuns. As categorias e lojas ficam em `category_words.py`.

Tudo sem acento e em minúsculas. O site recebe uma cópia gerada deste arquivo
(`frontend/src/lib/lexicon.generated.ts`, por `python -m app.cli lexicon`); um teste confere
que a cópia está em dia. Nada aqui chama serviço externo.
"""

from typing import Any

from app.services.category_words import WORDS


def _words(text: str) -> list[str]:
    """Lista separada por vírgula (termos podem ter espaço)."""
    return [" ".join(part.split()) for part in text.split(",") if part.strip()]


# ---------------------------------------------------------------- formas de pagamento

PAYMENTS: dict[str, str] = {}
for _method, _terms in {
    "pix": "pix, pixx, pics, piks, chave pix, via pix, no pix, por pix, pelo pix, qr code, qrcode, pix copia e cola, "
    "pix parcelado, fiz um pix, mandei pix",
    "debit": "debito, deb, cartao de debito, no debito, cartao debito, debito em conta, debito automatico, "
    "funcao debito, na funcao debito, passei no debito",
    "credit": "credito, cred, cartao, cartao de credito, no credito, cartao credito, no cartao, funcao credito, "
    "na funcao credito, credito parcelado, credito a vista, parcelado, crediario, passei no credito, passei no cartao",
    "boleto": "boleto, boletos, boleto bancario, no boleto, por boleto, codigo de barras",
    "cash": "dinheiro, especie, cash, em especie, em dinheiro, dinheiro vivo, no dinheiro, a dinheiro",
}.items():
    for _term in _words(_terms):
        PAYMENTS.setdefault(_term, _method)

# ---------------------------------------------------------------- lançar: receita ou despesa

# No começo da frase, marcam uma receita e saem da descrição ("recebi 3000 de salário").
INCOME_VERBS = _words(
    "recebi, recebido, recebemos, ganhei, ganhamos, entrou, entraram, caiu, cairam, pingou, faturei, "
    "depositaram, depositou, creditou, creditaram, pagaram, me pagaram, vendi, vendemos"
)
# Marcam uma receita e ficam na descrição ("salário 3000", "freela 600").
INCOME_NOUNS = _words(
    "salario, salarios, holerite, contracheque, pagamento do mes, adiantamento, adiantamento salarial, vale salario, "
    "freela, freelas, freelance, freelancer, frila, renda extra, hora extra, horas extras, "
    "comissao, comissoes, bonus, bonificacao, gratificacao, premiacao, plr, ppr, participacao nos lucros, "
    "decimo terceiro, 13o, 13 salario, decimo, ferias recebidas, rescisao, fgts, saque fgts, abono, abono salarial, "
    "seguro desemprego, aposentadoria, pensao recebida, bolsa familia, auxilio, auxilio estudo, "
    "bolsa de estudos, bolsa estagio, pro labore, prolabore, distribuicao de lucros, "
    "dividendos, dividendo, proventos, provento, jcp, juros sobre capital, rendimento, rendimentos, aluguel recebido, "
    "aluguel do inquilino, reembolso, restituicao, restituicao do ir, estorno, cashback, devolucao, venda, vendas, "
    "gorjeta, gorjetas, caixinha, doacao recebida, presente em dinheiro, pix recebido, transferencia recebida, "
    "recarga vale, receita, receitas, renda, rendas, entrada, entradas, recebimento, recebimentos"
)
# No começo da frase, dizem "isto é um lançamento" e saem da descrição ("gastei 50 no mercado").
ENTRY_VERBS = _words(
    "gastei, gastamos, paguei, pagamos, comprei, compramos, torrei, desembolsei, doei, emprestei, quitei, acertei, "
    "assinei, renovei, parcelei, aluguei, reservei, contratei, transferi, saquei"
)
# Pedidos de registro ("lançar mercado 50", "adiciona uber 23").
ENTRY_COMMANDS = _words(
    "lancar, lanca, lance, lancem, registrar, registra, registre, adicionar, adiciona, adicione, anotar, anota, anote, "
    "incluir, inclui, inclua, inserir, insere, insira, colocar, coloca, coloque, botar, bota, bote, cadastrar, cadastra, "
    "cadastre, salvar, salva, salve, debitar, debita, debite"
)
# Verbos do dia a dia que também abrem um lançamento, mas aparecem em perguntas ("fui", "pedi").
ENTRY_SOFT_VERBS = _words(
    "almocei, jantei, lanchei, abasteci, abastecemos, pedi, pedimos, fiz, fui, fomos, tomei, bebi, comi, comemos, "
    "levei, peguei, mandei"
)
# Quando o verbo é a frase toda ("almocei 35"), a descrição vira o nome do gasto.
VERB_NOUNS: dict[str, str] = {
    "almocei": "almoço",
    "jantei": "jantar",
    "lanchei": "lanche",
    "abasteci": "combustível",
    "abastecemos": "combustível",
}
# Substantivos que só anunciam o lançamento ("despesa mercado 50"): saem se sobrar descrição.
ENTRY_NOUNS = _words(
    "despesa, despesas, gasto, gastos, compra, compras, conta, pagamento, lancamento, saida, novo, nova, um, uma"
)
# Palavras de ligação que não entram na descrição.
FILLER = _words(
    "no, na, nos, nas, de, do, da, dos, das, em, com, por, pra, pro, para, a, o, ao, um, uma, r$, rs, brl, reais, "
    "real, conto, contos, pila, pilas, mango, mangos"
)
MONEY_UNITS = _words("r$, rs, brl, reais, real, conto, contos, pila, pilas, mango, mangos")
# Multiplicadores do valor ("2 mil", "1,5k").
MULTIPLIERS: dict[str, int] = {"mil": 1000, "k": 1000}

# ---------------------------------------------------------------- datas faladas

# Dias a partir de hoje.
DATE_WORDS: dict[str, int] = {
    "hoje": 0,
    "hj": 0,
    "ontem": -1,
    "ontm": -1,
    "anteontem": -2,
    "antes de ontem": -2,
    "ante ontem": -2,
    "amanha": 1,
    "depois de amanha": 2,
}
# Segunda = 0 ... domingo = 6. No lançamento, é o último dia assim que já passou (ou hoje).
WEEKDAYS: dict[str, int] = {}
for _index, _names in enumerate(
    [
        "segunda, segunda feira",
        "terca, terca feira",
        "quarta, quarta feira",
        "quinta, quinta feira",
        "sexta, sexta feira",
        "sabado",
        "domingo",
    ]
):
    for _name in _words(_names):
        WEEKDAYS[_name] = _index
WEEKDAY_LABELS = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

# ---------------------------------------------------------------- perguntar

# Quem começa assim está perguntando, não lançando.
QUESTION_STARTERS = _words(
    "quanto, quanta, quantos, quantas, qual, quais, quando, onde, aonde, cade, como, por que, porque, pq, quem, "
    "o que, oq, em que, em qual, com o que, com que, de onde, pra onde, para onde, ate quando, desde quando, "
    "sera que, quanto que, quanto e, quanto foi"
)
# Pedidos de consulta: valem como pergunta quando a frase não traz um valor para lançar.
ASK_VERBS = _words(
    "tem, tenho, temos, existe, ha, posso, devo, da pra, da para, consigo, me diz, me diga, me fala, me fale, "
    "me mostra, me mostre, me conta, me explica, mostra, mostre, mostrar, lista, liste, listar, ver, quero ver, "
    "quero saber, queria saber, gostaria de saber, preciso saber, voce sabe, diga, compare, comparar, compara, "
    "resumo, resuma, resumir, total, soma, some, media, calcule, calcula, calcular, explique, explica, analise, "
    "analisa, analisar, relatorio, extrato, saldo"
)
# Em qualquer ponto da frase, pedem uma conta (e não um lançamento).
ANALYTIC_WORDS = _words(
    "media, medio, total, soma, somado, somando, comparar, comparado, comparacao, versus, percentual, porcentagem, "
    "por cento, porcento, proporcao, ranking, maiores, menores, ultimos, ultimas, historico, evolucao, tendencia, "
    "previsao, projecao, quantas vezes, quantos, quantas, mais que, menos que, do que"
)

# ---------------------------------------------------------------- medidas, agrupamentos e assuntos

# Cada conceito tem as palavras que o acionam. O entendimento (understand.py) monta as regras a
# partir daqui, e a correção de digitação usa estas palavras como alvo.
CONCEPTS: dict[str, list[str]] = {
    # o que se quer saber
    "spend": _words(
        "gastei, gasto, gastos, gastar, gastou, gastamos, gastando, gastaram, gasta, paguei, pago, pagar, pagou, "
        "pagamos, pagando, pagamento, pagamentos, comprei, compra, compras, comprar, comprou, compramos, despesa, "
        "despesas, desembolsei, desembolso, torrei, torrou, saiu, sairam, saida, saidas, debito, debitos, custo, "
        "custos, custou, custaram, consumi, consumo, lancamento, lancamentos, gastanca, gastadeira, prejuizo"
    ),
    "income": _words(
        "recebi, recebeu, recebemos, receber, recebimento, recebimentos, recebido, recebidos, receita, receitas, "
        "renda, rendas, ganhei, ganho, ganhos, ganhar, ganhou, ganhamos, entrou, entraram, entrada, entradas, "
        "faturei, faturamento, salario, salarios, provento, proventos, remuneracao, holerite, contracheque, "
        "pro labore, prolabore, rendimento, rendimentos"
    ),
    "percent": _words(
        "%, por cento, porcento, percentual, percentagem, porcentagem, porcentual, proporcao, fatia, fracao, "
        "comprometimento, comprometido, comprometida, comprometi, compromete, comprometendo, parte da renda, "
        "quanto da renda, quanto da minha renda, quanto do salario, quanto do meu salario, quanto da receita, "
        "peso no orcamento, pesa no orcamento, participacao"
    ),
    "count": _words(
        "quantas vezes, quantos lancamentos, quantas compras, quantos gastos, quantas despesas, quantos pagamentos, "
        "quantos pedidos, quantas corridas, quantas idas, quantas viagens, quantas contas, quantas transacoes, "
        "quantos boletos, quantas parcelas paguei, numero de, quantidade de, qtd de, qtde de, com que frequencia, "
        "frequencia, quantas saidas, quantos debitos, quantas receitas, quantos recebimentos, quantas entradas"
    ),
    "average": _words(
        "media, medio, media de, em media, na media, por mes, mensal, mensalmente, ticket medio, valor medio, "
        "gasto medio, costumo gastar, normalmente gasto, geralmente gasto, em geral gasto"
    ),
    "smallest": _words(
        "menor gasto, menor despesa, menor compra, menor valor, menor lancamento, menor conta, menores gastos, "
        "menores despesas, gasto mais barato, compra mais barata, despesa mais barata, mais barato, mais barata, "
        "mais baratos, mais baratas, gasto mais baixo, despesa mais baixa, valor mais baixo, menor pagamento"
    ),
    "most": _words(
        "mais, maior, maiores, pior, piores, caro, cara, caros, caras, alto, alta, altos, altas, pesado, pesada, "
        "recorde, campeao, topo, top, disparado, explodiu, estourou, auge, pico"
    ),
    "least": _words(
        "menos, menor, menores, barato, barata, baratos, baratas, baixo, baixa, baixos, baixas, economico, "
        "economica, leve, leves, minimo, minima, tranquilo, tranquila, enxuto, enxuta"
    ),
    # como agrupar
    "group_weekday": _words("dia da semana, dias da semana, dia de semana"),
    "group_day": _words("dia, dias, data, datas"),
    "group_week": _words("semana, semanas"),
    "group_month": _words("mes, meses"),
    "group_year": _words("ano, anos"),
    "group_category": _words(
        "categoria, categorias, tipo de gasto, tipos de gasto, tipo de despesa, area, areas, setor"
    ),
    "group_place": _words(
        "lugar, lugares, loja, lojas, estabelecimento, estabelecimentos, local, locais, comercio, comercios, "
        "fornecedor, fornecedores, empresa, empresas, restaurante, restaurantes, mercado onde, site, sites, app, apps"
    ),
    # listar período a período
    "list": _words(
        "mes a mes, mes por mes, cada mes, em cada mes, todo mes, todos os meses, ano a ano, ano por ano, cada ano, "
        "em cada ano, por ano, todos os anos, dia a dia, dia por dia, cada dia, em cada dia, todos os dias, "
        "semana a semana, semana por semana, cada semana, em cada semana, todas as semanas, evolucao, evoluiu, "
        "historico de gastos, linha do tempo, ao longo do ano, ao longo dos meses, ao longo do tempo, por periodo"
    ),
    # média por dia ou por semana
    "per_day": _words(
        "por dia, ao dia, diario, diaria, diarios, diarias, diariamente, media diaria, cada dia em media"
    ),
    "per_week": _words("por semana, semanal, semanais, semanalmente, media semanal, a cada semana"),
    # assuntos que o bot já conhecia (v1.7 e v1.7.5), para a correção de digitação
    "topics": _words(
        "fatura, faturas, cartao, cartoes, limite, parcela, parcelas, parcelado, parcelamento, meta, metas, objetivo, "
        "objetivos, financiamento, financiamentos, emprestimo, emprestimos, divida, dividas, investimento, "
        "investimentos, investido, aplicacao, aplicacoes, assinatura, assinaturas, recorrencia, recorrencias, fixa, "
        "fixas, mensalidade, mensalidades, vencimento, vencimentos, vence, vencem, vencer, venceu, atrasada, "
        "atrasadas, atrasado, atrasados, pendente, pendentes, saldo, sobrou, sobraram, sobra, faltou, economizei, "
        "economia, poupei, guardei, disponivel, calendario, relatorio, categoria, categorias, orcamento, resumo, "
        "comparar, compare, comparacao, ultimo, ultima, ultimos, ultimas, proximo, proxima, proximos, proximas, "
        "passado, passada, anterior, atual, hoje, ontem, anteontem, amanha, semana, quinzena, bimestre, trimestre, "
        "semestre, janeiro, fevereiro, marco, abril, junho, julho, agosto, setembro, outubro, novembro, dezembro, "
        "quanto, quanta, quantos, quantas, qual, quais, quando, onde, como, porque, obrigado, obrigada"
    ),
}

# Abreviações e grafias comuns → forma que as regras entendem.
ABBREVIATIONS: dict[str, str] = {
    "pasado": "passado",
    "pasada": "passada",
    "qto": "quanto",
    "qnto": "quanto",
    "qnt": "quanto",
    "qt": "quanto",
    "qtos": "quantos",
    "qtas": "quantas",
    "qta": "quanta",
    "qtd": "quantidade",
    "qtde": "quantidade",
    "ql": "qual",
    "qdo": "quando",
    "qnd": "quando",
    "qndo": "quando",
    "ond": "onde",
    "oq": "o que",
    "oque": "o que",
    "pq": "por que",
    "vc": "voce",
    "vcs": "voces",
    "hj": "hoje",
    "ontm": "ontem",
    "msm": "mesmo",
    "tb": "tambem",
    "tbm": "tambem",
    "td": "tudo",
    "tds": "todos",
    "mto": "muito",
    "mt": "muito",
    "mta": "muita",
    "pra": "para",
    "pro": "para o",
    "prum": "para um",
    "ta": "esta",
    "to": "estou",
    "tava": "estava",
    "eh": "e",
    "blz": "beleza",
    "vlw": "valeu",
    "obg": "obrigado",
    "obgd": "obrigado",
    "obgda": "obrigada",
    "brigado": "obrigado",
    "brigada": "obrigada",
    "cred": "credito",
    "deb": "debito",
    "meis": "mes",
    "mez": "mes",
    "messes": "meses",
    "jan": "janeiro",
    "fev": "fevereiro",
    "abr": "abril",
    "mai": "maio",
    "jun": "junho",
    "jul": "julho",
    "ago": "agosto",
    "set": "setembro",
    "out": "outubro",
    "nov": "novembro",
    "gastey": "gastei",
    "gastai": "gastei",
    "gasti": "gastei",
    "gstei": "gastei",
    "gatei": "gastei",
    "gastie": "gastei",
    "paguey": "paguei",
    "pagei": "paguei",
    "pguei": "paguei",
    "comprey": "comprei",
    "conprei": "comprei",
    "recebie": "recebi",
    "resebi": "recebi",
    "receby": "recebi",
    "despeza": "despesa",
    "despezas": "despesas",
    "dispesa": "despesa",
    "dispesas": "despesas",
    "reseita": "receita",
    "reseitas": "receitas",
    "resseita": "receita",
    "salaro": "salario",
    "salaio": "salario",
    "celario": "salario",
    "fatuar": "fatura",
    "ftura": "fatura",
    "catao": "cartao",
    "cartaum": "cartao",
    "pacela": "parcela",
    "pacelas": "parcelas",
    "parsela": "parcela",
    "parselas": "parcelas",
    "porcento": "por cento",
    "porcentagen": "porcentagem",
    "percentagem": "porcentagem",
    "pct": "por cento",
    "perc": "percentual",
    "midia": "media",
    "medea": "media",
    "categoia": "categoria",
    "catergoria": "categoria",
    "categora": "categoria",
    "acinatura": "assinatura",
    "asinatura": "assinatura",
    "finaciamento": "financiamento",
    "financiameto": "financiamento",
    "imprestimo": "emprestimo",
    "enprestimo": "emprestimo",
    "vencimeto": "vencimento",
    "atrazada": "atrasada",
    "atrazadas": "atrasadas",
    "atrazado": "atrasado",
    "atrazo": "atraso",
    "economisei": "economizei",
    "economizai": "economizei",
    "investimeto": "investimento",
    "envestimento": "investimento",
    "conparar": "comparar",
    "mercdo": "mercado",
    "merdaco": "mercado",
    "mecado": "mercado",
    "supermecado": "supermercado",
    "famarcia": "farmacia",
    "farmasia": "farmacia",
    "gazolina": "gasolina",
    "gasosa": "gasolina",
    "alugel": "aluguel",
    "aluguer": "aluguel",
    "condominho": "condominio",
    "restaurate": "restaurante",
    "restorante": "restaurante",
    "ifod": "ifood",
    "ifoood": "ifood",
    "aifood": "ifood",
    "ubber": "uber",
    "netflx": "netflix",
    "netflics": "netflix",
    "spotfy": "spotify",
    "spotifai": "spotify",
}
ABBREVIATIONS = {key: value for key, value in ABBREVIATIONS.items() if key != value}


# ---------------------------------------------------------------- contas e cópia para o site


def concept_words() -> set[str]:
    """Todas as palavras soltas dos conceitos (alvo da correção de digitação)."""
    found: set[str] = set()
    groups = [
        *CONCEPTS.values(),
        QUESTION_STARTERS,
        ASK_VERBS,
        ANALYTIC_WORDS,
        ENTRY_VERBS,
        ENTRY_COMMANDS,
    ]
    for terms in [*groups, ENTRY_SOFT_VERBS, INCOME_VERBS, INCOME_NOUNS]:
        for term in terms:
            found.update(part for part in term.split() if part.isalpha())
    for term in [*PAYMENTS, *DATE_WORDS, *WEEKDAYS]:
        found.update(part for part in term.split() if part.isalpha())
    return found


def size() -> dict[str, int]:
    """Quantos termos o núcleo conhece (aparece no teste e no changelog)."""
    concepts = (
        sum(len(terms) for terms in CONCEPTS.values())
        + len(PAYMENTS)
        + len(INCOME_VERBS)
        + len(INCOME_NOUNS)
        + len(ENTRY_VERBS)
        + len(ENTRY_COMMANDS)
        + len(ENTRY_SOFT_VERBS)
        + len(ENTRY_NOUNS)
        + len(FILLER)
        + len(QUESTION_STARTERS)
        + len(ASK_VERBS)
        + len(ANALYTIC_WORDS)
        + len(DATE_WORDS)
        + len(WEEKDAYS)
        + len(ABBREVIATIONS)
    )
    return {"categories": len(WORDS), "concepts": concepts, "total": len(WORDS) + concepts}


def frontend() -> dict[str, Any]:
    """O que o Lançamento rápido (no navegador, funciona sem internet) precisa do núcleo."""
    return {
        "payments": dict(sorted(PAYMENTS.items())),
        "incomeVerbs": sorted(set(INCOME_VERBS)),
        "incomeNouns": sorted(set(INCOME_NOUNS)),
        "entryVerbs": sorted({*ENTRY_VERBS, *ENTRY_COMMANDS, *ENTRY_SOFT_VERBS}),
        "verbNouns": dict(sorted(VERB_NOUNS.items())),
        "entryNouns": sorted(set(ENTRY_NOUNS)),
        "filler": sorted(set(FILLER)),
        "multipliers": dict(sorted(MULTIPLIERS.items())),
        "dateWords": dict(sorted(DATE_WORDS.items())),
        "weekdays": dict(sorted(WEEKDAYS.items())),
        "questionStarters": sorted(set(QUESTION_STARTERS)),
        "askVerbs": sorted(set(ASK_VERBS)),
        "analyticWords": sorted(set(ANALYTIC_WORDS)),
    }
