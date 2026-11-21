/**
 * Histórico de versões para Configurações › Notas da versão, separado por solução do Hub.
 * Cada solução tem a própria numeração e só as próprias notas; versão já publicada não ganha
 * itens novos. Linguagem para o usuário (o detalhe técnico fica nos arquivos de changelog/).
 * Em cada solução, a primeira entrada é a versão atual (a mesma de release.ts).
 */
export type ReleaseSolutionId =
  | "hub"
  | "meu-orcamento"
  | "mensageria"
  | "dashboard-crm"
  | "catalogo"
  | "propostas"
  | "projetos"
  | "agenda"
  | "cofre"
  | "caderno";
export type ReleaseSolutionFilter = "all" | ReleaseSolutionId;

export type ReleaseSection = {
  title: string;
  items: string[];
  solution?: ReleaseSolutionId;
};

export type Release = {
  version: string;
  /** "dd/mm/aaaa às hh:mm" (Brasília). Sem data = versão em preparação (o horário entra no PR). */
  date?: string;
  title: string;
  /** Sem solução = Meu Orçamento (as versões anteriores ao Hub). */
  solution?: ReleaseSolutionId;
  sections: ReleaseSection[];
};

export const RELEASE_IN_PREPARATION = "Em preparação";

/** Data mostrada na tela: o horário da publicação ou "Em preparação". */
export function releaseDate(release: Release): string {
  return release.date ?? RELEASE_IN_PREPARATION;
}

export function releaseKey(release: Release): string {
  return `${release.solution ?? "meu-orcamento"}-${release.version}`;
}

export type ReleaseSolutionMeta = {
  id: ReleaseSolutionId;
  label: string;
  shortLabel: string;
  description: string;
};

export const RELEASE_SOLUTIONS: ReleaseSolutionMeta[] = [
  {
    id: "hub",
    label: "Hub de Soluções",
    shortLabel: "Hub",
    description: "Conta, segurança, configurações globais, painel de administração e transição entre soluções.",
  },
  {
    id: "meu-orcamento",
    label: "Meu Orçamento",
    shortLabel: "Meu Orçamento",
    description: "Orçamento mensal, cartões, divisões, empréstimos, investimentos, leitor de cupons e Tire sua dúvida.",
  },
  {
    id: "mensageria",
    label: "Mensageria",
    shortLabel: "Mensageria",
    description: "WhatsApp por QR Code, mídias, player de áudio, respostas rápidas com / e CRM 360° na conversa.",
  },
  {
    id: "dashboard-crm",
    label: "Dashboard & CRM",
    shortLabel: "Dashboard & CRM",
    description: "Painéis personalizados, funil de vendas, contatos, leitor universal de PDF/CSV e conectores de API.",
  },
  {
    id: "catalogo",
    label: "Catálogo & Estoque",
    shortLabel: "Catálogo",
    description: "Produtos, serviços, controle de estoque mínimo, margem e pedidos integrados ao Hub.",
  },
  {
    id: "propostas",
    label: "Propostas & PDFs",
    shortLabel: "Propostas",
    description: "Emissão local de propostas, ordens de serviço, contratos e recibos em PDF com envio pela Mensageria.",
  },
  {
    id: "projetos",
    label: "Projetos & Tarefas",
    shortLabel: "Projetos",
    description: "Kanban, checklists, apontamento de horas e cálculo de margem ligado ao Meu Orçamento.",
  },
  {
    id: "agenda",
    label: "Agenda & Compromissos",
    shortLabel: "Agenda",
    description: "Linha do tempo unificada com compromissos, follow-ups, entregas, fechamentos, validades e contas.",
  },
  {
    id: "cofre",
    label: "Cofre & Garantias",
    shortLabel: "Cofre",
    description: "Arquivo permanente de PDFs e fotos com busca por OCR local, validades e proteção do WhatsApp.",
  },
  {
    id: "caderno",
    label: "Caderno & Conhecimento",
    shortLabel: "Caderno",
    description: "Anotações em Markdown com links [[...]], modelos prontos, backlinks e busca BM25.",
  },
];

export function releaseSolutionLabel(solution: ReleaseSolutionId | undefined): string {
  const target = solution ?? "meu-orcamento";
  return RELEASE_SOLUTIONS.find((s) => s.id === target)?.label ?? "Meu Orçamento";
}

/**
 * Filtra a lista de versões pela solução escolhida ("all" devolve todas). Uma seção marcada com
 * outra solução nunca aparece no filtro da solução da versão.
 */
