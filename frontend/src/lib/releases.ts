/**
 * Histórico de versões para Ajustes › Notas da versão. Linguagem para o usuário (o detalhe
 * técnico fica nos arquivos de changelog/ do repositório). A primeira é a versão atual.
 */
export type Release = {
  version: string;
  date: string; // dd/mm/aaaa às hh:mm
  title: string;
  sections: { title: string; items: string[] }[];
};

export const RELEASES: Release[] = [
  {
    version: "1.1.0",
    date: "20/10/2026 às 21:30",
    title: "Menu em grupos, gestos no celular, solicitações como tarefas e 10 cores",
    sections: [
      {
        title: "Menu",
        items: [
          "Menu enxuto em grupos: Orçamento, Carteira, Planejamento, Investimentos e Análises.",
          "Mensagens virou um balão no menu, com o número de não lidas; o tema fica ao lado de Sair.",
          "No celular, as abas de baixo mostram os grupos e o topo mostra as telas de cada grupo.",
        ],
      },
      {
        title: "Celular",
        items: [
          "Arraste as janelas para baixo para fechar; se algo foi preenchido, o app pergunta antes.",
          "Deslize para a direita para voltar das sub-telas e para os lados para trocar de tela.",
          "Puxe para baixo no topo para atualizar.",
        ],
      },
      {
        title: "Mensagens",
        items: [
          "Responda aos recados do ADM: a resposta vira uma conversa.",
          "Solicitações numeradas (#N) em Mensagens › Conversas, com o andamento e a versão planejada.",
        ],
      },
      {
        title: "Aparência",
        items: ["10 cores de destaque em Preferências, todas legíveis no claro e no escuro."],
      },
      {
        title: "Correções",
        items: ["O botão \"Instalar no computador\" volta a aparecer no Chrome e no Edge.", "Horário de publicação das versões anteriores corrigido."],
      },
    ],
  },
  {
    version: "1.0.0",
    date: "20/10/2026 às 17:15",
    title: "Dívidas, mês financeiro, alertas, divisões e app Android",
    sections: [
      {
        title: "Dívidas e patrimônio",
        items: [
          "Financiamentos e empréstimos com taxa ao mês ou ao ano, Price ou SAC, custos extras e CET.",
          "As parcelas entram sozinhas no Orçamento e o saldo devedor cai a cada pagamento.",
          "Tabela de parcelas para imprimir ou baixar e simulação de amortização extra.",
          "Tela Dívidas com o patrimônio líquido mês a mês.",
        ],
      },
      {
        title: "Planejamento",
        items: [
          "Calculadoras em Insights: juros compostos, quanto guardar, à vista ou parcelado, antecipar parcelas e reserva de emergência.",
          "Mês financeiro pelo dia do salário, em Preferências.",
          "Alertas de gasto fora do padrão, lugar novo com valor alto, assinatura mais cara e renovação anual.",
        ],
      },
      {
        title: "Divisões",
        items: ["Divida despesas entre pessoas e acompanhe quem deve a quem, com acerto de contas."],
      },
      {
        title: "App",
        items: [
          "App Android para baixar em Ajustes › App e notificações, que se atualiza sozinho.",
          "Notificações no aparelho para contas a vencer, mensagens e alertas.",
          "Abre sem internet com os últimos dados salvos.",
        ],
      },
    ],
  },
  {
    version: "0.9.0",
    date: "20/10/2026 às 11:15",
    title: "Mensagens, tema na conta e começar do zero",
    sections: [
      {
        title: "Mensagens",
        items: [
          "Caixa de Mensagens no menu, com contador de não lidas: respostas às suas solicitações e recados da administração.",
          "Cópia por e-mail de cada mensagem, que pode ser desligada em Ajustes › Preferências.",
          "Recados importantes ficam fixados no topo até serem lidos.",
        ],
      },
      {
        title: "Aparência",
        items: [
          "Botão rápido de tema (automático, claro ou escuro) no menu e no “Mais” do celular.",
          "Tema e cor de destaque salvos na conta: valem em todos os aparelhos.",
          "O app abre direto no tema escolhido, sem piscar o claro, e o modo escuro foi revisado em todas as telas.",
        ],
      },
      {
        title: "Começar do zero (sugestão da comunidade)",
        items: [
          "Em Ajustes › Perfil, escolha quais áreas voltam ao padrão: lançamentos, recorrências, contas, cartões, metas, investimentos, categorias ou análises.",
          "Backup em um toque antes de apagar, confirmação com senha e aviso por e-mail.",
        ],
      },
      {
        title: "Correção",
        items: [
          "Um lançamento excluído não volta mais ao recarregar a página ou sair do app logo depois de excluir.",
        ],
      },
    ],
  },
  {
    version: "0.8.0",
    date: "20/10/2026 às 04:00",
    title: "Avisos por e-mail, metas com objetivo e importação única",
    sections: [
      {
        title: "Avisos por e-mail",
        items: [
          "Lembrete de vencimentos: um e-mail por dia, às 8h, com as contas em aberto que vencem em breve, as de hoje e as em atraso.",
          "Resumo do mês no dia 1, com resultado, taxa de poupança, maiores categorias e metas.",
          "Aviso de acesso por um aparelho novo, com o link “Não fui eu” para proteger a conta.",
          "Controle em Ajustes › Preferências: antecedência, ocultar valores e desligar cada aviso.",
        ],
      },
      {
        title: "Metas",
        items: [
          "Tipo de objetivo, imagem e motivação.",
          "Planejamento por data ou por valor mensal, com projeção sempre atualizada.",
          "Meta principal em destaque no Orçamento e sugestão de aporte quando sobra dinheiro no mês.",
        ],
      },
      {
        title: "Importar e exportar",
        items: [
          "Importação única para OFX, CSV, Excel, backup e arquivo do app antigo, com identificação automática das colunas.",
          "Prévia com repetidos marcados, destino em conta ou fatura de cartão e “Desfazer esta importação”.",
          "Exportação por objetivo, com filtros e resumo anual em PDF.",
        ],
      },
      {
        title: "Outras novidades",
        items: [
          "Comprovante (foto do recibo ou da nota) anexado à despesa.",
          "Configuração inicial guiada no primeiro acesso.",
          "Cotações mais estáveis: o último valor disponível continua na tela quando a fonte limita as consultas.",
          "Termos de uso e Política de privacidade completos.",
          "Esta tela de notas da versão.",
        ],
      },
    ],
  },
  {
    version: "0.7.6",
    date: "19/10/2026 às 18:44",
    title: "Correção: foto e banner do perfil no celular",
    sections: [{ title: "Correção", items: ["A prévia e o recorte da foto e do banner voltaram a funcionar em todos os navegadores."] }],
  },
  {
    version: "0.7.5",
    date: "19/10/2026 às 17:42",
    title: "Solicitações, perfil e cartão de débito",
    sections: [
      {
        title: "Novidades",
        items: [
          "Minhas solicitações: sugestões e problemas viram conversas com a administração, com imagens.",
          "Perfil com foto, banner, resumo pessoal e retrospectiva para compartilhar.",
          "Cartão de débito: compras saem na hora da conta vinculada, sem limite nem fatura.",
          "Formulários alinhados e datas com mensagens claras; nada é salvo com data inválida.",
        ],
      },
    ],
  },
  {
    version: "0.7.0",
    date: "19/10/2026 às 14:10",
    title: "Revisão profissional de layout e textos",
    sections: [
      {
        title: "Novidades",
        items: [
          "Ajustes reunidos em uma única tela, com sub-telas.",
          "Formulário de despesa em etapas e datas no padrão dd/mm/aaaa.",
          "Contas e saldos, Para revisar e busca em todos os meses.",
          "Categoria automática com mais de mil termos.",
        ],
      },
    ],
  },
  {
    version: "0.6.0",
    date: "19/10/2026 às 09:00",
    title: "Conforto de uso",
    sections: [
      {
        title: "Novidades",
        items: [
          "Lançamento em uma frase, atalhos de teclado e ações em lote.",
          "Cartões de crédito com faturas e melhor dia de compra.",
          "Disponível hoje e saldo previsto dia a dia.",
          "Regras de categoria e aviso de lançamento repetido.",
        ],
      },
    ],
  },
  {
    version: "0.5.0",
    date: "19/10/2026 às 00:30",
    title: "Lançamentos flexíveis, Calendário e Cotações",
    sections: [
      {
        title: "Novidades",
        items: [
          "Receitas fixas e variáveis, parcelas pelo total e recorrências com frequência.",
          "Calendário com vencimentos e despesas previstas.",
          "Investimentos com cotações e simulador de renda fixa.",
          "Central de ajuda e apresentação inicial.",
        ],
      },
    ],
  },
  {
    version: "0.4.0",
    date: "16/10/2026 às 15:35",
    title: "Insights personalizáveis",
    sections: [{ title: "Novidades", items: ["Monte sua análise, gráficos interativos e experiência adaptada a cada aparelho."] }],
  },
];
