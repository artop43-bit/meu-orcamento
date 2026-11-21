"""Parâmetros de domínio do Meu Orçamento: entidades, atributos, estados e sinônimos."""

from __future__ import annotations


def _words(text: str) -> list[str]:
    return [" ".join(part.split()) for part in text.split(",") if part.strip()]


ENTITY_TERMS: dict[str, list[str]] = {
    "expense": _words(
        "despesa, despesas, gasto, gastos, compra, compras, pagamento, pagamentos, saida, saidas, "
        "debito, debitos, lancamento, lancamentos, conta, contas, boleto, boletos, custo, custos"
    ),
    "income": _words(
        "receita, receitas, renda, rendas, entrada, entradas, recebimento, recebimentos, salario, "
        "salarios, ganho, ganhos, faturamento, provento, proventos, freela, freelance, comissao, "
        "bonus, decimo terceiro, reembolso, dividendo, dividendos, rendimento, rendimentos, holerite"
    ),
    "balance": _words(
        "saldo, sobra, sobrou, sobraram, faltou, resultado, balanco, fechamento, fechei, fiquei, "
        "economizei, economia, poupei, guardei, liquido, sobrando, restando"
    ),
    "card": _words(
        "cartao, cartoes, cartao de credito, limite, limite disponivel, limite usado, fatura, "
        "faturas, fechamento do cartao, melhor dia, rotativo, credito"
    ),
    "invoice": _words(
        "fatura, faturas, fatura aberta, fatura fechada, fatura vencida, fatura paga, "
        "vencimento da fatura, fechamento da fatura, valor da fatura, conta do cartao"
    ),
    "account": _words(
        "conta, contas, conta corrente, poupanca, carteira, conta bancaria, banco, bancos, "
        "saldo em conta, saldo da conta, vale refeicao, vale alimentacao, vr, va, beneficio"
    ),
    "transfer": _words(
        "transferencia, transferencias, transferi, mandei entre contas, movi dinheiro, "
        "pix entre contas, aplicacao entre contas, resgate entre contas"
    ),
    "recurring": _words(
        "recorrencia, recorrencias, despesa fixa, despesas fixas, conta fixa, contas fixas, "
        "renda fixa, mensalidade, mensalidades, todo mes, automatico, recorrente, recorrentes"
    ),
    "subscription": _words(
        "assinatura, assinaturas, streaming, streamings, clube, clubes, plano mensal, "
        "mensalidade de app, servico mensal"
    ),
    "installment": _words(
        "parcela, parcelas, parcelado, parcelada, parcelados, parceladas, parcelamento, "
        "em vezes, prestacao, prestacoes, carne, compras parceladas, falta pagar das parcelas"
    ),
    "project": _words(
        "projeto, projetos, etiqueta, etiquetas, tag, tags, evento, obra, reforma, viagem"
    ),
    "goal": _words(
        "meta, metas, objetivo, objetivos, sonho, sonhos, reserva, alvo, juntar dinheiro, "
        "quanto falta para, ritmo da meta, aporte, aportes, contribuicao, contribuicoes"
    ),
    "challenge": _words(
        "desafio, desafios, desafio de economia, no spend, sem gastar, meta de desafio"
    ),
    "investment": _words(
        "investimento, investimentos, investido, investidos, aplicacao, aplicacoes, carteira, "
        "acoes, acao, cdb, tesouro, tesouro direto, fii, fiis, fundo, fundos, renda fixa, "
        "renda variavel, reserva de emergencia, patrimonio aplicado, ticker, corretora"
    ),
    "loan": _words(
        "financiamento, financiamentos, emprestimo bancario, divida, dividas, saldo devedor, "
        "amortizacao, price, sac, prestacao do financiamento, consorcio, cheque especial, "
        "outra divida, outras dividas, acordo"
    ),
    "friend_loan": _words(
        "divisao, divisoes, racha, rachado, me deve, me devem, devendo, quem me deve, "
        "emprestei, emprestimo para amigo, emprestimo a amigo, devo para, devo ao, devo a, "
        "juros de emprestimo, lucro com emprestimos, cobranca, receber de amigo"
    ),
    "planned": _words(
        "planejado, planejados, planejada, planejadas, gasto previsto, gastos previstos, "
        "despesa prevista, despesas previstas, planejamento, previsto para, agendado"
    ),
    "net_worth": _words(
        "patrimonio, patrimonio liquido, bens e dividas, evolucao patrimonial, riqueza, "
        "ativos e passivos, total de bens"
    ),
    "tax_deductible": _words(
        "dedutivel, dedutiveis, deducao, imposto de renda, ir, irpf, declarar no ir, "
        "saude dedutivel, educacao dedutivel, previdencia, pensao alimenticia"
    ),
    "mei": _words(
        "mei, microempreendedor, cnpj, faturamento mei, limite mei, teto mei, nota fiscal mei, "
        "das mei, receita mei"
    ),
    "receipt": _words(
        "comprovante, comprovantes, cupom, cupom fiscal, nota fiscal, nfce, nfe, recibo, "
        "anexo, anexos, foto do comprovante"
    ),
    "can_spend": _words(
        "posso gastar, disponivel hoje, livre hoje, quanto ainda posso gastar, sobra pra gastar, "
        "orcamento diario, limite diario, quanto tenho livre"
    ),
    "due": _words(
        "vence, vencem, vencendo, vencimento, vencimentos, a pagar, pendente, pendentes, "
        "pra pagar, para pagar, contas proximas, proximos vencimentos, vence hoje, vence essa semana"
    ),
    "overdue": _words(
        "atrasada, atrasadas, atrasado, atrasados, em atraso, vencida, vencidas, vencido, vencidos"
    ),
    "needs_review": _words(
        "revisar, revisao, conferir, conferido, nao conferido, nao conferidos, pendente de revisao, "
        "importado, importados, extrato importado, precisa revisar, falta conferir"
    ),
}

