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
    version: "1.8.0",
    date: "13/11/2026 às 19:15",
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
