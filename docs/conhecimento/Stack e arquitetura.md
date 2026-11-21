---
tags: [meu-orcamento, arquitetura]
---
# Stack e arquitetura

## Motores locais da Reforma Tributária
- Integrações RTC com revisões fixadas em `integrations/rtc/` — cálculos e tabelas da Receita
  rodam localmente e o backend consulta os três motores pela rede interna do Compose (2026-11-20).
- `/api/rtc/` exige acesso ao Meu Orçamento. As calculadoras usam SQLite fiscal somente para
  leitura. O gerador recebe XML por requisição e devolve PDF sem persistência. Operação e limites
  em [Motores da Reforma Tributária](../../integrations/rtc/README.md).

## Ajustes da revisão de 20/11/2026
- A migração `0039` remove `refresh_interval_minutes` e `sync_failures` sem recriar o banco;
  as rotas sem tela e o campo `entities` da prévia de PDF foram retirados — manter apenas
  os recursos aprovados (2026-11-20).
- PDF do CRM reutiliza `app.services.ocr.extract`, com o mesmo motor/semáforo do leitor de
  cupons; renderização limitada a 12 MP e 4.096 px por lado — evita motores duplicados e
  páginas desproporcionais na memória (2026-11-20).
- Uploads da Mensageria e leitura de PDF do CRM executam o trabalho bloqueante em rotas
  síncronas; recebimento assíncrono do corpo continua limitado — preserva o loop da API (2026-11-20).
- O bot importa o vocabulário comum e reutiliza os serviços financeiros das telas; seu
  localizador pré-filtra candidatos no banco antes do BM25 — mantém os cálculos consistentes
  e reduz o custo da busca (2026-11-20).

## Repositório
```
backend/    API em Python (FastAPI + SQLAlchemy + Alembic), gerenciado com uv
frontend/   React + Vite + TypeScript (TanStack Query)
android/    App Android (TWA, abre o site)
deploy/     Caddy, backup (age) e scripts do servidor
e2e/        Auditorias pela interface (Playwright em Python)
changelog/  Um .txt por versão
```

## Backend
- FastAPI com routers em `app/api/*`, regras em `app/services/*`, modelos em `app/models/*`.
- Dinheiro: `Numeric(12,2)` + `Decimal`; taxas `Numeric(8,4)`.
- Migrações Alembic numeradas (`20261114_0031_...py`, revision "0031", down "0030").
  Nomes de chaves estrangeiras seguem a convenção `fk_<tabela>_<coluna>_<tabela_ref>`.
- Erros para o usuário: `AppError(status, "codigo", "mensagem em português")` →
  JSON `{"error": "codigo", "message": "..."}`.
- Lint/format: `ruff check .` e `ruff format --check .` (linha máx. 100).
- PDF gerado no servidor com **fpdf2** + fonte Inter embutida (sem serviço externo).
- Indicadores (CDI, IPCA) do Banco Central com cache; se falhar, a tela segue sem eles.

