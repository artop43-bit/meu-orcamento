"""Parâmetros de intenção, operação, agrupamento, comparação, localização e guarda de finalidade."""

from __future__ import annotations


def _words(text: str) -> list[str]:
    return [" ".join(part.split()) for part in text.split(",") if part.strip()]


LOCATE_RECORD_TRIGGERS = _words(
    "onde esta, onde esta o, onde esta a, onde ficam os, onde fica o lancamento, onde fica a despesa, "
    "onde fica o gasto, onde lancei, onde eu lancei, onde cadastrei, onde registrei, onde anotei, "
    "onde foi parar, cade o, cade a, cade aquele, cade aquela, em qual mes esta, em que mes esta, "
    "em qual mes lancei, em que mes lancei, em qual mes foi lancado, em que tela esta o lancamento, "
    "acha pra mim, ache pra mim, achar o lancamento, achar o gasto, achar a despesa, "
    "procura pra mim, procure o lancamento, encontra o lancamento, encontre o lancamento, "
    "localiza o lancamento, localize o gasto, localizar gasto, buscar lancamento, busca lancamento, "
    "quando foi aquele gasto, quando lancei, aquele gasto de, aquela compra de, aquele lancamento de"
)

NAVIGATE_HINT_WORDS = _words(
    "tela, pagina, aba, menu, secao, botao, configuracao, configuracoes, ajuste, ajustes, "
    "exportar, exporto, importar, importo, backup, senha, senhas, mudo, mudar, trocar, troco, "
    "2fa, tema, escuro, claro, instalar, aplicativo, android, ajuda, suporte, tutorial, "
    "calculadora, calculadoras, simulador, projecao, score, saude financeira, dados, "
    "retrospectiva, perfil, novidades, relatorio anual"
)

MOST_TRIGGERS = _words(
    "mais, maior, maiores, pior, piores, caro, cara, caros, caras, alto, alta, altos, altas, "
    "pesado, pesada, recorde, campeao, topo, top, disparado, explodiu, estourou, auge, pico, maximo, maxima"
)

LEAST_TRIGGERS = _words(
    "menos, menor, menores, barato, barata, baratos, baratas, baixo, baixa, baixos, baixas, "
    "economico, economica, leve, leves, minimo, minima, tranquilo, tranquila, enxuto, enxuta"
)

PERCENT_TRIGGERS = _words(
    "%, por cento, porcento, percentual, percentagem, porcentagem, porcentual, proporcao, fatia, "
    "fracao, comprometimento, comprometido, comprometida, comprometi, compromete, parte da renda, "
    "quanto da renda, quanto da minha renda, quanto do salario, quanto do meu salario, quanto da receita, "
    "peso no orcamento, pesa no orcamento, participacao"
)

COUNT_TRIGGERS = _words(
    "quantas vezes, quantos lancamentos, quantas compras, quantos gastos, quantas despesas, "
    "quantos pagamentos, quantos pedidos, quantas corridas, quantas idas, quantas viagens, "
    "quantas contas, quantas transacoes, quantos boletos, numero de, quantidade de, qtd de, "
    "qtde de, com que frequencia, frequencia, quantas saidas, quantos debitos, quantas receitas, "
    "quantos recebimentos, quantas entradas, quantos pix, quantas transferencias"
)

AVERAGE_TRIGGERS = _words(
    "media, medio, media de, em media, na media, mensalmente, ticket medio, valor medio, "
    "gasto medio, costumo gastar, normalmente gasto, geralmente gasto, em geral gasto"
)

PER_DAY_TRIGGERS = _words(
    "por dia, ao dia, diario, diaria, diarios, diarias, diariamente, media diaria, cada dia em media"
)

PER_WEEK_TRIGGERS = _words(
    "por semana, semanal, semanais, semanalmente, media semanal, a cada semana"
)

COMPARE_TRIGGERS = _words(
    "comparar, compare, comparacao, comparado, versus, vs, do que, mais que, menos que, "
    "diferenca entre, variacao entre, quanto mudou, subiu ou caiu"
)

SERIES_TRIGGERS = _words(
    "mes a mes, mes por mes, cada mes, em cada mes, todo mes, todos os meses, "
    "ano a ano, ano por ano, cada ano, em cada ano, todos os anos, "
    "dia a dia, dia por dia, cada dia, em cada dia, todos os dias, "
    "semana a semana, semana por semana, cada semana, em cada semana, todas as semanas, "
    "trimestre a trimestre, por trimestre, evolucao, evoluiu, historico de gastos, "
    "linha do tempo, ao longo do ano, ao longo dos meses, ao longo do tempo, por periodo"
)

LIST_RECORDS_TRIGGERS = _words(
    "lista, liste, listar, me mostra os, me mostre os, mostra todos, quais foram os, "
    "quais gastos, quais despesas, quais receitas, quais lancamentos, o que eu gastei, "
    "o que lancei, o que eu lancei, o que registrei, o que cadastrei, todos os gastos, "
    "todas as despesas, todos os lancamentos, extrato de, detalhes de, detalha"
)

