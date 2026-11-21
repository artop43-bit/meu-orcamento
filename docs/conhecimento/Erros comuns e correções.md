---
tags: [meu-orcamento, erros, aprendizado]
---
# Erros comuns e correções

## Motores da Reforma Tributária (20/11/2026)
- Reservar um tmpfs executável exclusivamente para o SQLite JDBC — o driver extrai
  a biblioteca nativa antes de carregá-la, e o tmpfs comum do Docker não permite isso (2026-11-20).
- Criar o diretório da base fiscal com permissão de travessia antes de copiar o SQLite
  como somente leitura — aplicar `0444` ao diretório impede o usuário do Java de abrir o arquivo (2026-11-20).

## Revisão do Hub antes do primeiro PR (20/11/2026)
- Seletores e2e por classes reutilizadas ficaram ambíguos (`.wa-msg__reply-btn` e
  `.wa-budget-card`) → selecionar ações pelo papel/nome acessível, conferir o valor esperado
  no painel e aguardar a confirmação de salvamento antes de avançar — mantém os testes
  compatíveis com os componentes compartilhados sem reduzir a validação (2026-11-20).
- Teste do rodapé exigia data até para versão em preparação → aceitar o estado explícito
  "Em preparação" ou uma data válida de publicação — acompanha a regra de versões sem
  inventar um horário de lançamento (2026-11-20).
- Lançar da Mensageria criava despesa diretamente e pulava regras do cartão → usar
  `budget.create_expense`, exigir cartão no crédito e manter compra em aberto no mês da fatura
  — evita saldo e limite divergentes do Orçamento (2026-11-20).
- Limpeza e fusão de conversas perdiam informações de atendimento → preservar etiquetas,
  retorno, notas e vínculos; carregar binários só nas rotas próprias — evita perda de contexto
  e transferência desnecessária de imagens no polling (2026-11-20).
- Bot novo refazia cálculos das telas → reutilizar `daily.forecast`, `loans.summary`,
  `cards.invoice`, `splits.board` e `goals.projection`; lançamentos de hoje usam `created_at`
  no fuso da conta — mantém valores e datas iguais aos apresentados nas telas (2026-11-20).
- Localizador montava BM25 de todo o histórico por pergunta → pré-filtrar no SQL e limitar
  candidatos por tabela, com reserva para acentos e busca aproximada — medição local com
  20 mil despesas: cerca de 2.006 ms antes e 36 ms depois (2026-11-20).
- Conector do CRM resolvia o domínio novamente ao conectar → fixar o IP validado, preservar
  nome TLS e aplicar prazo total, bloqueando endereços IPv6 encapsulados privados/NAT64
  — fecha a troca de destino após a validação e a leitura sem prazo total (2026-11-20).
- PDF do CRM criava outro motor OCR e renderizava páginas sem teto → reutilizar o motor e
  semáforo do leitor de cupons, limitar resolução por página e executar uploads fora do loop
  assíncrono — reduz consumo de memória e bloqueio dos demais usuários (2026-11-20).
- Versões novas ainda referenciavam o formato global antigo → usar `SOLUTION_RELEASES` nos
  rodapés, Novidades e relatórios; versão em preparação fica sem data — evita importações
  quebradas e atribuição da versão de outra solução (2026-11-20).

## Processo
- **Agir sem checklist aprovado** → sempre checklist primeiro ([[Regras de trabalho com o Claude]]).
- **Incluir funções não pedidas** (Pix copia e cola, WhatsApp, telefone) → removidas na
  v1.8.0.2. Ver [[Mudanças rejeitadas pelo usuário]].