export function filterReleasesBySolution(
  releases: Release[],
  filter: ReleaseSolutionFilter,
): Release[] {
  if (filter === "all") return releases;
  const out: Release[] = [];
  for (const rel of releases) {
    const relSolution = rel.solution ?? "meu-orcamento";
    if (relSolution === filter) {
      const ownSections = rel.sections.filter((sec) => (sec.solution ?? relSolution) === filter);
      if (ownSections.length === rel.sections.length) out.push(rel);
      else if (ownSections.length > 0) out.push({ ...rel, sections: ownSections });
      continue;
    }
    const matchingSections = rel.sections.filter((sec) => sec.solution === filter);
    if (matchingSections.length > 0) {
      out.push({
        ...rel,
        solution: filter,
        sections: matchingSections,
      });
    }
  }
  return out;
}

export const RELEASES: Release[] = [
  {
    version: "1.0.0",
    title: "Arquivo permanente, validades e OCR local",
    solution: "cofre",
    sections: [
      {
        title: "Cofre & Garantias",
        items: [
          "Guarde PDFs, notas fiscais, garantias, contratos e fotos com busca pelo texto extraído por OCR local.",
          "Validades entram automaticamente na Agenda 360° com filtro rápido de itens vencendo.",
          "Botão Guardar no Cofre na Mensageria e em Propostas & PDFs protege documentos contra a limpeza de 7 dias.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Notas Markdown, links [[...]] e busca BM25",
    solution: "caderno",
    sections: [
      {
        title: "Caderno & Conhecimento",
        items: [
          "Organize atas, POPs e roteiros em cadernos com tags, fixação no topo e modelos prontos.",
          "Conecte notas com [[Nome da nota]], veja backlinks e consulte roteiros direto na Mensageria.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Kanban, checklists, horas trabalhadas e rentabilidade real",
    solution: "projetos",
    sections: [
      { title: "Lista de projetos", items: ["Abra um cartão para editar nome, descrição, prazo e valores ou excluir com a opção de desfazer."] },
      {
        title: "Projetos & Tarefas",
        items: [
          "Organize entregas em quadros Kanban (A fazer, Fazendo, Concluído) com prioridades, prazos e checklists.",
          "Aponte horas trabalhadas e acompanhe automaticamente o ganho real por hora comparando o orçado com despesas do Meu Orçamento.",
          "Crie projetos direto de negócios do CRM ou documentos de Propostas e converta mensagens do WhatsApp em tarefas.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Linha do tempo 360° e confirmação pelo WhatsApp",
    solution: "agenda",
    sections: [
      { title: "Agenda no celular", items: ["Veja o período em formato curto, escolha a visualização em uma linha e deslize os filtros de camadas. O vermelho identifica contas em atraso."] },
      {
        title: "Agenda & Compromissos",
        items: [
          "Visão de Dia, Semana, Mês e Próximos compromissos reunindo Agenda própria, follow-ups da Mensageria, fechamentos do CRM, prazos de Projetos e vencimentos do Meu Orçamento.",
          "Filtre as camadas visíveis e prepare ou envie confirmações de compromisso direto na conversa do WhatsApp.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Produtos, serviços, estoque mínimo e pedidos integrados",
    solution: "catalogo",
    sections: [
      { title: "Lista de itens", items: ["Os nomes podem ocupar duas linhas. O código aparece em uma linha própria e o preço fica abaixo do item no celular.", "A descrição do pedido se ajusta a nomes longos do Catálogo."] },
      {
        title: "Catálogo & Estoque",
        items: [
          "Cadastre produtos com controle de saldo e alerta automático de reposição e serviços com custo e margem unitária.",
          "Registre entradas, saídas e ajustes manuais com histórico completo por item.",
          "Confirme pedidos dando baixa automática no estoque e lançando a venda no Meu Orçamento e no funil do CRM.",
          "Fonte nativa ao vivo disponível também nos painéis do Dashboard & CRM.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Propostas, ordens de serviço, contratos e recibos em PDF",
    solution: "propostas",
    sections: [
      { title: "Lista de documentos", items: ["Os títulos podem ocupar duas linhas e aparecem completos ao abrir o cartão. No celular, o preço fica embaixo.", "Descrições longas ficam legíveis ao editar os itens."] },
      {
        title: "Documentos em PDF e integração",
        items: [
          "Emita propostas comerciais, ordens de serviço, contratos e recibos A4 em PDF gerados 100% no servidor do Hub.",
          "Puxe clientes do CRM e itens do Catálogo com cálculo automático de desconto e validade.",
          "Envie o PDF pronto direto em uma conversa ativa da Mensageria e aprove o documento criando negócio ganho e receita no Orçamento.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Hub de Soluções: todas as soluções numa conta só",
    solution: "hub",
    sections: [
      {
        title: "Termos e privacidade",
        items: [
          "Os Termos de uso e a Política de privacidade cobrem as nove soluções, incluindo os documentos arquivados no Cofre e as notas do Caderno.",
          "No cadastro, o aceite dos Termos fica distinto da declaração de leitura da Política de privacidade.",
        ],
      },
      {
        title: "Hub de Soluções",
        items: [
          "Depois de entrar, você escolhe a solução: Meu Orçamento, Mensageria ou Dashboard & CRM.",
          "Ao abrir uma solução aparece uma animação curta com o nome dela, e a tela já chega pronta, sem aviso de carregamento no meio.",
          "O botão Sair dentro de uma solução volta ao Hub sem encerrar a sessão. Para trocar de solução, você passa pelo Hub.",
        ],
      },
      {
        title: "Conta e Configurações",
        items: [
          "Perfil, Segurança (verificação em duas etapas e sessões), Preferências de aparência (Padrão ou Liquid glass, claro ou escuro), App e notificações e Notas da versão ficam nas Configurações do Hub e valem para todas as soluções.",
          "Mensagens da plataforma (recados da administração e as suas solicitações) ficam no Hub, no botão de carta da barra de cima.",
          "O botão Sair da barra do Hub encerra a sessão da conta.",
          "Notas da versão separadas por solução, cada uma com o próprio número de versão.",
        ],
      },
      {
        title: "Administração",
        items: [
          "Para contas administradoras, o painel de Administração fica na barra do Hub e nas Configurações: usuários, liberação de acesso, e-mails, solicitações, recados e erros.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "WhatsApp por QR Code, mídias e atendimento na conversa",
    solution: "mensageria",
    sections: [
      { title: "Conexão com acesso restrito", items: ["A instalação pode configurar um acesso dedicado ao banco para o conector do WhatsApp."] },
      {
        title: "Conexão com o WhatsApp por QR Code",
        items: [
          "Conecte o seu número lendo o QR Code no celular (Aparelhos conectados), como no WhatsApp Web.",
          "Ao conectar, chegam as conversas recentes. Mensagens novas entram sozinhas, e as enviadas mostram ✓ enviada, ✓✓ entregue e lida.",
          "O nome salvo na agenda vale mais que o apelido, números escondidos não viram nome e conversas repetidas do mesmo contato são juntadas.",
          "Fotos de perfil dos contatos. Sem WhatsApp conectado, a caixa de envio fica desligada.",
          "Só conversas individuais: grupos, status e canais ficam de fora.",
        ],
      },
      {
        title: "Fotos, áudios, vídeos e documentos",
        items: [
          "Receba e envie fotos, áudios, vídeos, figurinhas e documentos de até 8 MB: pelo botão de anexo, colando com Ctrl+V ou arrastando o arquivo para a conversa.",
          "Grave áudio pelo microfone do aparelho.",
          "Player de áudio como o do WhatsApp: ouvir e pausar, barra para avançar ou voltar, tempo, velocidade 1x, 1.5x e 2x e botão para baixar.",
          "Botão Copiar nas fotos e figurinhas, no balão e na foto ampliada.",
        ],
      },
      {
        title: "Atendimento na conversa (CRM 360°)",
        items: [
          "Etiquetas (Lead, Cliente, Orçamento, Cobrança, Urgente, VIP ou as suas), status do atendimento (Em aberto, Aguardando cliente, Resolvido) e lembrete de retorno, com filtros na lista de conversas.",
          "Respostas rápidas digitando / ou tocando em ⚡ (/pix, /cobranca, /boasvindas, /orcamento, /retorno e as que você criar), que já preenchem o nome, o telefone, a chave Pix e o valor pendente.",
          "Painel CRM 360° no contato: veja e mude a etapa dos negócios no Funil, crie um negócio, salve o contato no CRM e cobre com Pix em 1 clique.",
          "Botão Lançar nas mensagens: pega o valor em R$ do texto e registra uma receita ou despesa no mês atual do Meu Orçamento.",
        ],
      },
      {
        title: "Limpeza automática",
        items: [
          "Mensagens e mídias com mais de 7 dias saem da Mensageria para não ocupar espaço. Nada é apagado do celular, e as conversas fixadas ficam.",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    title: "Painéis, funil de vendas e leitura de PDF e CSV",
    solution: "dashboard-crm",
    sections: [
      {
        title: "Painéis e gráficos",
        items: [
          "Monte vários painéis com filtro de período e comece por um modelo pronto: Visão CRM, Mensageria · WhatsApp, Meu Orçamento, Fonte importada ou em branco.",
          "Seis tipos de gráfico: indicador, barras, linha, rosca, funil e tabela.",
        ],
      },
      {
        title: "Funil de vendas e contatos",
        items: [
          "Negócios por etapa (quadro no computador e lista no celular), com o histórico de atividades.",
          "Traga contatos das conversas da Mensageria.",
          "Ao marcar um negócio como Ganho, um botão envia a receita para o Meu Orçamento.",
        ],
      },
      {
        title: "Fontes de dados",
        items: [
          "Dados ao vivo do próprio Hub: negócios e contatos do CRM, mensagens da Mensageria e lançamentos do Meu Orçamento.",
          "Leitura de PDF (tabelas, extratos, fichas e até PDF escaneado) e de CSV no servidor do app, sem serviço externo, com prévia para corrigir antes de importar.",
          "O que foi lido vira um painel pronto ou entra direto em Contatos ou Negócios.",
          "Conexão com APIs (endereço https que devolve JSON), com proteção contra endereços internos e a chave de acesso guardada cifrada.",
        ],
      },
    ],
  },
  {
    version: "1.11.0",
    title: "Reforma Tributária e novo Tire sua dúvida",
    solution: "meu-orcamento",
    sections: [
      { title: "Primeiros passos", items: ["O guia do resumo de Análises exibe os passos em uma coluna no celular."] },
      {
        title: "Reforma Tributária",
        items: [
          "Simule IBS e CBS no Regime Regular e no Simples Nacional e Imposto Seletivo no Regime Regular, com cálculo por item.",
          "Consulte códigos fiscais, fundamentação e atividades do Simples na data da operação.",
          "Gere o PDF DANFSe com o XML de uma nota de serviço já emitida.",
        ],
      },
      {
        title: "Tire sua dúvida",
        items: [
          "Junta vários filtros na mesma pergunta: período, categorias, cartões, contas, projetos, formas de pagamento, pessoas e faixas de valor, e agrupa o resultado de 15 jeitos.",
          "Acha qualquer lançamento (“onde está o lançamento X?”) em despesas, receitas, notas, recorrências, metas, dívidas, divisões e investimentos.",
          "Entende saudações sem confundir com categorias e avisa quando a pergunta foge do tema financeiro.",
          "Continua tudo no servidor do app, sem serviço externo.",
        ],
      },
      {
        title: "Ajustes e Análises",
        items: [
          "Ajustes agora tem só o que é do orçamento. As Preferências reúnem mês financeiro, chave Pix, MEI, avisos financeiros (e-mail, webhook e celular), modo privacidade e atalhos. Perfil, segurança, aparência e app ficam nas Configurações do Hub.",
          "As médias dos meses fechados, a taxa de poupança e a retrospectiva para compartilhar saíram do Perfil e ficam em Análises › Retrospectiva.",
          "Começar do zero fica em Ajustes › Importar e exportar.",
        ],
      },
      {
        title: "Correções",
        items: [
          "Notas da versão 1.10.0: horário corrigido para 17/11 às 21:20 e incluída a correção do limite do cartão, que foi publicada junto.",
        ],
      },
    ],
  },
  {
    version: "1.10.0",
    date: "17/11/2026 às 21:20",
    title: "Leitor de cupons novo",
    sections: [
      {
        title: "Ler comprovante (foto)",
        items: [
          "A foto agora é lida por um leitor de cupons novo, que corrige a inclinação e entende melhor fotos de celular.",
          "Os produtos do cupom só são sugeridos quando a soma deles fecha com o total.",
          "Boleto, valor a pagar, data e forma de pagamento continuam funcionando como antes.",
          "A leitura continua no servidor do app: a foto não vai para nenhum serviço externo.",
        ],
      },
      {
        title: "Correções",
        items: [
          "Horário da versão 1.9.0.1 corrigido nas notas (16/11 às 00:44).",
          "Cartão de crédito: a compra nunca entra como paga e sempre ocupa o limite do cartão.",
        ],
      },
    ],
  },
  {
    version: "1.9.0.1",
    date: "16/11/2026 às 00:44",
    title: "Leitura de comprovante corrigida",
    sections: [
      {
        title: "Ler comprovante (foto)",
        items: [
          "Cupom fiscal não é mais confundido com boleto (o boleto só vale com os dígitos verificadores certos).",
          "O valor a pagar (depois do desconto), a data e a forma de pagamento vêm certos.",
          "Na dúvida, o campo fica em branco para você preencher, em vez de um valor inventado.",
        ],
      },
      {
        title: "Correções",
        items: ["Resumo da semana: compras no cartão aparecem pela fatura, como no lembrete de vencimentos."],
      },
    ],
  },
  {
    version: "1.9.0",
    date: "15/11/2026 às 18:47",
    title: "Avisos por webhook",
    sections: [
      {
        title: "Avisos por webhook",
        items: [
          "Em Ajustes › Preferências, cole o endereço de um webhook do Discord, do Slack ou de outro serviço e escolha quais avisos chegam lá.",
          "Seis avisos para escolher: vencimentos, resumo do mês, resumo da semana, Disponível hoje, mensagens e alertas de gastos.",
          "Botão Enviar teste. Se o endereço parar de responder, os envios pausam e você recebe um aviso.",
        ],
      },
      {
        title: "Ajustes e correções",
        items: [
          "Menu recolhido em janelas baixas: tudo cabe dentro do menu.",
          "Com Ocultar valores ligado, os alertas e o aviso do MEI no celular não mostram valores.",
          "Divisões: a pessoa aberta continua aberta depois de lançar uma anotação.",
        ],
      },
    ],
  },
  {
    version: "1.8.0.2",
    date: "14/11/2026 às 19:35",
    title: "Cobrar só com a chave Pix",
    sections: [
      {
        title: "Cobrar",
        items: [
          "A mensagem pronta (lembrete, cobrança do atraso ou resumo) leva só a sua chave Pix de Preferências.",
          "Um botão só: Copiar mensagem. Saíram o código Pix copia e cola, o QR Code, o WhatsApp e o telefone.",
        ],
      },
    ],
  },
  {
    version: "1.8.0.1",
    date: "14/11/2026 às 17:02",
    title: "Termo pronto para entregar, cobrança com mensagem e pagamento a mais",
    sections: [
      {
        title: "Termo de empréstimo",
        items: [
          "Formato de documento para entregar: cláusulas numeradas, cronograma, local e data, assinaturas e duas testemunhas.",
          "Nome, CPF e endereço das partes, cidade e chave Pix são opcionais: só entra no termo o que você preencher, e nada fica salvo.",
          "Saíram a marca do app, o e-mail e a taxa equivalente.",
        ],
      },
      {
        title: "Cobrar",
        items: [
          "“Cobrar” abre a mensagem pronta (lembrete, cobrança do atraso ou resumo) com a chave Pix de Preferências, para editar e mandar.",
          "Abrir no WhatsApp (direto no contato, se você informar o telefone), copiar ou compartilhar; Pix copia e cola no valor exato e QR Code opcionais.",
        ],
      },
      {
        title: "Pagamentos",
        items: [
          "Pagou a mais: abater do fim (as próximas continuam iguais e termina antes) ou adiantar a próxima, com prévia antes de confirmar e desconto de juros opcional.",
          "Mudar valor das parcelas: o que falta é redividido no novo valor (ex.: R$ 700 por semana), com prévia.",
          "Histórico dos pagamentos no cronograma, com desfazer em cada um.",
        ],
      },
    ],
  },
  {
    version: "1.8.0",
    date: "13/11/2026 às 19:33",
    title: "Empréstimos com juros nas Divisões",
    sections: [
      {
        title: "Simulador de empréstimo",
        items: [
          "Você escolhe o que definir: a taxa, o lucro, o valor da parcela ou o total; o resto é calculado na hora.",
          "Juros sobre o total, simples ao mês, compostos (parcelas iguais) ou SAC (parcelas que diminuem), e sem juros.",
          "Pagamentos por dia, por semana, a cada 15 dias ou por mês, com as datas de cada um.",
          "Taxa equivalente ao mês e ao ano, o mesmo lucro em outras formas de juros e o aviso da Lei da Usura acima de 1% ao mês.",
          "“Vale a pena?”: comparação com o CDB e a inflação, em que parcela o dinheiro volta e quanto se perde se a pessoa parar de pagar.",
        ],
      },
      {
        title: "Acompanhar e cobrar",
        items: [
          "Cada parcela entra no Orçamento do mês como receita prevista (ou despesa, quando é você quem deve).",
          "Recebi a parcela, pagamento parcial ou adiantado, desfazer e quitar antes com desconto dos juros que ainda não venceram.",
          "Cronograma completo, multa e juros por atraso (opcional), aviso de parcela atrasada, cobrança por Pix, mensagem pronta e termo de empréstimo em PDF.",
          "O Tire sua dúvida responde “quanto o João ainda me deve?” e “quanto lucrei com empréstimos?”.",
        ],
      },
      {
        title: "Divisões",
        items: [
          "Uma linha por pessoa, que abre e fecha, com busca por nome, filtros (com empréstimo, atrasados, te devem, você deve) e “Abrir todos”.",
          "Novos números no topo: emprestado com juros e lucro com juros.",
        ],
      },
    ],
  },
  {
    version: "1.7.6.1",
    date: "12/11/2026 às 11:36",
    title: "Exportar em PDF e tela de exportar reorganizada",
    sections: [
      {
        title: "Exportar",
        items: [
          "Novo formato PDF: o recorte escolhido (período, conteúdo, contas e categorias) com resumo, categorias, mês a mês e lançamentos.",
          "Relatório do mês e Resumo anual também baixam direto em PDF.",
          "Tela reorganizada: o recorte de um lado e, do outro, o resumo na hora (lançamentos, receitas, despesas e saldo) e os três formatos.",
          "Contas, cartões e categorias em listas suspensas com busca, no lugar das fileiras de botões.",
        ],
      },
    ],
  },
  {
    version: "1.7.6",
    date: "11/11/2026 às 19:45",
    title: "Um vocabulário só para lançar e para perguntar",
    sections: [
      {
        title: "Tire sua dúvida",
        items: [
          "Entende a pergunta por partes: em que dia, dia da semana, semana, mês, ano ou lugar você gastou mais (ou menos).",
          "Percentual da renda (“quantos % das receitas eu gastei?”), quantas vezes, menor gasto, média por dia e mês a mês.",
          "Conserta erros de digitação e abreviações, e pergunta em vez de chutar quando não tem certeza.",
          "Não registra lançamentos: a frase vai para o Lançamento rápido do Orçamento, já preenchida.",
        ],
      },
      {
        title: "Lançamento rápido",
        items: [
          "Usa o mesmo vocabulário do Tire sua dúvida, com mais de 7 mil termos, guardado no próprio site.",
          "Entende “gastei 50 no mercado”, “paguei 200 de luz na sexta”, “recebi 3 mil de salário” e “em 12 vezes no cartão de crédito”.",
          "Só registra: se a frase for uma pergunta, oferece abrir no Tire sua dúvida.",
        ],
      },
      {
        title: "Cartões e menu",
        items: [
          "Ao lado da pilha de cartões, a barra de limite do cartão da frente; o cartão correspondente fica destacado na lista.",
          "Menu recolhido sem a faixa de destaque sobrando sobre a página, e barra de rolagem discreta no menu aberto.",
        ],
      },
    ],
  },
  {
    version: "1.7.5",
    date: "11/11/2026 às 00:05",
    title: "Painel vivo, menu recolhível e Tire sua dúvida com histórico",
    sections: [
      {
        title: "Painel do Orçamento",
        items: [
          "Saudação com o resumo de agora numa frase e mini gráficos dos últimos 6 meses.",
          "Linha do mês: receitas e vencimentos ao longo do mês, com um marcador até hoje.",
          "Avisos todos no mesmo formato: com seta, a linha inteira abre; sem seta, só informa.",
          "Controle deslizante para simular uma despesa e comparação com o mês anterior por categoria.",
        ],
      },
      {
        title: "Menu e telas",
        items: [
          "Menu lateral recolhível: botão ao lado do logo ou Ctrl+B.",
          "Cartões em pilha, metas com trilha e marcos, e período em pílulas em Insights › Categorias.",
        ],
      },
      {
        title: "Tire sua dúvida",
        items: [
          "Entende hoje, ontem, semana, faturas, parcelas que faltam, financiamentos, assinaturas, média por mês e comparações.",
          "Continua a conversa (“e em setembro?”) e guarda o histórico por 30 dias; dá para desligar em Preferências.",
        ],
      },
      {
        title: "Mais rápido",
        items: ["Fontes hospedadas no site, fotos em formato mais leve e imagens carregadas só quando aparecem."],
      },
    ],
  },
  {
    version: "1.7.0",
    date: "10/11/2026 às 11:57",
    title: "Painel mais leve, cores consistentes e Tire sua dúvida",
    sections: [
      {
        title: "Painel do Orçamento",
        items: [
          "Resumo do mês num bloco só, com o saldo em destaque.",
          "Avisos reunidos numa faixa que abre ao tocar; filtros em pílulas e o menu ⋯ na lista de despesas.",
          "Coluna lateral mais enxuta: detalhes aparecem quando você toca.",
        ],
      },
      {
        title: "Tire sua dúvida",
        items: [
          "Em Insights, pergunte sobre os seus lançamentos: o que mais gastou, em que mês, quando gastou mais numa categoria, o que vence e onde fica cada coisa no site.",
          "Respondido pelo próprio site, sem serviço externo; a pergunta não fica salva.",
        ],
      },
      {
        title: "Cores e mouse",
        items: [
          "Listas suspensas legíveis em todos os temas e cores.",
          "Ícones e botões ganham destaque na cor escolhida ao passar o mouse.",
        ],
      },
    ],
  },
  {
    version: "1.6.5",
    date: "09/11/2026 às 21:35",
    title: "Fluidez e enquadramento",
    sections: [
      {
        title: "Mais fluido",
        items: [
          "Troca de telas e deslizar entre abas mais leves, principalmente no celular e no Liquid glass.",
          "Um marcador desliza até a aba ativa no menu, na barra de baixo e nas abas das telas.",
          "Os cartões surgem em sequência, os números sobem até o valor e trocar de tema ou estilo revela a nova aparência a partir do toque.",
        ],
      },
      {
        title: "Tudo no lugar",
        items: [
          "Abas, títulos e linhas de itens não partem mais palavras no celular; faixas que deslizam mostram quando há mais conteúdo ao lado.",
        ],
      },
    ],
  },
  {
    version: "1.6.0",
    date: "09/11/2026 às 17:45",
    title: "Estilos visuais e parcelamento que conhece as suas contas",
    sections: [
      {
        title: "Aparência",
        items: [
          "Visual novo em todas as telas e um segundo estilo, Liquid glass: escolha em Preferências › Aparência. Combina com o tema claro ou escuro e com a sua cor de destaque, e fica salvo na conta.",
          "Gráficos, investimentos, Retrospectiva e ícones dos cartões agora acompanham a cor escolhida, com leitura conferida em todas as combinações.",
        ],
      },
      {
        title: "Calculadoras",
        items: [
          "Parcelar ou à vista mostra o efeito da parcela nos seus próximos meses: quanto da renda fica comprometida, a sobra mês a mês, o limite do cartão e se o saldo cobre o à vista sem tocar na reserva.",
          "Sugestão do menor número de parcelas sem mês negativo e \"Lançar como planejado\".",
          "Resultados em destaque com mini gráficos, rendimento pelo CDI atual e vírgula ou ponto nos números.",
        ],
      },
      {
        title: "Correções",
        items: ["Um desafio começado hoje não é mais perdido por uma despesa que já estava lançada antes de começar."],
      },
    ],
  },
  {
    version: "1.5.0",
    date: "30/10/2026 às 08:47",
    title: "Cupom item a item, vale-transporte e INSS",
    sections: [
      {
        title: "Lançamentos",
        items: [
          "Comprovante: o cupom com vários produtos é lido item a item e a compra já vem dividida pelas categorias sugeridas. A lista de itens fica na observação.",
          "Lançamento rápido: com outro mês aberto no Orçamento, a frase sem data é lançada nele (dia 1). \"Dia 5\" também vale para o mês aberto.",
        ],
      },
      {
        title: "Contas e salário",
        items: [
          "Nova conta Vale-transporte: recarga mensal como receita e pagamento só de Transporte, como o vale-refeição.",
          "Receita fixa: \"Calcular o líquido pelo salário bruto\" desconta o INSS pela tabela de 2026 e anota o cálculo na observação.",
        ],
      },
    ],
  },
  {
    version: "1.4.4",
    date: "22/10/2026 às 16:04",
    title: "Manutenção e otimização",
    sections: [
      {
        title: "Por dentro",
        items: [
          "A cada atualização o celular baixa menos da metade do que baixava: as bibliotecas ficam guardadas no aparelho.",
          "O banco de dados ganhou índices para continuar rápido conforme os lançamentos crescem.",
          "Bibliotecas atualizadas e limpeza de código antigo.",
        ],
      },
    ],
  },
  {
    version: "1.4.3",
    date: "21/10/2026 às 21:39",
    title: "Telas mais rápidas",
    sections: [
      {
        title: "Desempenho",
        items: [
          "Cotações e investimentos aparecem na hora com o último dado e se atualizam em segundo plano.",
          "Com sinal fraco, o app mostra os últimos dados guardados em até 5 segundos e se atualiza quando a resposta chega.",
          "As telas ficam prontas para abrir logo depois de entrar no app.",
        ],
      },
    ],
  },
  {
    version: "1.4.2",
    date: "21/10/2026 às 19:52",
    title: "iPhone instalado e volta das sub-telas",
    sections: [
      {
        title: "Correções",
        items: [
          "Com o app instalado no iPhone, a tela não fica mais cortada: a barra de baixo fica acima da linha de home e o topo abaixo da ilha.",
          "Deslizar para voltar de uma sub-tela (como Ajustes › Perfil) não deixa mais a tela travada.",
          "Se a tela ainda parecer cortada, remova o app da tela de início e instale de novo.",
        ],
      },
    ],
  },
  {
    version: "1.4.1",
    date: "21/10/2026 às 18:42",
    title: "Celular mais fluido",
    sections: [
      {
        title: "Navegação",
        items: [
          "Deslize para o lado para trocar as abas de baixo; cada aba volta ao submenu em que você estava.",
          "Os submenus (Contas, Cartões, Calendário, Metas…) ficam no toque.",
          "Sem tela preta: a próxima aba aparece colada enquanto você desliza.",
          "O menu Mais fecha na hora ao abrir uma tela.",
        ],
      },
      {
        title: "Telas",
        items: [
          "Gráfico do Histórico cabe na tela, com os meses legíveis.",
          "Barra de baixo com ícones e textos maiores e o tema em três botões alinhados.",
        ],
      },
    ],
  },
  {
    version: "1.4.0",
    date: "21/10/2026 às 17:00",
    title: "Pix, vale-refeição, MEI, Imposto de Renda e o raio-x dos gastos",
    sections: [
      {
        title: "Divisões e contas",
        items: [
          "Cobre via Pix: cadastre sua chave em Preferências e gere o QR Code e o copia e cola com o valor devido.",
          "Novo tipo de conta: vale-refeição ou alimentação, com recarga mensal automática.",
        ],
      },
      {
        title: "MEI e Imposto de Renda",
        items: [
          "Sou MEI: acompanhe o faturamento do ano e receba um aviso ao chegar em 80% do teto.",
          "O resumo anual mostra o que interessa para o Imposto de Renda: despesas dedutíveis, rendimentos, bens e dívidas.",
          "Ao importar um extrato, o que você já lançou à mão é reconhecido e não entra duplicado.",
        ],
      },
      {
        title: "Calendário",
        items: [
          "Gastos grandes previstos mostram quanto guardar por mês até a data.",
          "Leve os vencimentos para a agenda do celular com um link secreto.",
          "Aviso diário opcional com o disponível do dia.",
        ],
      },
      {
        title: "Insights, investimentos e projetos",
        items: [
          "Tarifas e juros pagos no ano e a sua inflação comparada ao IPCA.",
          "Calculadora do 13º e da restituição.",
          "Meta de alocação da carteira, com a divisão do próximo aporte.",
          "Projetos: junte despesas de categorias diferentes e acompanhe o total na Busca.",
        ],
      },
    ],
  },
  {
    version: "1.3.2",
    date: "21/10/2026 às 12:10",
    title: "Mensagens com um só acesso",
    sections: [
      {
        title: "Mensagens",
        items: [
          "Um só acesso no menu: o balão de Mensagens.",
          "A nova solicitação fica na aba Solicitações; a aba Recados mostra só os recados e as respostas.",
        ],
      },
    ],
  },
  {
    version: "1.3.1",
    date: "21/10/2026 às 11:50",
    title: "Mensagens: recados com respostas em thread e solicitações com tema e arquivos",
    sections: [
      {
        title: "Mensagens",
        items: [
          "Duas abas: Recados e Solicitações. O botão “Nova solicitação” e o balão do menu continuam iguais.",
          "Recados numa lista só, com as respostas em thread no próprio recado, visíveis para todos que o receberam.",
          "Respostas antigas a recados passaram para a thread do recado.",
        ],
      },
      {
        title: "Nova solicitação",
        items: [
          "Tema em botões (Sugestão, Dúvida, Erro, Elogio ou Outro) e mensagem de até 1000 caracteres.",
          "Anexe até 3 arquivos de até 5 MB: imagens, PDF ou planilhas (XLSX, XLS, CSV ou ODS).",
        ],
      },
    ],
  },
  {
    version: "1.3.0",
    date: "21/10/2026 às 10:45",
    title: "Voz, foto do comprovante, sem internet, desafios e painel personalizado",
    sections: [
      {
        title: "Lançamentos",
        items: [
          "Lançamento por voz: toque no microfone, fale (ex.: “mercado 120 no pix ontem”), confira e lance.",
          "Compra dividida em categorias, cada parte com o seu valor, sem lançar nada em dobro.",
          "Ler comprovante pela foto: valor, data e descrição preenchidos para conferir; a foto fica anexada.",
          "Sem internet: despesas, receitas e o “pagar” ficam no aparelho e sobem sozinhos quando a conexão volta.",
        ],
      },
      {
        title: "Planejamento",
        items: [
          "Sobra do limite da categoria para o mês seguinte (opcional, em Categorias).",
          "Plano de quitação em Dívidas: menor dívida primeiro ou juros mais altos primeiro, com juros e prazos.",
          "Calculadora de correção pela inflação (IPCA), em Insights › Calculadoras.",
        ],
      },
      {
        title: "Hábito",
        items: [
          "Desafios de economia em Metas, com progresso pelos seus lançamentos.",
          "Plano para equilibrar o mês quando ele fica no negativo, passo a passo e sem julgamento.",
          "Resumo da semana às segundas, por e-mail e no aparelho (pode ser desligado em Preferências).",
        ],
      },
      {
        title: "Experiência",
        items: [
          "Personalize o painel do Orçamento: escolha os cartões e a ordem.",
          "Atalhos ao segurar o ícone do app instalado: Nova despesa, Nova receita e Lançar por voz.",
        ],
      },
    ],
  },
  {
    version: "1.2.0",
    date: "21/10/2026 às 00:20",
    title: "Navegação fluida e cores consistentes",
    sections: [
      {
        title: "Navegação",
        items: [
          "As telas abrem na hora, sem o cartão de carregamento piscando entre uma e outra.",
          "Os dados da tela começam a chegar quando você aponta ou toca no item do menu.",
          "Vários grupos do menu abertos ao mesmo tempo; clicar no título só abre ou fecha.",
          "No celular, a aba de cada grupo volta para a última tela que você abriu nele.",
        ],
      },
      {
        title: "Cores",
        items: [
          "Saldo positivo, \"Paga\", metas e gráficos seguem a cor de destaque escolhida.",
          "Com rosa, vermelho, laranja ou âmbar, o positivo fica neutro para não parecer alerta.",
          "O vermelho fica só para valores negativos e atrasos; cotações mantêm verde e vermelho.",
        ],
      },
    ],
  },
  {
    version: "1.1.0",
    date: "20/10/2026 às 22:00",
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