## Frontend
- Páginas em `src/pages`, componentes em `src/components`, API em `src/api/*`.
- Hub de Soluções (`HubShell` + `Hub.tsx` + `lib/hub.ts`): após entrar, concentra a escolha da solução e as áreas da conta/plataforma (Perfil, Segurança, Preferências globais, App, Mensagens, Notas da versão e Administração); cada solução (como o Meu Orçamento no `Shell` e a Mensageria no `MessagingShell`) mantém só suas telas/ajustes e o "Sair" interno retorna ao Hub (2026-11-18).
- Transição entre o Hub e as soluções (`SolutionTransition.tsx` + regras puras em `lib/hub.ts`): provider fora do `<Suspense>` geral (a animação fica na tela enquanto a solução carrega e só sai quando ela montou), saída com esmaecimento, e `SolutionGate` (com `key` por solução) que leva ao Hub qualquer salto direto de uma solução para outra — só CSS, sem View Transitions na navegação, que já são usadas na troca de tema (2026-11-19).
- Solução Mensageria: modelos em `app/models/messaging.py` (migrações `0034`, `0035` e `0036`), serviço em pastas `app/services/messaging/` (`phones`, `sessions`, `chats`, `messages`, `media`, `cleanup`, `connector`, `connector_client`, `budget`), rotas da tela em `app/api/messaging.py` e do conector em `app/api/messaging_connector.py`; tela em `MessagingShell.tsx`, `pages/Messaging.tsx` e `components/messaging/*` — busca incremental (`since`/`cursor`), mídias (até 8 MB) e avatares guardados no Postgres e limpeza semanal (7 dias) via `cli.py` `cleanup(db)` (2026-11-20).
- Conector do WhatsApp (`integrations/whatsapp/`, Node 24 + Baileys `7.0.0-rc14` fixo): supervisor + processos por sessão (`hash(session_id) % WORKERS`), credenciais no Postgres (`messaging_auth_keys`), eventos em lote para a API com `X-Connector-Token`, download/envio de mídias em segundo plano, fila espaçada de fotos de perfil e resolução bidirecional `pnJid ↔ lidJid` — substituiu o adaptador `whatsapp-web.js` (2026-11-20).
- Solução Dashboard & CRM (`/crm`, `id: "dashboard-crm"`): modelos em `app/models/crm.py` (migração `0037`, 9 tabelas com FKs reais para `users`, `messaging_chats` e `incomes`), serviços em `app/services/crm/` (`pdf_reader` com PyMuPDF + `leitor_comprovantes` via `app/services/ocr.py`, `csv_reader`, `api_connector` anti-SSRF com credenciais cifradas, `query_engine`, `hub_bridge`, `sources`, `crm`, `dashboards`), API em `app/api/crm.py`, moldura `CrmShell.tsx` e telas `pages/crm/{Dashboards,Pipeline,Contacts,DataSources}.tsx` — sem salto direto entre soluções, respeitando o `SolutionGate` (2026-11-20; atualizado 2026-11-21).
- Estado de servidor com TanStack Query (`queryKey`), invalidar após mutações.
- Download de arquivos pela função `download(path, nome, body?)` (POST quando há body).

## Ambiente local (docker-compose.yml)
`db` (Postgres 17), `backend` (porta 8000) e `frontend` (Vite, http://localhost:5173, repassa
`/api` para a API).
- A API do PC roda com `watchfiles`: a cada `.py` salvo em `backend/app` ou `backend/alembic`, roda
  `alembic upgrade head` e religa a API; migração nova entra no banco sozinha, sem reiniciar o
  Docker. A migração continua escrita à mão (sem `--autogenerate` automático); se ela der erro,
  a API fica fora até o arquivo ser corrigido — ver `docker compose logs backend` — banco local
  nunca fica atrás do código (2026-11-19).
- `whatsapp` (conector da Mensageria, sem porta aberta no PC): religa sozinho quando muda algo em
  `integrations/whatsapp/src` via checagem periódica (`src/dev-watch.js`, já que `node --watch-path`
  não detecta edições do Windows no Docker); a chave `MESSAGING_CONNECTOR_TOKEN` fica no `.env` (2026-11-20).
- O site no Docker usa checagem periódica de arquivos (`VITE_USE_POLLING=1`): no Windows o Vite
  dentro do contêiner não percebia as edições (2026-11-19).

## Produção (docker-compose.prod.yml)
`db` (Postgres 17), `api`, `scheduler` (rotinas diárias), `whatsapp` (conector da Mensageria,
teto de 8 GB, só rede interna), `backup` (cópias cifradas com age), `caddy` (HTTPS + site; responde
404 para `/api/messaging/connector/*` vindo de fora). Imagens montadas para **ARM64** (VM Oracle).
- Capacidade medida (2026-11-20, PC): a API grava ~300 mensagens/s vindas do conector (lote de 100
  em ~0,65 s) sem crescer a memória; conector parado ~270 MB (supervisor + 2 processos); estimativa
  de 30–80 MB por número conectado → 100 números cabem no teto de 8 GB.

## Conceitos do domínio
- **Mês do orçamento** com dia de início configurável (`month_start_day`).
- Receitas (`incomes`) e despesas (`expenses`) por mês; parcelas, recorrências, cartões,
  contas, metas, investimentos, projetos.
- Itens gerados por outra função carregam a origem (`loan_id`, `personal_loan_id`,
  `recurring_id`) e são **refeitos** por uma função `sync` em vez de editados à mão.

## Leitura de comprovante
- Leitura de foto pelo leitor de cupons próprio (`leitor_comprovantes`, repo `artop43-bit/Leitor-de-cupons`, RapidOCR local) no lugar do Tesseract; dependência fixada por commit no `pyproject.toml`; as regras de texto do `ocr.py` ficam como reserva campo a campo e o boleto continua nelas — leitor mais completo (itens, conferência da soma) e sem serviço externo (2026-11-17)


