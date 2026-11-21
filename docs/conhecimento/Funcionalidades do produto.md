---
tags: [meu-orcamento, produto]
---
# Funcionalidades do produto

- **Reforma Tributária** em **Análises → Ferramentas**. Simula IBS e CBS no Regime Regular
  e no Simples Nacional, além do Imposto Seletivo no Regime Regular. Mostra valores,
  alíquotas e memória por item e sinaliza estimativas e resultados parciais. Consulta
  NCM, NBS, CST, cClassTrib e atividades do Simples por data de vigência. Gera o PDF
  DANFSe a partir do XML de uma NFS-e nacional já emitida, sem guardar o arquivo.

- **Orçamento do mês**: receitas, despesas, parcelas, recorrências, cartões e contas;
  **Lançamento rápido** por frase ("gastei 50 no mercado").
- **Tire sua dúvida** (bot composicional local em `app/services/bot/`, sem IA, atualizado em 2026-11-20):
  combina múltiplos filtros na mesma frase (períodos, cartões, contas, projetos, Pix/débito/crédito/boleto,
  faixa ou valor aproximado, pago/atrasado/revisar/parcelado/fixo/essencial/IR/MEI), agrupa por 15 dimensões,
  traz **localizador universal** (`"onde está o lançamento X?"`) em todas as tabelas, guarda de finalidade
  (`out_of_scope`) para bloquear assuntos fora do sistema, saudações casuais (`"OI MANO"`) sem falso positivo
  de categoria, rotas atualizadas do Hub e encaminhamento mútuo com o Lançamento rápido.
- **Exportar**: CSV, Excel e PDF do recorte escolhido; relatório do mês e resumo anual em PDF.
- **Divisões** (v1.8): linhas por pessoa, anotações simples, **empréstimos com juros**.
  - Simulador: definir taxa, lucro, parcela ou total; juros sobre o total, simples, Price,
    SAC ou sem juros; pagamentos por dia, semana, 15 dias ou mês; taxa equivalente; aviso da
    Lei da Usura (1% a.m.); comparação com CDB/IPCA; risco.
  - Parcelas viram **receitas previstas** no Orçamento (despesas quando "eu devo").
  - Recebi a parcela (parcial; a mais: abater do fim ou adiantar a próxima), mudar valor das
    parcelas, quitar com desconto de juros, histórico com desfazer.
  - **Termo de empréstimo** em PDF pronto para entregar (dados das partes opcionais,
    testemunhas).
  - **Cobrar**: mensagem pronta só com a chave Pix e o botão "Copiar mensagem".
- Dívidas/financiamentos, metas, investimentos, insights, calendário, histórico,
  notificações, 2FA, backup e "Começar do zero".
- **Mensageria** (solução do Hub, `/mensageria`): troca de mensagens estilo WhatsApp com busca,
  filtros, citações/respostas e vínculo opcional de contatos com pessoas de Divisões/Empréstimos
  do Meu Orçamento.
  - **Conexão real com o WhatsApp por QR Code** (2026-11-19): "Conectar" → o QR aparece e se
    renova sozinho → a pessoa escaneia em Aparelhos conectados. Mensagens recebidas entram
    sozinhas; as enviadas saem de verdade com ✓ / ✓✓ / ✓✓ lida; as mandadas pelo celular também
    aparecem; abrir a conversa marca como lida no celular (e vice-versa). Ao conectar, traz as
    conversas recentes (até 50 × 20 mensagens). Reconecta sozinho após reinício.
  - Sem conexão, a caixa de envio fica desativada ("Conecte o WhatsApp para enviar mensagens.").
  - **Mídias, fotos de perfil, nomes corretos e limpeza semanal** (2026-11-20): recebe e envia fotos (com zoom e botão **Copiar** para a área de transferência), áudios (player estilo WhatsApp com barra deslizante, tempo, velocidade `1x`/`1.5x`/`2x`, download, streaming HTTP `206 Partial Content` e gravação pelo microfone do navegador), vídeos, figurinhas e documentos de até 8 MB; aceita **colar mídias com `Ctrl+V`** e **arrastar e soltar arquivos** na conversa; exibe foto de perfil dos contatos com fallback para iniciais; prioriza nome da agenda sobre apelido, rejeita números mascarados e une conversas duplicadas (LID/número); limpeza automática semanal (7 dias) remove mensagens/mídias antigas e conversas inativas não fixadas apenas do servidor (nunca do celular).
  - **CRM 360° e Finanças dentro da Mensageria** (2026-11-20):
    - *Etiquetas, status de atendimento e follow-up*: etiquetas coloridas (`Lead`, `Cliente`, `Orçamento`, `Cobrança`, `Urgente`, `VIP` ou personalizadas), status (`Em aberto`, `Aguardando cliente`, `Resolvido`) e agendamento de follow-up com lembrete (`Hoje +2h`, `Amanhã 09h`, `Em 7 dias` ou data/hora livre), com filtros na barra lateral (`Todas`, `Não lidas`, `Follow-up`, `Arquivadas` e por etiqueta).
    - *Respostas rápidas com `/` e variáveis inteligentes*: menu ao digitar `/` ou tocar em ⚡ (`/pix`, `/cobranca`, `/boasvindas`, `/orcamento`, `/retorno` + criação de novos atalhos) preenchendo automaticamente `{nome}`, `{telefone}`, `{chave_pix}` e `{valor_pendente}`.
    - *Funil CRM e Meu Orçamento sem sair do chat*: criação e mudança de etapa de negócios do contato no Funil CRM direto pelo painel *CRM 360°*, botão **"Cobrar com Pix no chat"** em 1 clique e botão **"Lançar"** em qualquer mensagem (extrai valores em `R$` do texto e grava Receita ou Despesa real no mês atual do Meu Orçamento).
  - Só conversas individuais (grupos, status e canais ficam de fora).
  - Contato com número oculto pelo WhatsApp aparece como "Número oculto pelo WhatsApp".
