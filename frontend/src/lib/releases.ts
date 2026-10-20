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
    version: "0.8.1",
    date: "20/10/2026 às 12:00",
    title: "Correção na exclusão de lançamentos",
    sections: [
      {
        title: "Correção",
        items: [
          "Excluir um lançamento e logo em seguida recarregar a página, fechar a aba ou sair do app fazia ele voltar. Agora a exclusão vale na hora em que a página é deixada; o “Desfazer” continua funcionando enquanto a tela está aberta.",
        ],
      },
    ],
  },
  {
    version: "0.8.0",
    date: "20/10/2026 às 07:00",
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