## Referência detalhada do Hub e das soluções (20/11/2026)

## 6. Hub de Soluções, Transição Padrão e Mensageria (branch `exp/hub-solucoes`)

### 6.1 Estrutura do Hub de Soluções
- Após o login, o usuário chega ao **Hub de Soluções** (`/`, moldura `frontend/src/components/HubShell.tsx`).
- Recursos da conta e da plataforma ficam centralizados no Hub (nunca misturados dentro de uma solução):
  - `/perfil`: somente dados do perfil da pessoa (nome, foto, capa, e-mail).
  - `/configuracoes` (botão de engrenagem na barra do Hub): atalhos para `/seguranca`, `/preferencias` (aparência global), `/app`, `/notas` (**Notas da versão separadas por solução**: *Todas as soluções*, *Hub de Soluções*, *Meu Orçamento*, *Mensageria* e *Dashboard & CRM*) e, para contas com `is_admin`, o cartão **Administração** (`/admin`).
  - `/mensagens*` (avisos da administração e solicitações) e `/admin*` (botão **Administração** na barra superior do Hub e cartão em `/configuracoes` para contas `is_admin`; `seed_demo` marca `admin@example.com` com `is_admin=True`).
  - **Governança de acesso e proteção de dados por usuário (Fase A, 2026-11-20)**: migração `0040` (`users.blocked_resources` em JSON e `users.storage_quota_mb`, padrão 50 MB) + regra global em `messaging_connector_kv` (`hub_global_blocked_resources`); dependências `require_solution` / `require_feature` (`feature:whatsapp_connect`, `feature:external_api`, `feature:pdf_ocr_upload`, `feature:data_export`) e `assert_storage_quota` no backend; controle por usuário e global em `/admin` (*Usuários* › *Permissões e cota* e aba *Controle de acesso*), cartão travado com cadeado no Hub e proteção de URL no `SolutionGate`. Contas administradoras são isentas de bloqueios e cotas.
  - Encerrar a sessão da conta (logout real) fica na barra superior do Hub.
- Cada solução tem sua própria moldura (`Shell.tsx` para **Meu Orçamento**, `MessagingShell.tsx` para **Mensageria**), e o botão **Sair** dentro de qualquer solução retorna ao Hub (`/`) sem deslogar a conta.
- **Não existe salto direto entre soluções** (decisão do Arthur, 2026-11-19): para trocar de solução a pessoa volta ao Hub e escolhe. Nenhuma solução tem link/atalho para outra; o `SolutionGate` (em `SolutionTransition.tsx`) leva ao Hub qualquer navegação interna de uma solução direto para outra. Endereço digitado, favorito, recarga e notificação continuam abrindo direto.
- O catálogo central das soluções fica em `frontend/src/lib/hub.ts` (`HUB_SOLUTIONS`).

### 6.2 Transição entre o Hub e as soluções
- Tudo em `frontend/src/components/SolutionTransition.tsx` + regras puras em `frontend/src/lib/hub.ts` (testadas em `hub.test.ts`):
  - `SolutionTransitionProvider` fica no `App.tsx` **fora do `<Suspense>` geral**: a animação continua na tela enquanto o código da solução é baixado (nada de "Carregando…" no meio).
  - **Entrada** (`useEnterSolution`, usado pelos cartões do Hub): no clique a animação (logo → nome) aparece na hora, o código e os dados da solução são pré-carregados (`preloadSolutionRoute` em `pages/lazy.ts`), e ela só sai quando a tela da solução foi montada de verdade (sinal dentro do `<Suspense>` do `SolutionGate`); o conteúdo entra suavemente (`data-solution-entering` no `<html>`).
  - **Saída** (`useLeaveSolution`, botão "Sair" das molduras): a solução esmaece (`data-solution-leaving`) e o Hub aparece com os cartões entrando em sequência.
  - `SolutionGate` recebe `key` por solução no `App.tsx` (o React Router reaproveita a instância entre rotas irmãs).
- Só animação CSS, igual em todos os navegadores: **não usar a View Transitions API** na navegação (ela já é usada na troca de tema e as duas brigam). Respeita "reduzir movimento", Esc/clique pula, cores só por tokens.
- Para integrar uma nova solução: cadastrar em `HUB_SOLUTIONS` (`id`, `name`, `icon`, `to`, `routePrefixes`), registrar o ícone em `SolutionIcon.tsx`, a primeira tela em `preloadSolutionRoute` e envolver a moldura com `<SolutionGate solution="id" key="id">` no `App.tsx`; a moldura usa `data-solution-root="id"` e `useLeaveSolution()` no "Sair".

