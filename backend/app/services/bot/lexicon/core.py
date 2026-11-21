"""Núcleo linguístico expandido: formas de pagamento, verbos, gírias, abreviações e correções.

Reaproveita o dicionário de categorias do próprio sistema (`app.services.category_words`)
para manter uma única fonte de verdade entre Lançamento rápido e Tire sua dúvida.
"""

from __future__ import annotations

from app.services import lexicon as shared
from app.services.category_words import EXACT_ONLY, FALLBACK, WORDS
from app.services.suggest import keyword_category

# ---------------------------------------------------------------- formas de pagamento
PAYMENT_TERMS = shared.PAYMENTS

PAYMENT_LABELS: dict[str, str] = {
    "pix": "Pix",
    "debit": "Débito",
    "credit": "Crédito",
    "boleto": "Boleto",
    "cash": "Dinheiro",
}

# ---------------------------------------------------------------- verbos e comandos de lançamento
INCOME_VERBS = shared.INCOME_VERBS

INCOME_NOUNS = shared.INCOME_NOUNS

ENTRY_VERBS = shared.ENTRY_VERBS

ENTRY_COMMANDS = shared.ENTRY_COMMANDS

ENTRY_SOFT_VERBS = shared.ENTRY_SOFT_VERBS

ENTRY_NOUNS = shared.ENTRY_NOUNS

QUESTION_STARTERS = shared.QUESTION_STARTERS

ASK_VERBS = shared.ASK_VERBS

ANALYTIC_WORDS = shared.ANALYTIC_WORDS

WEEKDAYS = shared.WEEKDAYS

WEEKDAY_LABELS = shared.WEEKDAY_LABELS

DATE_WORDS = shared.DATE_WORDS

# ---------------------------------------------------------------- abreviações e erros comuns
ABBREVIATIONS: dict[str, str] = {
    "retrasdo": "retrasado",
    "qais": "quais",
    "onnde": "onde",
    "ondde": "onde",
    "kd": "cade",
    "kade": "cade",
    "mar": "marco",
    "dez": "dezembro",
    "gastoo": "gasto",
    "faturas": "faturas",
    "cartoes": "cartoes",
    "lancameto": "lancamento",
    "lancaento": "lancamento",
    "lançamento": "lancamento",
    "categoira": "categoria",
    "asinaturas": "assinaturas",
    "trasferencia": "transferencia",
    "trasnferencia": "transferencia",
    "progeto": "projeto",
    "recorrencia": "recorrencia",
    "recorrencias": "recorrencias",
    "recorencia": "recorrencia",
    "dedutivel": "dedutivel",
    "dedutiveis": "dedutiveis",
    "nubak": "nubank",
    "nunbank": "nubank",
    "itauu": "itau",
    "c6bank": "c6",
    "santader": "santander",
    "bradesco": "bradesco",
    "picpay": "picpay",
    "mercadopago": "mercado pago",
}
ABBREVIATIONS = {
    **shared.ABBREVIATIONS,
    **{k: v for k, v in ABBREVIATIONS.items() if k != v and k not in shared.ABBREVIATIONS},
}

# Palavras estruturais da pergunta que nunca devem virar filtro de texto de descrição
COMMON_STOPWORDS: set[str] = set(
    """
    o a os as um uma uns umas de do da dos das em no na nos nas com por pra para pro ao aos
    e ou que qual quais quanto quanta quantos quantas quando onde aonde cade como porque pq quem
    foi foram fiz tive fizemos era sao esta estao estou estava ficar ficou tenho tem temos ha existe
    eu meu minha meus minhas me mim voce vc nos nosso nossa nossos nossas ele ela eles elas
    se ja ainda so mais menos muito pouco bastante bem mal todo toda todos todas cada qualquer nenhum
    este esta estes estas esse essa esses essas aquele aquela aquilo isso isto aqui ali la
    mes meses mes atual ano anos dia dias semana semanas quinzena bimestre trimestre semestre
    vez vezes coisa coisas algo alguma algum parte lugar local tela pagina aba menu sistema site app
    gastei gasto gastos gasta gastou gastamos gastar gastando paguei pago pagar paga pagou pagamento pagamentos
    comprei compra compras comprar comprou despesa despesas conta contas lancamento lancamentos lancado lancados
    lancei registrei registre cadastrei anotei saida saidas debito debitos valor valores total soma somado
    maior maiores menor menores caro cara caros caras barato barata baratos baratas alto alta altos altas
    baixo baixa baixos baixas ultimo ultima ultimos ultimas primeiro primeira proximo proxima passado passada
    anterior recente antigo antigos novo nova novos novas media medio mensal diario semanal anual
    comparar compare comparacao comparado versus vs contra entre do que acima abaixo perto cerca aproximadamente
    encontrar encontro achar acho acha buscar busco localizar localizo procurar procuro ver mostra me diga
    fala fale conta conte lista liste listar saber queria quero preciso gostaria da pra posso consigo devo
    pesou pesa pesam peso uso usei usa usam usou custou custa custam custaram mudo mudar troco trocar
    altero alterar exporto exportar importo importar configuro configurar gero gerar imprimo imprimir
    faco fazer vejo ativo ativar desativo desativar dados senha senhas
    categoria categorias lugar lugares loja lojas estabelecimento estabelecimentos forma meio metodo
    pagamento cartao cartoes fatura faturas conta contas projeto projetos etiqueta etiquetas pessoa pessoas
    amigo amigos registro registros historico todo tudo tempo longo linha periodo evolucao
    sobre item itens linha linhas numero reais real r$ rs brl
    """.split()
)


__all__ = [
    "ABBREVIATIONS",
    "ANALYTIC_WORDS",
    "ASK_VERBS",
    "COMMON_STOPWORDS",
    "DATE_WORDS",
    "ENTRY_COMMANDS",
    "ENTRY_NOUNS",
    "ENTRY_SOFT_VERBS",
    "ENTRY_VERBS",
    "EXACT_ONLY",
    "FALLBACK",
    "INCOME_NOUNS",
    "INCOME_VERBS",
    "PAYMENT_LABELS",
    "PAYMENT_TERMS",
    "QUESTION_STARTERS",
    "WEEKDAYS",
    "WEEKDAY_LABELS",
    "WORDS",
    "keyword_category",
]
