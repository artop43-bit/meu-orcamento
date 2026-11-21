# AGENTS.md — Hub de Soluções (Meu Orçamento & Suíte Integrada)

Instruções para qualquer agente de IA que trabalhe neste repositório (Claude, Gemini, Codex,
Copilot...). Plataforma modular multiusuário de finanças, operação e relacionamento: FastAPI + React, servidor ARM64.

## 1. Antes de qualquer tarefa
Leia, nesta ordem, em `docs/conhecimento/`:
1. `Regras de trabalho com o Claude.md` — as regras valem para **qualquer** IA.
2. `Plano do projeto.md` — em que fase estamos e o que vem a seguir.
3. `Pendências.md`.
4. `Erros comuns e correções.md` e `Mudanças rejeitadas pelo usuário.md` — o que não pode se repetir.
5. Conforme a tarefa: `Stack e arquitetura.md`, `Padrão visual.md`, `Testes e auditorias.md`,
   `Fluxo de versão e publicação.md`, `Funcionalidades do produto.md`.

Rode `git pull` antes de começar: o Arthur também edita essas notas pelo Obsidian.

## 2. Regras que não se negociam (resumo; o detalhe está nas notas)
- **Checklist antes de agir**, e esperar aprovação explícita ("Pode seguir"). Responder a uma
  pergunta não é aprovação. Ver `Modelo de checklist.md`.
- **Não incluir nada que não foi pedido**: ideias extras entram como sugestão no checklist.
- **Nada que gere custo** e **nada que dependa de serviço externo** (banco, WhatsApp, gateways,
  APIs pagas). Exceções: a conexão da Mensageria com o WhatsApp (seção 6.3) e os conectores de
  API REST/JSON do Dashboard & CRM (seção 7, só https, sem custo — 2026-11-20).
  **Sem IA dentro do produto.**
- **Manter a estética atual**: componentes e classes existentes, cores só por tokens.
- **Nunca reiniciar, parar ou atualizar o servidor** sem aprovação.
- **Nunca pular ou desligar teste** para ficar verde. Toda funcionalidade nova ganha teste.
- Sempre em **português do Brasil**, linguagem simples; ser honesto sobre o que não foi testado.
- Versões: changelog + `frontend/src/release.ts` + `frontend/src/lib/releases.ts`; uma versão
  por PR; hotfix só para o que trava o uso. **Cada solução tem número e notas próprios**
  (Hub, Meu Orçamento, Mensageria, Dashboard & CRM, Catálogo & Estoque, Propostas & PDFs, Projetos & Tarefas, Agenda & Compromissos, Cofre & Garantias, Caderno); versão publicada não ganha itens novos.

- **Fluxo**: ideia do Arthur → desenvolvida no Claude ou Antigravity → **o Claude monta o plano
  de ação** (o que e como) → os outros agentes executam, cada um no seu branch/worktree. O
  Claude é a segunda cabeça do projeto e revisa as entregas. Ver `Como trabalhamos.md`.
- **Clean code**: código organizado, nomes claros, funções curtas, um assunto por arquivo —
  fácil de achar e ajustar à mão.
- **Antes do PR** de solução nova ou mudança com upload/login/conector externo/dados de outra
  conta: auditoria `security-audit`; testes de ataque `hunt-*` só no site local; `hallmark` só em
  modo `audit`. Ver `Regras de trabalho com o Claude.md` (regras 15–19).

## 3. Repositório público: nada sensível
Não grave em nenhum arquivo do repositório (inclusive `docs/conhecimento/`): IPs ou endereços
de acesso ao servidor, usuários e chaves SSH, segredos, dados da conta Oracle, número ou nomes
de usuários, preferências pessoais do Arthur. Isso fica só nas notas pessoais dele.

## 4. Ao terminar uma tarefa: atualizar a memória
No mesmo PR da tarefa, atualize o que mudou em `docs/conhecimento/`:
- Regra, convenção ou decisão nova → nota certa, no formato `- regra — motivo (AAAA-MM-DD)`.
- Erro novo e como foi resolvido → `Erros comuns e correções.md`.
- Ideia recusada pelo Arthur → `Mudanças rejeitadas pelo usuário.md`.
- Item feito ou novo → `Pendências.md` e `Plano do projeto.md`.
- Versão publicada → `Histórico de versões.md`.

Antes de gravar, veja se já existe para não duplicar. Não apague nem reescreva notas sem pedir.
Os links `[[Nome da nota]]` são do Obsidian: mantenha-os e use o nome exato do arquivo.

## 5. Comandos
- Backend: `cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .`
- Frontend: `cd frontend && npx tsc -b && npm test`
- e2e e demais auditorias: ver `docs/conhecimento/Testes e auditorias.md`.