### 6.3 Solução: Mensageria (`/mensageria`) — WhatsApp de verdade por QR Code
Exceção à regra "nada que dependa de serviço externo" (seção 2), liberada pelo Arthur em 2026-11-19 **só para a Mensageria**. Sem custo. Conexão **não oficial** (risco de bloqueio do número pelo WhatsApp).
```
[Navegador] --cookie--> [API :8000] <--X-Connector-Token--> [conector "whatsapp" :3100] <--> WhatsApp
                              \------------- Postgres -------------/
```
- **Conector** (`integrations/whatsapp/`, Node 24 + **Baileys `7.0.0-rc14` fixo**; ver o `README.md` dele): conecta o número como "aparelho conectado" (igual ao WhatsApp Web). Supervisor + 2 processos (sessão vai para `hash(session_id) % WORKERS`), no máximo 3 pareamentos ao mesmo tempo por processo, eventos para a API em lote (500 ms / 100), varredura da fila a cada 15 s. Sem porta aberta para fora; teto de 8 GB no `docker-compose.prod.yml`.
  - Cuidados obrigatórios da Baileys (2026-11-19): versão do WhatsApp Web buscada ao vivo (`fetchLatestWaWebVersion`, última boa em `messaging_connector_kv`); nunca tupla de navegador "Desktop"; `syncFullHistory: false`; correção da queda a cada ~50 min (ack de `CB:status`); Node 24 (vazamento de memória em versões antigas); credenciais no Postgres (`messaging_auth_keys`), nunca em arquivos.
  - Mídias, fotos de perfil, nomes e limpeza semanal (2026-11-20):
    - **Nomes corretos e unificação LID/PN**: resolução bidirecional `pnJid ↔ lidJid` no histórico e em `lid-mapping.update` / `chats.upsert` / `chats.update`; cache temporário de contatos chegados antes das mensagens; prioridade de nome (`manual > agenda/contact > apelido/push > fallback`); nomes mascarados (`+55·······80`, `.`, `~`) rejeitados; fusão automática de conversas duplicadas; status real (`✓✓` / lida) preservado no histórico.
    - **Fotos de perfil**: busca em segundo plano limitada (fila espaçada em 350 ms, cache 24 h) salva em `messaging_chats.avatar_data`/`avatar_mime` e servida autenticada em `/api/messaging/chats/{id}/avatar` com fallback para iniciais.
    - **Recebimento e envio de mídias (até 8 MB)**: fotos, áudios, vídeos, figurinhas e documentos baixados em segundo plano pelo conector (`downloadMediaMessage`, histórico ordenado das mídias mais novas para as mais antigas em `mapping.js` com fila de até 120 itens, concorrência 3 e 1 retentativa automática em `session.js`), gravados em `messaging_media` e anexados por `media_attach`; envio na tela por anexo de arquivo, **colar da área de transferência (`Ctrl+V`)**, **arrastar e soltar (`onDrop`)** e gravação de áudio (`MediaRecorder`, `Permissions-Policy: microphone=(self)`), enfileirados no outbox e enviados pela Baileys. SVG é forçado como `document` + `attachment`.
    - **Player de áudio estilo WhatsApp e streaming HTTP Range (`206 Partial Content`)**: `GET /api/messaging/media/{media_id}` detecta o MIME real pelos magic bytes (`sniff_media_mime`: `OggS`, `RIFF..WAVE`, `ID3`/`0xFFE0`, EBML, `ftyp`) e responde a cabeçalhos `Range: bytes=start-end` com `206 Partial Content` + `Accept-Ranges: bytes` + `Content-Range` (permitindo seek e cálculo de duração em qualquer navegador); no frontend, `AudioPlayer` em `MessageBubble.tsx` (`min-width: 248px` / `.wa-msg--audio`, nunca esmagado pelo flexbox) traz botão Ouvir/Pausar, barra deslizante, cronômetro `m:ss`, velocidade **`1x` / `1.5x` / `2x`**, botão baixar e aviso claro quando um áudio antigo do histórico não teve mídia sincronizada.
    - **Copiar mídia para a área de transferência**: botão **Copiar** nos balões de foto/figurinha (`MessageBubble.tsx`) e na janela de zoom (`ChatThread.tsx`) que converte a imagem para PNG em `<canvas>` e grava via `navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])`.
    - **CRM 360° & Finanças dentro da Mensageria (migração `0038`)**:
      - *Etiquetas, status de atendimento e follow-up*: `tags` (`Lead`, `Cliente`, `Orçamento`, `Cobrança`, `Urgente`, `VIP` ou personalizadas), `service_status` (`open`, `waiting`, `resolved`) e `followup_at`/`followup_note` em `messaging_chats`, com filtros na barra lateral (`Todas`, `Não lidas`, `Follow-up`, `Arquivadas` + filtro por etiqueta).
      - *Respostas rápidas com `/` e variáveis inteligentes*: tabela `messaging_quick_replies` (`/api/messaging/quick-replies`, semeada com `/pix`, `/cobranca`, `/boasvindas`, `/orcamento` e `/retorno` + criação/exclusão pelo botão ⚡ ou digitando `/` no `Composer.tsx`), preenchendo `{nome}`, `{telefone}`, `{chave_pix}` e `{valor_pendente}`.
      - *Funil CRM e Meu Orçamento na conversa*: no `ContactSheet.tsx` ("CRM 360°"), consulta e move a etapa dos negócios do contato ou cria novo negócio no Funil (`GET/POST /api/messaging/chats/{id}/crm-context` e `/crm-deal`) e preenche cobrança Pix em 1 clique (**"Cobrar com Pix no chat"**); em qualquer mensagem (`MessageBubble.tsx`) ou no topo da conversa (`ChatThread.tsx`), o botão **Lançar** extrai valores em `R$` do texto (`extractMoneyFromMessage`) e registra Receita ou Despesa real no mês atual do Meu Orçamento (`POST /api/messaging/chats/{id}/budget-entry`).
    - **Limpeza semanal (7 dias)**: `app/services/messaging/cleanup.py` chamado em `cli.py` `cleanup(db)` (diário no `scheduler`) remove mensagens e mídias com mais de 7 dias e conversas inativas não fixadas apenas do banco do Hub (nunca apaga nada do celular e preserva conversas fixadas).
  - Fica de fora: grupos, status e canais. Histórico só no primeiro pareamento (até 50 conversas × 20 mensagens).