- **Horário de publicação errado** nas notas → estimar antes do PR e corrigir depois.
- **Mudar arquivo depois de abrir o PR** reinicia o CI (~27 min). Ajustar horário antes.
- **Duas sessões juntando no `main` ao mesmo tempo**: o deploy de uma publica o `main` inteiro,
  inclusive o merge da outra, antes do CI do `main` dessa outra terminar; e a versão sai sem as
  notas da outra mudança (v1.10.0 levou o PR #75 do cartão). Uma sessão por vez junta no `main`;
  quem juntar depois confere o `git log` do `main` e as notas (2026-11-17).
- **Hora errada no Git Bash do Windows**: `TZ=America/Sao_Paulo date` não aplica o fuso (sem
  tzdata) e a estimativa da v1.10.0 saiu 23:55 em vez de ~21:25 → pegar a hora com PowerShell
  `Get-Date` e conferir com o relógio antes de escrever o horário (2026-11-17).
- **Primeira proposta visual fora do padrão** → refazer em cima da tela real, com as classes
  existentes ([[Padrão visual]]).
- **`gh pr merge --auto` junta na hora** — o repositório tem `allow_auto_merge=false`, então não
  existe "juntar quando o CI passar"; esperar o CI do PR e só então fazer o merge (2026-11-15).

## Testes de interface (Playwright)
- **`check()`/`uncheck()` em opção salva no servidor falha às vezes** ("did not change its
  state"): a tela só atualiza no ciclo seguinte (TanStack Query avisa por `setTimeout(0)`). Usar o
  helper `mark()` do `persona.py` (clica e espera `to_be_checked`) (2026-11-15).
- **Rodar a persona também na `main`** antes de culpar a mudança: a falha de Divisões já existia
  na v1.8.0.2 (2026-11-15).

## Testes que dependem da data
- **O CI roda em UTC**: depois das 21h de Brasília já é o dia seguinte. Teste com
  `date.today()` pode passar no PC e falhar no CI — reproduzir trocando a data do teste
  (ex.: `test_card_purchases_come_through_the_invoice` só falhava quando o dia caía numa
  segunda e revelou que o resumo da semana listava a compra do cartão solta) (2026-11-15).
- Valores em reais usam **espaço inquebrável** (`R$ 1.400,00`): normalizar com
  `.replace("\xa0", " ")` ou usar `\s` na regex.
- `get_by_label("Pessoa")` casa com vários elementos → `exact=True`.
- `label` envolvendo um `textarea` faz o nome acessível incluir o texto do campo → usar
  `<label htmlFor>` separado.
- Código Pix tem espaços → regex de linha inteira, não `\S+`.
- `acessibilidade.py` precisa rodar da pasta do repositório (procura o axe-core em
  `frontend/node_modules`).
- Rodar pytest junto com os e2e causa falhas falsas.

## Backend
- **Conflito de rota**: `/loans` já era dos financiamentos → empréstimos a amigos em
  `/friend-loans`.
- `Decimal` com `-(-a // b)` **não** arredonda para cima (trunca) → usar `math.ceil(a / b)`.
- Coluna `UTCDateTime` não aceita `date` → usar `utcnow()`.
- SQLite de produção pode não ter cascade de FK ativo → apagar dependentes explicitamente.
- Nomes de FK na migração devem seguir a convenção do `MetaData` (senão o `alembic check` falha).
- Cabeçalho `Content-Disposition` com acento quebra → nome de arquivo sem acentos.
- `ruff format` reorganiza o código; ao editar por script depois, conferir se a troca aplicou.
- fpdf2: `markdown=True` com fonte já em negrito inverte o negrito → escrever rótulo e texto
  com `write()` separados.
- No termo em PDF, manter fechamento + assinaturas + testemunhas juntos (quebrar página antes).
- **Banco local atrás do código** (ficou na 0033 com a 0034 já no código): o `--reload` do
  uvicorn religava a API mas não rodava o `alembic upgrade head` de novo → no
  `docker-compose.yml` o `watchfiles` roda o alembic e religa a API a cada `.py` salvo em
  `app/` ou `alembic/` (2026-11-19).

- **Mensagens com o mesmo horário** (o WhatsApp manda em segundos) empatam e o desempate é pelo
  uuid aleatório → teste que confere ordem precisa de horários diferentes (2026-11-19).
- **Mensageria marcava "enviada" sem WhatsApp conectado** (envio falso) → sem conexão a API
  recusa (409 `whatsapp_disconnected`) e a caixa de envio fica desativada (2026-11-19).
- **Baileys com a versão do WhatsApp Web que vem na biblioteca** fica velha e derruba a conexão
  (405) → buscar a versão ao vivo a cada conexão e guardar a última boa (2026-11-19).
- **Saldo de empréstimo a amigo na Mensageria (`budget.py`) ignorava parcela paga parcialmente**:
  parcelas com pagamento parcial já têm `received_at` preenchido, então filtrar `received_at.is_(None)`
  omitía o saldo restante → somar `max(amount - received_amount, 0)` igual ao `personal_loans.py` (2026-11-20).
- **Dependência `pypdf` só existe em dev no `pyproject.toml`**: usar `try: from pypdf import PdfReader`
  no leitor de PDF do CRM para que a imagem de produção (com `pymupdf` + `rapidocr-onnxruntime`) não
  quebre na importação (2026-11-20).

## Frontend
- `useEffect` que refaz texto editável: substitui o que foi digitado (ok quando é intencional).
- Download de PDF gerado a partir de dados do formulário → POST com corpo, não GET.
- **React Router reaproveita a instância do elemento entre rotas irmãs** (sem `key`): o
  `SolutionGate` não percebia a troca de solução e o bloqueio entre soluções não funcionava →
  `key` por solução no `App.tsx` (2026-11-19).
- **Regra global de "reduzir movimento" com `!important`** anulava o esmaecimento curto da
  transição (sumia de uma vez) → a regra local precisa vencer com seletor mais forte (2026-11-19).
- **Animação dentro do `<Suspense>` geral some** quando a tela carrega sob demanda (o fallback
  "Carregando…" troca a árvore inteira) → a transição fica fora do `<Suspense>` (2026-11-19).
- **Vite no Docker do Windows não percebe edições** (servia arquivo antigo) → `usePolling` via
  `VITE_USE_POLLING=1` no `docker-compose.yml` (2026-11-20).
- **Container com `overflow-x: auto` sem foco de teclado** falha em `axe-core` (`scrollable-region-focusable`)
  no celular → colocar `tabIndex={0}` e `role="region"` em `.table-scroll` (2026-11-20).

## Acréscimos de 16/11/2026
- **IP "Ephemeral" não se move nem se reserva.** Antes de planejar mover IP, conferir o tipo em
  *Edit Private IP Address*. Mudar para "No public IP" perde o IP para sempre.
- **Guia antigo dizia que o IP era reservado** — conferir no painel, não confiar no documento.
- **`DEPLOY_KNOWN_HOSTS`** precisa começar com o **mesmo IP** do `DEPLOY_HOST`; senão o deploy
  falha com "Host key verification failed".
- **Variável `DOMAIN`** sem `https://` e sem `/` no fim.
- **Nunca deixar uma IA reiniciar o servidor** sem aprovação (derrubou o site).
- **"Stopping" travado na Oracle:** não aceita outro comando até terminar (até ~15 min).
- **Esta sessão na nuvem não alcança SSH (porta 22) nem o Obsidian**: o que é do servidor ou
  do cofre roda no PC do usuário.
- **Compra no cartão de crédito vinha marcada "Já paga"** (caixa marcada sozinha) e não
  diminuía o limite → hotfix v1.9.0.2.
- Compra no crédito **entra no Orçamento do mês da fatura** (correto, não é bug).

## Acréscimos de 20/11/2026
- **`node --watch-path=src` no Docker Desktop (Windows) não detecta edições do PC** (mesmo caso do Vite): o contêiner `whatsapp` ficou rodando código antigo sem mídias/avatares. Corrigido com `integrations/whatsapp/src/dev-watch.js` (checagem periódica via `stat`) no `docker-compose.yml` (produção segue usando `node src/index.js`) — (2026-11-20).
- **Anexo de mídia na Mensageria (`Composer.tsx`) no Chrome/Windows**: manter o `File` cru do disco podia falhar ao montar prévia (`blob:`) e abortar o `FormData` com `ERR_UPLOAD_FILE_CHANGED` / `"Sem conexão com o servidor"`. Corrigido copiando o arquivo (≤ 8 MB) para memória ao selecionar (`snapshotFile`) e adicionando fallback visual no `onError` da miniatura, além de excluir `/api/messaging/` do cache do `sw.js` — (2026-11-20).
- **HTTP 502 transitório ao reiniciar a API (`watchfiles`)**: o cliente (`frontend/src/api/client.ts`) mostrava `"Erro inesperado (502)."`. Agora tenta novamente uma vez em leituras (`GET`) e mostra mensagem amigável em português quando `502`/`503`/`504` persiste — (2026-11-20).
- **Bot "Tire sua dúvida" respondendo *Serviços* para `"OI MANO"` / `"EU SÓ FALEI OI"`**: o bot antigo caía no termo `"oi"` (operadora) da lista de categorias. Resolvido integrando o novo motor composicional (`app/services/bot/`), com saudações casuais (`help`) e guarda de finalidade (`out_of_scope`) — (2026-11-20).
- **Balão de áudio da Mensageria esmagado (~68px, mostrando só `— ⋮` / `● ⋮`) e áudios sem barra de tempo**:
  1. `.wa-msg` é flex shrink-to-fit e, como `mediaCaption("🎤 Áudio", "audio")` retorna `""`, a largura intrínseca do pai vinha só do rodapé `10:50 ✓✓` (~68px); `.wa-media-audio { width: min(260px, 100%) }` resolvia `100%` como 68px. Corrigido com o player customizado `AudioPlayer` (`.wa-audio-player`, `min-width: 248px` e `.wa-msg--audio`) com Ouvir/Pausar, barra deslizante, tempo `m:ss`, velocidade `1x`/`1.5x`/`2x` e botão de download.
  2. `GET /api/messaging/media/{media_id}` devolvia `200 OK` sem `Accept-Ranges: bytes` nem suporte a `Range`, impedindo seek e duração de áudios Ogg/WebM no Chrome/Safari. Corrigido com suporte a `Range: bytes=start-end` (`206 Partial Content`, `Content-Range`, `Accept-Ranges: bytes`) e detecção de MIME por magic bytes (`sniff_media_mime`).
  3. No conector (`mapping.js` / `session.js`), `selectHistory` percorria as conversas da mais nova para a mais antiga e `mediaItems.slice(-40)` pegava as 40 mídias mais antigas em vez das mais recentes. Corrigido ordenando `mediaItems` por timestamp decrescente (`b.ts - a.ts`), usando `slice(0, 80)`, fila de 120 mídias e 1 retentativa automática — (2026-11-20).
- **Painel de Administração (`/admin`) ausente para `admin@example.com` e nas Configurações do Hub (`/configuracoes`)**: `seed_demo` (`backend/app/demo.py`) criava/atualizava `admin@example.com` sem `is_admin=True`, e `HubSettings.tsx` não incluía o cartão de Administração. Corrigido marcando `is_admin=True` em `seed_demo`, adicionando o cartão **Administração** em `HubSettings.tsx` e o botão **Administração** na barra superior do `HubShell.tsx`, além de separar as **Notas da versão** (`/notas`) por solução (`ReleaseNotes.tsx` e `releases.ts`) — (2026-11-20).

## Acréscimos das Fases A, B e C (expansão do Hub — 20/11/2026)
- **Colisão de prefixo `/api/projects`**: o módulo financeiro (`money.py`) já expõe `/api/projects` e a tabela `projects` para etiquetas do Meu Orçamento. Novas soluções não devem reutilizar esse caminho/nome: usar prefixo próprio (`/api/work/projects` e tabela `work_projects` ligada por `budget_project_id`) — (2026-11-20).
- **`str` passado para coluna SQLAlchemy `Uuid` quebra no SQLite dos testes**: SQLite exige `uuid.UUID(...)` (`AttributeError: 'str' object has no attribute 'hex'`), enquanto Postgres aceita strings. Sempre converter com helper `as_uuid` antes de consultar/inserir — (2026-11-20).
- **`sum([...])` de `Decimal` sem valor inicial**: `sum([])` devolve `int(0)` e falha em `.quantize(...)`. Usar sempre `sum(..., Decimal("0.00"))` — (2026-11-20).
- **Chamada posicional em `messaging.send_message`**: `body` é parâmetro nomeado (`keyword-only`). Usar `send_message(..., body=...)` em qualquer integração com a Mensageria — (2026-11-20).
- **Telas novas feitas com `<table>` genérica, `<Kpi>` seco e `style={{ background: "var(--surface-2)" }}` quebram a identidade do Meu Orçamento e o Liquid Glass**: substituir tabelas frias por `.card.person-row` expansíveis + `.list-tools--pills` + `.greeting`/`.month-summary`, e usar `<MoneyInput>`, `<DateField>`, `<EmptyGuide>`, `<Tip>` e `.cal-grid`/`.agenda__list` sem fundos inline opacos — (2026-11-20).

## Acréscimos da revisão 21/11/2026
- **Acesso do conector ao PostgreSQL**: `messaging_connector_kv` guarda também regras de
  governança. Limitar o papel do conector à chave `wa_version` com política por linha,
  além das permissões necessárias em `messaging_auth_keys` — preserva as regras da API (2026-11-21).
- **Palavras partidas no resumo novo de Análises**: a classe `.steps` passou a usar colunas
  para a navegação de etapas. O guia usa `.analysis-start-steps` para manter os passos em
  coluna — evita que cada instrução receba só um terço da tela (2026-11-21).
- **Descrição longa cortada no pedido**: o editor compartilhado de itens usa um campo de
  texto com altura automática — nomes longos de produtos precisam quebrar linha também
  quando são copiados para um pedido ou documento (2026-11-21).
- **Rota pública `/calendar-feed/{token}.ics` ignorava bloqueio do usuário**: por ser link secreto sem cookie de sessão (`CurrentUser`), não passava pela governança padrão — resolver conferindo `effective_blocked_resources` para o dono (`meu-orcamento`/`agenda`) e retornando `404` tanto para token inválido quanto para recurso bloqueado, sem vazar existência — (2026-11-21).
- **Condição de corrida em confirmações/aprovações e primeira criação de `BudgetMonth` no SQLite e no Postgres**: `.with_for_update()` vira no-op no SQLite (onde leituras prévias do request mantêm snapshot antigo), e `ensure_month` fora do lock colidia em `IntegrityError`. Corrigido isolando `ensure_month` com savepoint (`begin_nested()`), movendo-o para depois de `.with_for_update()`, serializando o SQLite com `row_lock_guard` (lock reentrante por profundidade em `Session.info`, além de `FOR UPDATE` no `User` para `client_ref` no Postgres) e passando `client_ref` determinístico em `create_budget_income` (`hub-order-...` / `hub-doc-...` / `hub-deal-...`) — (2026-11-21).
- **Cadeia completa de receita e precisão fracionária (`Catalog`/`Propostas`/`CRM`)**: `create_budget_income` passou a percorrer toda a cadeia de origem (`doc`/`order`/`deal`) evitando receitas duplicadas; quantidades e estoques fracionários usam `Numeric(12, 3)` (sem arredondamento prematuro em 2 casas); cancelamento de pedido/documento preserva receita já recebida no Meu Orçamento emitindo aviso em vez de apagar — (2026-11-21).
- **`toISOString().slice(0, 10)` trocando o dia à noite no Brasil (UTC-3)**: usar sempre o helper local `todayISO()` no frontend para evitar datas adiantadas após 21h — (2026-11-21).
- **Janela ilimitada na Agenda Unificada (`/agenda/timeline`) e vazamento em pontes bloqueadas**: `SafeDate` limita o intervalo a no máximo 92 dias (`400` se passar) e os endpoints de pontes (`/hub/bridges`) e camadas da timeline filtram recursos bloqueados por `/admin/governance` — (2026-11-21).
- **Socket pendente em retentativa de `GET` (`client.ts`), duplo `DELETE` no Undo (`undo.tsx`) e formulário resetado por refetch (`NewOrderSheet.tsx` / `BudgetEntrySheet.tsx`)**: cancelar `response.body?.cancel()` antes de tentar novamente `502`/`503`/`504` em `GET` (evitando travar `networkidle`); usar `ctrl.takeIfKey(item.key)` sem fallback em `commit()`; travar reset de modal aberto via `wasOpen` ref e desabilitar reenvio de lançamento após sucesso (`canSubmitBudgetEntry`) — (2026-11-21).
- **Estouro em celular `390 px` em Propostas (`/propostas`) e Admin E-mails (`/admin?aba=emails`)**: remover `white-space: nowrap` de `.person-row__who strong` (`visual.css`) e garantir `max-width: 100%; overflow-wrap: anywhere` em `.item__main`/`.item__title`/`.item__meta` (`styles.css`) — (2026-11-21).
- **`sqlite3.OperationalError: database is locked` em `GET /api/months/{mes}` (`ensure_month`) sob concorrência e `rollback()` em transações já com `flush()`**: em SQLite `DEFERRED`, duas leituras simultâneas tentavam promover a escrita no `flush()` de `BudgetMonth` e devolviam `SQLITE_BUSY` imediato; além disso, checar só `not db.new/dirty/deleted` no `row_lock_guard` fazia `db.rollback()` apagar registros já enviados via `db.flush()` antes de `ensure_month` (ex.: `restore_backup` e testes do `daily.forecast`). Resolvido habilitando `PRAGMA busy_timeout=30000` e `PRAGMA journal_mode=WAL` (bancos em arquivo) em `app/db/session.py`, protegendo a escrita de `ensure_month` em `app/services/budget.py` com `row_lock_guard(db)` e rastreando escritas na sessão via eventos SQLAlchemy (`_SQLITE_TX_WRITES_KEY` em `app/services/common.py`) para nunca dar rollback em transações já escritas — (2026-11-21).
- **Ordem/dependência E2E da Reforma Tributária (`e2e/rtc.py`) e desalinhamento em `.grid-2` de formulários (`VaultUploadSheet`)**: (1) `rtc.py` importava `persona` (exigindo `--with pyotp` no CI) e marcava `POST /api/onboarding/done` no usuário demo antes do `persona.py`, derrubando o passo `Conta nova` → movido para depois de `persona.py` em `.github/workflows/ci.yml` com `--with pyotp`; (2) `<Tip>` dentro do `<span className="field-label">` em `.grid-2` quebrava o rótulo em duas linhas e deslocava o `DateField` vizinho em `43 px` (`form-cofre-doc`) → usar rótulos curtos de 1 linha na grade e colocar a dica logo abaixo do `.grid-2` — (2026-11-21).