## 6. Hub, transições e Mensageria (branch `exp/hub-solucoes`)

### 6.1 Hub de Soluções
- Entrada após login em `/`. Conta e plataforma ficam no Hub: Perfil, Segurança,
  Preferências globais, App, Mensagens, Notas da versão e Administração.
- `HUB_SOLUTIONS` em `frontend/src/lib/hub.ts` é o catálogo central.
- Sair dentro da solução retorna ao Hub; encerrar a sessão fica na barra do Hub.
- Governança (`/admin`): bloqueio global e por usuário de soluções e sub-recursos (`require_solution`, `require_feature`), cota em MB (`assert_storage_quota`, padrão 200 MB) e isolamento estrito por `user_id`.
- Não há salto de navegação interna entre soluções: voltar ao Hub para escolher outra.
  Endereço digitado, favorito, recarga e notificação continuam abrindo direto.
- Cada solução tem número, notas e Novidades próprios; versões em preparação não têm data.

### 6.2 Transições
- `SolutionTransitionProvider` fora do Suspense geral; `SolutionGate` com key por solução.
- Entrada só termina quando a tela montou; saída esmaece para o Hub.
- Só CSS, respeitando reduzir movimento. Não usar View Transitions na navegação.

### 6.3 Mensageria
- `/mensageria` é a solução WhatsApp; `/mensagens` é a caixa interna do Hub.
- WhatsApp real por QR Code: Node 24 e Baileys `7.0.0-rc14` fixo, conexão não oficial e sem custo.
- Credenciais no Postgres; conector só na rede interna e autenticado por token.
- Sem conexão, não envia. Só conversas individuais; mídias até 8 MB.
- CRM 360° e Lançar integram os dados das soluções sem salto de rota.
- Limpeza após 7 dias preserva conversas fixadas e com informações de atendimento/vínculos.
- Detalhes técnicos, cuidados da Baileys e rotas: [[Stack e arquitetura]].

## 7. Dashboard & CRM
- `/crm`, moldura `CrmShell`, integrado ao catálogo e transições do Hub.
- Painéis, funil, contatos, fontes internas, leitura local de PDF/CSV e APIs REST/JSON HTTPS.
- OCR local de PDF reaproveita o `leitor_comprovantes` (`app/services/ocr.py`, `MAX_OCR_PAGES = 5` com aviso de corte na prévia; PDF até 15 MB/40 págs, CSV até 10 MB, 5.000 linhas/fonte); importação direta no CRM limitada a 2.000 contatos e 1.000 negócios (2026-11-21).
- Conector de API é exceção autorizada sem custo; exige proteção anti-SSRF e credenciais cifradas.
- Dados isolados por conta; negócio ganho pode gerar receita real uma única vez.
- Sem atualização automática sem agendador, rotas sem tela ou extração de CPF/CNPJ de PDF.
- Componentes existentes, cores por tokens; detalhes em [[Stack e arquitetura]].

## 8. Tire sua dúvida
- Motor modular em `backend/app/services/bot/`, fachada `app/services/ask.py`.
- 100% local e determinístico, sem IA; mesmo contrato `/api/ask` e histórico de 30 dias.
- Filtros combináveis, localizador de lançamentos, saudações e guarda de finalidade.
- Cálculos reutilizam os serviços das telas; vocabulário compartilhado com Lançamento rápido.
- Pergunta financeira não entendida recebe ajuda; assunto externo recebe aviso de finalidade.
- Arquitetura e referências detalhadas em [[Stack e arquitetura]].

## 9. Catálogo & Estoque e Propostas & PDFs (Fase B)
- `/catalogo` (`catalogo`) e `/propostas` (`propostas`), integrados via `SolutionShell` e `SolutionGate`.
- Produtos/serviços, margem, saldo mínimo, pedidos com baixa de estoque e integração idempotente ao Meu Orçamento (`Income`) e ao funil CRM (`CrmDeal`).
- PDFs A4 locais (`fpdf2`) de Proposta, OS, Contrato e Recibo; **sem Pix nem link bancário**.
- Envio direto do PDF para a Mensageria e fonte nativa `native_catalog` ao vivo no Dashboard & CRM.

## 10. Projetos & Tarefas e Agenda & Compromissos (Fase C)
- `/projetos` (`projetos`, API em `/api/work/projects` para não colidir com `/api/projects` de etiquetas do Meu Orçamento) e `/agenda` (`agenda`, API em `/api/agenda`), integrados via `SolutionShell` e `SolutionGate`.
- Kanban, checklists, horas trabalhadas (`ProjectTimeEntry`) e rentabilidade ligada às despesas reais do Meu Orçamento (`work_projects.budget_project_id`).
- Agenda Unificada 360° reunindo compromissos próprios, follow-ups da Mensageria, fechamentos do CRM, prazos de Projetos, vencimentos do Meu Orçamento (`planned.month_calendar`) e validades do Cofre (`cofre`), além de confirmação pelo WhatsApp e criação rápida de tarefas/compromissos direto da Mensageria, CRM e Propostas.