- **Banco**: migrações `0034` (tabelas), `0035` (conector: `wanted`, `lid_jid`, `updated_at`/`claimed_at` nas mensagens, único `(user_id, external_id)`, tabelas `messaging_auth_keys` e `messaging_connector_kv`; `@c.us` → `@s.whatsapp.net`), `0036` (`name_source`, `avatar_data`/`avatar_mime`/`avatar_updated_at` em `messaging_chats`, tabela `messaging_media` e `media_id` em `messaging_messages`) e `0038` (`tags`, `service_status`, `followup_at`, `followup_note` em `messaging_chats` e tabela `messaging_quick_replies`).
- **API** (`backend/app/services/messaging/` em partes: `phones`, `sessions`, `chats`, `messages`, `media`, `cleanup`, `connector`, `connector_client`, `budget`):
  - Tela: `/api/messaging/session` (+ `/connect`, `/disconnect`), `/chats`, `/chats/{id}`, `/chats/{id}/avatar`, `/chats/{id}/messages?since=` (devolve `{items, cursor}`), `/chats/{id}/media`, `/media/{id}`, `/budget-context`.
  - Conector: `/api/messaging/connector/{sessions,outbox,events}` e `/sessions/{id}/{media,avatar}` com `X-Connector-Token` (`MESSAGING_CONNECTOR_TOKEN`). O Caddy responde 404 para essas rotas vindas de fora.
  - Sem WhatsApp conectado **não se envia** (409 `whatsapp_disconnected`); acabou o "enviada" falso.
