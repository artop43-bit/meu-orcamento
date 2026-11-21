"""Mapa completo das telas e seções do Meu Orçamento e do Hub para respostas de navegação."""

from __future__ import annotations

PLACES: list[tuple[str, str, str]] = [
    (
        "Lançar uma despesa ou receita",
        "/orcamento",
        "lancar lancamento despesa receita adicionar nova novo cadastrar rapido orcamento gasto",
    ),
    ("Calendário de vencimentos", "/calendario", "calendario vencimento vencimentos datas agenda"),
    ("Cartões e faturas", "/cartoes", "cartao cartoes fatura faturas limite credito debito"),
    (
        "Contas e saldos",
        "/contas",
        "banco bancaria bancarias saldo saldos carteira transferencia transferir",
    ),
    (
        "Revisar lançamentos importados",
        "/revisar",
        "revisar conferir importados importado pendentes revisao extrato",
    ),
    ("Busca geral", "/busca", "busca buscar procurar pesquisar pesquisa"),
    (
        "Mensagens e avisos",
        "/mensagens",
        "mensagens mensagem notificacoes notificacao avisos lembretes",
    ),
    (
        "Dívidas e financiamentos",
        "/dividas",
        "divida dividas emprestimo emprestimos financiamento quitar amortizacao",
    ),
    ("Divisões com outras pessoas", "/divisoes", "dividir divisao divisoes racha rachar amigos"),
    (
        "Metas e desafios",
        "/metas",
        "meta metas objetivo objetivos guardar poupar sonho desafio desafios",
    ),
    ("Histórico", "/historico", "historico anteriores antigos"),
    ("Insights", "/analises", "insights insight analise analises resumo graficos grafico"),
    (
        "Calculadoras",
        "/analises?secao=calculadoras",
        "calculadora calculadoras juros parcelamento parcelar parcela reserva emergencia",
    ),
    ("Projeção", "/analises?secao=projecao", "projecao previsao futuro proximos"),
    ("Simulador", "/analises?secao=simulador", "simulador simular simulacao"),
    ("Comparar meses", "/analises?secao=comparar", "comparar comparacao"),
    ("Saúde financeira", "/analises?secao=saude", "saude score nota regra 50/30/20"),
    (
        "Investimentos",
        "/investimentos",
        "investimento investimentos aplicacao aplicacoes cdb tesouro acoes rendimento",
    ),
    (
        "Recorrências (contas fixas)",
        "/ajustes/recorrencias",
        "recorrencia recorrencias fixa fixas assinatura assinaturas mensalidade",
    ),
    ("Categorias", "/ajustes/categorias", "categoria categorias teto limite dedutivel"),
    ("Projetos e etiquetas", "/ajustes/projetos", "projeto projetos etiqueta etiquetas tag tags"),
    (
        "Importar e exportar dados",
        "/ajustes/dados",
        "importar exportar backup planilha csv extrato ofx dados",
    ),
    ("Segurança e senha", "/seguranca", "senha seguranca fatores 2fa sessoes"),
    (
        "Aparência e preferências da conta",
        "/preferencias",
        "tema cor cores aparencia estilo escuro claro glass",
    ),
    (
        "Preferências do orçamento",
        "/ajustes/preferencias",
        "preferencias atalhos mes financeiro pix mei privacidade avisos",
    ),
    ("Perfil", "/perfil", "perfil nome foto email"),
    (
        "Solicitações e suporte",
        "/mensagens/conversas",
        "suporte problema sugestao sugestoes solicitacao solicitacoes erro",
    ),
    ("Ajuda", "/ajustes/ajuda", "ajuda tutorial usar"),
    ("Novidades da versão", "/notas", "novidades versao atualizacao notas"),
    ("Instalar o app", "/app", "app aplicativo instalar celular android"),
    ("Resumo e retrospectiva", "/analises?secao=retrospectiva", "retrospectiva resumo anual"),
    ("Relatório do mês", "/relatorio", "relatorio imprimir pdf"),
]