STATUS_TRIGGERS: dict[str, list[str]] = {
    "paid_true": _words(
        "ja pago, ja pagos, ja paga, ja pagas, pagos, pagas, quitado, quitados, quitada, quitadas, "
        "que eu ja paguei, que paguei, liquidado, liquidados"
    ),
    "paid_false": _words(
        "nao pago, nao pagos, nao paga, nao pagas, em aberto, pendente, pendentes, "
        "a pagar, falta pagar, faltam pagar, sem pagar, nao paguei, ainda nao paguei"
    ),
    "overdue_true": ENTITY_TERMS["overdue"],
    "needs_review_true": ENTITY_TERMS["needs_review"],
    "installment_true": ENTITY_TERMS["installment"],
    "recurring_true": _words(
        "recorrente, recorrentes, despesa fixa, despesas fixas, conta fixa, contas fixas, "
        "fixo, fixa, fixas, fixos, mensalidade, assinatura, assinaturas"
    ),
    "essential_true": _words("essencial, essenciais, necessario, necessarias, basico, basica"),
    "essential_false": _words(
        "nao essencial, nao essenciais, superfluo, superfluos, superflua, superfluas, cortavel"
    ),
    "mei_true": ENTITY_TERMS["mei"],
}

DEDUCTIBLE_TERMS: dict[str, list[str]] = {
    "saude": _words("saude, medico, hospital, dentista, clinica, exame, plano de saude"),
    "educacao": _words("educacao, escola, faculdade, universidade, pos, colegio"),
    "previdencia": _words("previdencia, pgbl"),
    "pensao": _words("pensao, pensao alimenticia"),
}

MONTH_NAMES_NORM: dict[str, int] = {
    "janeiro": 1,
    "jan": 1,
    "fevereiro": 2,
    "fev": 2,
    "marco": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "maio": 5,
    "mai": 5,
    "junho": 6,
    "jun": 6,
    "julho": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "setembro": 9,
    "set": 9,
    "outubro": 10,
    "out": 10,
    "novembro": 11,
    "nov": 11,
    "dezembro": 12,
    "dez": 12,
}

TEXT_NUMBERS: dict[str, int] = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "doze": 12,
    "quinze": 15,
    "vinte": 20,
    "trinta": 30,
    "sessenta": 60,
    "noventa": 90,
}