- **Frontend**: `MessagingShell.tsx` (moldura + janela de conexão via contexto do Outlet), `pages/Messaging.tsx` (orquestra) e `components/messaging/*` (`ChatAvatar`, `ChatList`, `ChatThread` com zoom de imagem, `MessageBubble` com foto/áudio/vídeo/figurinha/documento, `Composer` com anexo e gravação de áudio, `NewChatSheet`, `ContactSheet` com botão "Salvar no CRM", `ConnectionSheet`). Fundo do QR pelo token `--qr-paper` (branco nos dois modos).
- **Variáveis**: `MESSAGING_CONNECTOR_TOKEN` e `MESSAGING_MAX_SESSIONS` (padrão 100) no `.env`/`.env.production`; sem a chave, a Mensageria avisa "conexão indisponível" e o resto funciona.
- **Atenção nas rotas**: `/mensagens` é a caixa interna do Hub (recados e solicitações); `/mensageria` é a solução de mensagens.
- **e2e**: a persona faz o papel do conector pela API (`X-Connector-Token`), com o endereço do conector inalcançável de propósito. Seletores do cartão do Hub ancorados (`re.compile("^Meu Orçamento")`, `re.compile("^Dashboard & CRM")`): a descrição da Mensageria também cita "Meu Orçamento".

## 7. Solução: Dashboard & CRM (`/crm`, branch `exp/hub-solucoes`)

Integrada ao Hub de Soluções em 2026-11-20 seguindo exatamente o padrão da seção 6 (catálogo `HUB_SOLUTIONS`, transição logo → nome, `SolutionGate` sem salto direto entre soluções, zero custo, zero serviço pago externo, sem IA dentro do produto).

- **Catálogo e moldura**: `id: "dashboard-crm"`, nome **"Dashboard & CRM"**, rota `/crm`, ícone `"crm"` (`LayoutDashboard` em `SolutionIcon.tsx`), `CrmShell.tsx` (`data-solution-root="dashboard-crm"`, navegação desktop + barra inferior móvel para `/crm`, `/crm/funil`, `/crm/contatos`, `/crm/fontes`, e botão **Sair** voltando ao Hub `/`).
- **Banco**: migração `0037` (`backend/app/models/crm.py`, 9 tabelas isoladas por `user_id` com FKs reais do Hub):
  - CRM: `crm_pipelines`, `crm_stages`, `crm_contacts` (FK `messaging_chats.id`), `crm_deals` (FK `incomes.id`), `crm_activities`.
  - Fontes e painéis: `data_sources`, `data_snapshots`, `crm_dashboards`, `crm_widgets`.
- **API e serviços** (`backend/app/api/crm.py` + `backend/app/services/crm/`):
  - **4 fontes nativas ao vivo** (`hub_bridge.py` + `sources.py`): *CRM · Negócios*, *CRM · Contatos*, *Mensageria · Mensagens* (lê `messaging_chats`/`messaging_messages`) e *Meu Orçamento · Lançamentos* (lê `incomes`/`expenses`/`categories`).
  - **Pontes reais (sem salto de rota entre soluções)**:
    - *Mensageria ↔ CRM*: botão "Salvar no CRM" em `ContactSheet.tsx` e janela "Importar da Mensageria" em `pages/crm/Contacts.tsx` (`POST /api/crm/contacts/from-messaging/{chat_id}`).
    - *CRM → Meu Orçamento*: ao marcar um negócio como **Ganho**, botão "Enviar receita ao Meu Orçamento" cria uma receita real (`Income`) no mês atual (`POST /api/crm/deals/{id}/sync-budget`).
  - **Leitor universal de PDF e CSV** (`pdf_reader.py`, `csv_reader.py`): leitura local determinística usando `pymupdf` + `leitor_comprovantes` (`app/services/ocr.py`, até 5 páginas com OCR em PDF escaneado e aviso de corte na prévia; limites `MAX_PDF_BYTES = 15 MB`, `MAX_CSV_BYTES = 10 MB`, `MAX_ROWS = 5.000`, `MAX_CONTACT_IMPORT_ROWS = 2.000`, `MAX_DEAL_IMPORT_ROWS = 1.000`), com 5 estratégias em cascata (tabela nativa, colunas de texto, linhas financeiras, fichas campo:valor, documento livre + OCR local), prévia editável de cabeçalhos/tipos/células e criação opcional de painel automático ou importação direta para Contatos/Negócios do CRM.
  - **Conectores de API REST/JSON** (`api_connector.py`): apenas `https://`, proteção anti-SSRF (bloqueio de IPs privados/loopback/metadata, sem redirecionamentos, timeout 10 s, teto 2 MB e 5.000 linhas) e credenciais cifradas em repouso via `app/core/security.py` (`encrypt`/`decrypt`).
  - **Painéis personalizados** (`dashboards.py`, `query_engine.py`, `components/crm/WidgetChart.tsx`): 6 tipos de widget (`kpi`, `bar`, `line`, `donut`, `funnel`, `table`), filtro de período global e modelos prontos (*Visão CRM*, *Mensageria · WhatsApp*, *Meu Orçamento*, *Fonte importada*, *Em branco*).