- **Dashboard & CRM** (solução do Hub, `/crm`, 2026-11-20):
  - **Painéis personalizados**: múltiplos painéis, modelos prontos (CRM, Mensageria ao vivo, Meu Orçamento ao vivo, fonte importada), filtro global de período e 6 tipos de gráfico (KPI, barras, linha, rosca, funil e tabela).
  - **Funil CRM e Contatos**: quadro por etapas (Kanban no desktop, lista no celular), linha do tempo de atividades, importação de contatos da Mensageria e lançamento real de receita no Meu Orçamento ao marcar um negócio como Ganho.
  - **Fontes de dados**: 4 fontes nativas ao vivo do Hub, leitura local universal de PDFs (tabelas, extratos, fichas, texto livre e PDFs escaneados via OCR local) e CSVs com prévia editável, além de conectores de API REST/JSON HTTPS com proteção anti-SSRF e credenciais cifradas.
- **Hub de Soluções**: para trocar de solução a pessoa sempre volta ao Hub (não há atalho de uma
  solução para outra). Entrada com animação logo → nome sem "Carregando…" no meio; saída com
  esmaecimento e os cartões do Hub entrando em sequência (2026-11-19).
- **Governança no Administração** (`/admin`, Fase A, 2026-11-20; padrão ajustado em 2026-11-21): contas administradoras podem bloquear soluções e sub-recursos por usuário ou globalmente e definir cota de armazenamento em MB (padrão 200 MB); contas comuns ficam isoladas dos dados e rotas administrativas.
- **Catálogo & Estoque** (`/catalogo`, Fase B, 2026-11-20): cadastro de produtos/serviços com custo, venda, margem unitária, saldo mínimo e histórico de movimentações; pedidos com baixa automática de estoque e confirmação explícita de sincronização no Meu Orçamento e CRM (D2, 2026-11-21), além de fonte ao vivo nos painéis do CRM.
- **Propostas & PDFs** (`/propostas`, Fase B, 2026-11-20): emissão 100% local de propostas, ordens de serviço, contratos e recibos A4 em PDF (sem vínculo bancário ou Pix), com envio direto pelo WhatsApp da Mensageria, arquivamento direto no Cofre e modal de aprovação integrada ao CRM e Meu Orçamento.
- **Projetos & Tarefas** (`/projetos`, Fase C, 2026-11-20): quadros Kanban com prioridades, checklists e prazos integrados à Agenda, apontamento de horas trabalhadas, rentabilidade real ligada às despesas do Meu Orçamento (com criação de etiqueta exclusiva por padrão — D3, 2026-11-21) e criação rápida a partir de CRM, Propostas e Mensageria.
- **Agenda & Compromissos** (`/agenda`, Fase C, 2026-11-20): visões de Dia, Semana, Mês e Próximos reunindo compromissos próprios, follow-ups da Mensageria, fechamentos do CRM, entregas de Projetos, contas a vencer do Meu Orçamento e validades do Cofre (6ª camada), com confirmação direta pelo WhatsApp.
- **Cofre & Garantias** (`/cofre`, Fase D, 2026-11-21): arquivo permanente de PDFs e imagens (até 15 MB por arquivo dentro da cota da conta) com leitura/OCR 100% local de até 5 páginas para busca pelo texto interno, radar de validades conectado à Agenda 360° e cópia permanente de mídias da Mensageria ou PDFs A4 de Propostas.
- **Caderno & Conhecimento** (`/caderno`, Fase D, 2026-11-21): base de notas em Markdown com modelos prontos, conexões internas `[[...]]`, painel de ligações de ida e volta (backlinks), busca por relevância BM25 100% local e acesso rápido ao roteiro de respostas direto da Mensageria.