### 10.1 Cofre & Garantias e Caderno & Conhecimento (Fase D)
- `/cofre` (`cofre`, API em `/api/cofre`) e `/caderno` (`caderno`, API em `/api/caderno`), integrados via `SolutionShell`, `SolutionGate` e `HUB_SOLUTIONS`.
- Cofre (migração `0044`, `vault_documents`): arquivo permanente local de PDFs e imagens (PNG/JPG/WebP até 15 MB; rejeita SVG/HTML, valida imagem por Pillow e conta na cota de 200 MB/usuário via `assert_storage_quota`), extração de texto local PyMuPDF + OCR `leitor_comprovantes` (até 5 páginas sob `feature:pdf_ocr_upload`), radar de vencimentos/garantias ligado como 6ª camada `"cofre"` na Agenda 360° e arquivamento direto de mídias da Mensageria e PDFs A4 de Propostas preservado mesmo após a limpeza de 7 dias (`messaging/cleanup.py`).
- Caderno (`notebook_notes`): notas em Markdown com 5 modelos prontos, links internos `[[...]]`, grafo de backlinks bidirecional, busca Okapi BM25 100% local (sem IA) com normalização de acentos e gaveta rápida **Roteiro** na Mensageria inserindo conteúdo na mensagem em composição.

## 11. Padrão de Experiência "Meu Orçamento" (Obrigatório em qualquer tela nova)
Todas as soluções do Hub precisam carregar a **mesma originalidade, leveza conversacional e identidade tátil do Meu Orçamento** (`Month.tsx`, `Splits.tsx`, `Calendar.tsx`, `Goals.tsx`), nos modos **Padrão** e **Liquid Glass** (claro/escuro) e no celular (`390 px`):
- **Abertura humana e protagonista**: `.greeting` com data e resumo vivo da situação + `.card.month-summary` (valor/indicador principal, `<Bar />`/barra de progresso e `.stats`), em vez de fileiras secas de `<Kpi>` genéricos.
- **Listas expansíveis no lugar de planilhão**: preferir `.list-tools.list-tools--pills` (busca + `.pill-group` `.chip-btn[aria-pressed]` com contagem + `"Abrir todos"`) e cartões `.card.person-row` expansíveis (com `<details className="details">` e `<ul className="items">`), evitando `<table>` multi-coluna estilo ERP.
- **Calendários e agendas**: `.cal-summary`, `.card.reminder` ("Hoje e próximos 7 dias"), `.cal-grid` / `.ev` com cor + ícone + `<ul className="legend">`, `.agenda` / `.agenda__day.is-today` / `.agenda__list` e `.charge__text` para envio/cópia de mensagens.
- **Fluxos e formulários**: `.crm-kanban` / `.crm-deal-card` com avanço em 1 toque; `.segmented` / `.chips`, `<MoneyInput>`, `<DateField>`, `<Tip>`, prévia ao vivo em `.summary-box`, `<EmptyGuide>` com exemplo prático brasileiro e `<label htmlFor>` separado em `<textarea>`.
- **Zero cores fixas e zero atalho opaco**: só tokens de `theme.css`; não colocar `style={{ background: "var(--surface-2)" }}` em cartões principais para não furar a translucidez do `visual.css` (**Liquid Glass**). Detalhes em [[Padrão visual]].

## 12. Padrões Técnicos ao Criar Novas Soluções
- **Isolamento e governança**: toda tabela operacional leva `user_id`; registrar solução e sub-recursos em `HUB_SOLUTIONS` + catálogo de governança (`/admin`) e proteger endpoints com `require_solution`, `require_feature` e `assert_storage_quota`.
- **Banco e tipos**: nunca colidir com rotas existentes do Meu Orçamento (ex.: `/api/projects` já é etiquetas em `money.py`, usar prefixo próprio como `/api/work/projects`); somas monetárias sempre com `sum(..., Decimal("0.00"))`; converter IDs para `uuid.UUID(...)` ao consultar colunas SQLAlchemy `Uuid` (compatibilidade com SQLite nos testes); validar `send_message(..., body=...)` por parâmetro nomeado.
- **Fluxo completo**: seguir [[Como trabalhamos]] (checklist → migração & serviços → telas no padrão Meu Orçamento → testes backend/front + Chrome E2E em Desktop Claro, Liquid Glass Escuro e Mobile 390 px → memória no Obsidian).