- **Frontend**: `api/crm.ts`, `lib/crm.ts`, `components/CrmShell.tsx`, `components/crm/WidgetChart.tsx`, `pages/crm/{Dashboards,Pipeline,Contacts,DataSources}.tsx`. Estilos escopados em `.crm-*` usando 100% tokens de `theme.css` (zero hex em `visual.css`, compatível com Padrão e Liquid glass, claro e escuro).

## 8. Novo bot do Tire sua dúvida (`app/services/bot/`, integrado em 2026-11-20)

Integrado a partir do laboratório `meu-orcamento-bot` (100% local, zero custo, sem IA, mesmo contrato `/api/ask` e histórico de 30 dias em `ask_history.py`):
- **Pacote modular** em `backend/app/services/bot/` (`contracts`, `months`, `text_utils`, `lexicon/{core,domain,intents,navigation}`, `nlu/{corrector,periods,filters,planner}`, `engine/{executor,locator,specials,responder}`) com fachada compatível em `backend/app/services/ask.py`.
- **Parâmetros combináveis**: período/período2 (dias, semanas, meses, trimestres, semestres, anos, intervalos e todo o histórico), categorias, cartões, contas, projetos/etiquetas, formas de pagamento, pessoas (divisões/empréstimos), faixas e valor aproximado (`acima de`, `abaixo de`, `entre X e Y`, `perto de`), flags (`pago`, `em aberto`, `atrasado`, `revisar`, `parcelado`, `fixo`, `essencial`/`supérfluo`, `dedutível IR`, `MEI`), 15 dimensões de agrupamento, busca textual exata/prefixo/fuzzy e continuação de conversa (`"e em setembro?"`).
- **Localizador universal BM25/fuzzy** (`engine/locator.py`): responde `"onde está o lançamento X?"` buscando em despesas, receitas, notas internas, recorrências, transferências, planejados, metas, financiamentos, dívidas, divisões, investimentos e projetos.
- **Guarda de finalidade (`out_of_scope`) + saudações naturais**: saudações casuais (`"OI MANO"`, `"oi tudo bem"`) respondem como ajuda (`help`) sem cair na operadora "Oi" → *Serviços*; perguntas fora do escopo (`"EU SÓ FALEI OI"`, assuntos gerais/aleatórios) devolvem `out_of_scope` com aviso de finalidade e sugestões úteis.
- **Navegação atualizada do Hub** (`lexicon/navigation.py`): `/perfil`, `/seguranca`, `/preferencias`, `/ajustes/preferencias`, `/mensagens/conversas`, `/notas`, `/app` e `/analises?secao=retrospectiva`.
- **Testes**: `test_v17_ask.py`, `test_v175_ask.py`, `test_v176_ask.py` (2.230+ frases), `test_v18_bot_phrases.py` e `test_bot_v2.py` (incluindo bateria de 1.000 cenários aleatórios e adversariais).

## 9. Catálogo & Estoque (`/catalogo`) e Propostas & PDFs (`/propostas`) (Fase B, 2026-11-20)
- **Banco** (migração `0041`, modelos em `backend/app/models/commerce.py`): `catalog_items`, `catalog_movements`, `commercial_orders`, `commercial_documents`, isolados por `user_id` com FKs para `crm_contacts`, `crm_deals` e `incomes`.
- **Serviços e rotas** (`backend/app/services/commerce/{shared,catalog,pdf_doc,proposals}.py`, `backend/app/api/commerce.py`): `catalog_router` (`/api/catalog`, `require_solution("catalogo")`) e `proposals_router` (`/api/proposals`, `require_solution("propostas")`).
- **Integrações nativas (sem salto de rota)**: pedidos e documentos aprovados lançam receita idempotente no Meu Orçamento e negócio ganho no CRM; documentos usam `fpdf2` + fontes locais `Inter` sem nenhum campo ou menção a Pix e enviam o PDF direto para a fila da Mensageria (`send_media_message`); `native_catalog` expõe itens e estoques ao vivo no Dashboard & CRM.
- **Frontend**: moldura compartilhada `SolutionShell.tsx`, `LineItemsEditor.tsx`, `CatalogShell`/`CatalogPage` (`/catalogo` e `/catalogo/pedidos`) e `ProposalsShell`/`ProposalsPage` (`/propostas`). Testes em `backend/tests/test_commerce.py` e `frontend/src/lib/commerce.test.ts`.