GROUPING_TRIGGERS: dict[str, list[str]] = {
    "weekday": _words("dia da semana, dias da semana, dia de semana"),
    "quarter": _words("trimestre, trimestres"),
    "semester": _words("semestre, semestres"),
    "year": _words("ano, anos"),
    "month": _words("mes, meses"),
    "week": _words("semana, semanas"),
    "day": _words("dia, dias, data, datas"),
    "category": _words(
        "categoria, categorias, tipo de gasto, tipos de gasto, tipo de despesa, area, setor"
    ),
    "place": _words(
        "lugar, lugares, loja, lojas, estabelecimento, estabelecimentos, local, locais, comercio, "
        "comercios, fornecedor, fornecedores, empresa, empresas, restaurante, restaurantes, site, sites, app, apps"
    ),
    "payment_method": _words(
        "forma de pagamento, meio de pagamento, modo de pagamento, metodo de pagamento, como paguei"
    ),
    "card": _words("cartao, cartoes"),
    "account": _words("conta, contas, banco, bancos"),
    "project": _words("projeto, projetos, etiqueta, etiquetas"),
    "person": _words("pessoa, pessoas, amigo, amigos"),
    "status": _words("situacao, status, pago ou pendente"),
}

ALL_TIME_TRIGGERS = _words(
    "todo o historico, todo historico, no historico todo, de todo o historico, desde o comeco, "
    "desde o inicio, de sempre, de todos os tempos, em todos os tempos, alguma vez, ja gastei, "
    "em toda a historia, no total geral, desde sempre, de todos os anos, todos os anos"
)

GREETINGS = _words(
    "oi, oii, oiii, ola, opa, eae, salve, ajuda, bom dia, boa tarde, boa noite, "
    "o que voce faz, o que voce sabe, e ai, menu, help"
)

GREETING_STARTERS = _words(
    "oi, oii, oiii, ola, opa, eae, e ai, salve, fala, bom dia, boa tarde, boa noite"
)

GREETING_TAIL_WORDS = _words(
    "mano, cara, amigo, amiga, pessoal, galera, gente, bot, robo, assistente, parceiro, irmao, irma, "
    "bro, chefe, tudo bem, td bem, tudo bom, td bom, beleza, blz, joia, como vai"
)

THANKS = _words(
    "obrigado, obrigada, muito obrigado, muito obrigada, valeu, vlw, brigado, brigada, "
    "show, perfeito, otimo, legal, ok, tchau, ate mais, show de bola, top"
)

# Sinais explícitos de assuntos fora da finalidade do Meu Orçamento
OFF_TOPIC_PATTERNS = [
    r"\b(?:eu\s+)?so\s+(?:falei|disse)\s+oi\b",
    r"\bquanto pesa (?:um|uma) (?:elefante|cachorro|rato)\b",
    r"\b(?:chover|chuva|previsao do tempo|temperatura|clima|calor|frio|sol hoje)\b",
    r"\b(?:futebol|campeonato|brasileirao|libertadores|copa do mundo|flamengo|corinthians|palmeiras|sao paulo fc|selecao)\b",
    r"\b(?:piada|charada|poema|poesia|horoscopo|signo|novela|filme|serie de tv|musica|letra da musica)\b",
    r"\b(?:capital da|capital do|quem descobriu|presidente do|planeta|universo|sentido da vida|segunda guerra|historia do brasil)\b",
    r"\b(?:receita de (?:bolo|pudim|torta|pao|brigadeiro|lasanha|feijoada|macarrao|comida|frango|carne)|ingredientes|modo de preparo)\b",
    r"\b(?:escrev[ae] um codigo|python|javascript|typescript|html|css|sql|java|algoritmo|programacao)\b",
    r"\b(?:quem e voce|qual seu nome|voce e uma ia|voce e ia|inteligencia artificial|chatgpt|claude|gemini|tudo bem com voce)\b",
    r"\b(?:rato roeu|rei de roma|tres pratos de trigo|trava lingua)\b",
    r"\b(?:quem ganhou|ganhou o jogo|banco de praca|banco da praca|torre eiffel|como tocar)\b",
    r"\b(?:quanto (?:e|da) \d+\s*[+\-*/x]\s*\d+|raiz quadrada|equacao)\b",
]

PURPOSE_ALERT_MESSAGE = (
    "Isso foge do assunto do sistema. Minha finalidade é exclusiva para ajudar você a consultar e "
    "localizar informações já registradas no Meu Orçamento (despesas, receitas, cartões, faturas, "
    "contas, metas, parcelas, dívidas, divisões, projetos, impostos/MEI e telas do site). "
    "Não respondo assuntos externos nem perguntas gerais."
)

OFF_TOPIC_SUGGESTIONS = [
    "Qual ano mais gastei?",
    "Qual foi meu maior gasto no ano?",
    "Onde está o lançamento da farmácia?",
    "Quanto posso gastar hoje?",
]