## 10. Projetos & Tarefas (`/projetos`) e Agenda & Compromissos (`/agenda`) (Fase C, 2026-11-20)
- **Banco** (migração `0042`, modelos em `backend/app/models/work.py`): `work_projects` (evitando colisão com a tabela `projects` de etiquetas do Meu Orçamento, mas ligada a ela por `budget_project_id`), `project_tasks`, `project_time_entries` e `agenda_events`.
- **Serviços e rotas** (`backend/app/services/work/{projects,agenda}.py`, `backend/app/api/work.py`): `projects_router` (`/api/work/projects`, evitando conflito com `/api/projects` do `money.py`, protegida por `require_solution("projetos")`) e `agenda_router` (`/api/agenda`, protegida por `require_solution("agenda")`).
- **Integrações 360°**: rentabilidade real comparando `budget_value` com despesas marcadas na etiqueta `budget_project_id` + ganho efetivo por hora; linha do tempo da Agenda agregando compromissos próprios, follow-ups da Mensageria, fechamentos do CRM, prazos de Projetos/Tarefas e contas/cartões de `planned.month_calendar`; ações rápidas em CRM, Propostas e Mensageria para abrir projeto/tarefa/compromisso sem salto de rota; preparação e envio de confirmação pelo WhatsApp (`send_message`).
- **Frontend**: `ProjectsShell`/`ProjectsPage.tsx` (Kanban, checklists, horas e rentabilidade) e `AgendaShell`/`AgendaPage.tsx` (Dia/Semana/Mês/Próximos e filtros de camada, incluindo `cofre`). Testes em `backend/tests/test_work.py` e `frontend/src/lib/work.test.ts`.

## 11. Cofre & Garantias (`/cofre`) e Caderno & Conhecimento (`/caderno`) (Fase D, 2026-11-21)
- **Banco** (migração `0044`, modelos em `backend/app/models/memory.py`): `vault_documents` e `notebook_notes` isolados por `user_id` (com FKs `SET NULL` para `crm_contacts`, `work_projects`, `commercial_documents`, `messaging_media` e `messaging_chats`); a mesma migração elevou o padrão de `users.storage_quota_mb` de `50` para `200` MB (incluindo contas que ainda estavam com `50` MB).
- **Serviços e rotas** (`backend/app/services/memory/{vault,notebook,bridges}.py`, `backend/app/api/memory.py`): `vault_router` (`/api/cofre`, `require_solution("cofre")`, OCR opcional sob `require_feature("feature:pdf_ocr_upload")`) e `notebook_router` (`/api/caderno`, `require_solution("caderno")`).
- **Cofre e cota**: aceita apenas PDF (`pymupdf` + `leitor_comprovantes` até 5 páginas), PNG, JPG ou WebP validados com Pillow até 15 MB por arquivo, rejeitando SVG/HTML; download servido com `X-Content-Type-Options: nosniff`; contagem em `admin.py` soma `VaultDocument.size_bytes` na cota; `messaging/cleanup.py` limpa `messaging_media_id`/`messaging_chat_id` antes de expurgar mídias/chats de 7 dias para não apagar arquivos do Cofre nem notas do Caderno; radar de vencimentos alimenta a 6ª camada (`"cofre"`) na Agenda 360°; arquiva direto mídias da Mensageria e PDFs A4 de Propostas.
- **Caderno e Mensageria**: editor Markdown com 5 modelos prontos, extração automática de `[[wikilinks]]`, grafo de backlinks (`/notes/{id}/backlinks`), busca Okapi BM25 local e gaveta **Roteiro** no `ChatThread`/`Composer` da Mensageria.
- **Frontend**: `VaultShell`/`VaultPage.tsx`, `VaultUploadSheet.tsx`, `NotebookShell`/`NotebookPage.tsx`, `api/memory.ts` e `lib/memory.ts`. Testes em `backend/tests/test_memory.py` e `frontend/src/lib/memory.test.ts`.
- **Perfil opcional da Reforma Tributária (`integrations/rtc/compose.yml`)**: serviços `rtc-regular`, `rtc-simples` e `rtc-danfse` usam `profiles: ["rtc"]` para não subirem à força em `docker compose up` de desenvolvimento; scripts de deploy, smoke test e CI passam `--profile rtc` (D1, 2026-11-21).
