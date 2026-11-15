# v1.9.0 · Avisos por webhook — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a pessoa cola um webhook em Ajustes › Preferências e escolhe quais dos 6 avisos chegam lá.

**Architecture:** novo serviço `app/services/webhook.py` (validação de endereço, formato por
serviço, envio com `urllib`). Entra no fluxo pelo `push.send` (todos os avisos passam por ele) e,
para o resumo do mês, direto no `notify.run_daily`. API em `/notifications/webhook`. Cartão novo
no front, no mesmo estilo de "Avisos por e-mail".

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest · React + TanStack Query, vitest · Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-11-15-webhook-notificacoes-design.md`

## Global Constraints
- Sem dependência nova; HTTP por `urllib.request` (padrão de `app/services/indicators.py`).
- Tipos (ordem fixa): `due`, `monthly`, `weekly`, `daily`, `messages`, `alerts`.
- Todas as caixinhas **desligadas** por padrão. Pausa após **5** falhas seguidas. Tempo limite **5 s**.
- Endereço: `https`, até 500 caracteres, sem usuário/senha, IP de destino público.
- Erros: `AppError(400, "webhook_invalido", "<mensagem em português>")`.
- Textos em português do Brasil, linguagem simples. Linha máx. 100 (ruff).
- Versão **1.9.0**: `changelog/`, `frontend/src/release.ts`, `frontend/src/lib/releases.ts`.

## Review Focus
1. Endereço que resolve para IP interno (`127.0.0.1`, `10.x`, `169.254.169.254`, `::1`) ou que
   redireciona → nunca recebe requisição. (Teste na Task 1.)
2. Webhook fora do ar (timeout, 404, 500) → aviso por e-mail/aparelho continua saindo e o
   `run_daily` não quebra para os outros usuários. (Teste na Task 2.)
3. "Esconder valores" ligado → nenhum `R$` no que vai ao webhook. (Teste na Task 2.)
4. Pessoa com aparelho desligado (`push_*` falso) mas webhook ligado → webhook recebe mesmo assim;
   e o contrário: webhook desligado não muda nada do push atual. (Teste na Task 2.)
5. Endereço salvo nunca volta inteiro pela API (só a dica). (Teste na Task 3.)

---

### Task 0: Menu recolhido em janelas baixas (correção pedida pelo usuário)

**Causa:** `visual.css:2406` põe `overflow: visible` no `.sidebar` recolhido (para as etiquetas e
os painéis de subitens saírem à direita). Com isso o menu deixa de rolar; somando cabeça, 8 ícones
de 44 px, ferramentas e rodapé dá ≈ 790 px, e no estilo Liquid glass o menu tem `100vh − 28px`.
Numa janela com ≈ 690 px úteis os últimos ícones (sair) vazam para fora da moldura.

**Files:**
- Modify: `frontend/src/visual.css` (bloco "menu lateral recolhível", dentro de `@media (min-width: 1024px)`)
- Modify: `e2e/layout.py` (checagem nova)

- [ ] **Step 1: Checagem que falha** em `e2e/layout.py`: com o menu recolhido, nos tamanhos
  1366×690, 1280×640 e 1440×560, nos estilos Padrão e Liquid glass, o último botão do rodapé
  (`.sidebar__footer-row > :last-child`) fica dentro do retângulo do `.sidebar` **ou** o `.sidebar`
  rola (`scrollHeight > clientHeight` e `overflow-y` = `auto`).
- [ ] **Step 2:** rodar `layout.py` → falha em 1366×690 (reproduz o print).
- [ ] **Step 3: Compactar** com `@media (min-width: 1024px) and (max-height: 820px)` no menu
  recolhido: ícones de 44 → 38 px, `gap` da cabeça 10 → 6, `padding-block` do menu 20 → 12,
  ferramentas 36 → 32 px, `padding-top` do rodapé 14 → 8. Meta: tudo cabe a partir de ≈ 640 px.
- [ ] **Step 4: Último recurso** com `(max-height: 639px)`: o menu recolhido volta a rolar
  (`overflow-y: auto`); as etiquetas e os painéis de subitens passam a abrir **dentro** do menu
  rolável sem sumir (painel de subitens com `position: static` abaixo do ícone, como no menu aberto).
- [ ] **Step 5:** `layout.py`, `acessibilidade.py` e `cores.py` → 0 falhas; fotos 1366×690 antes/depois. Commit `v1.9.0: menu recolhido cabe em janelas baixas`.

### Task 1: Serviço de webhook (validação, formato, envio)

**Files:**
- Create: `backend/app/services/webhook.py`
- Modify: `backend/app/models/user.py` (3 colunas em `User`, depois de `push_daily`)
- Create: `backend/alembic/versions/20261115_0032_v190_webhook.py` (revision "0032", down "0031")
- Test: `backend/tests/test_v19_webhook.py`

**Interfaces:**
- Produces:
  - Colunas: `webhook_url: str | None` (String 500), `webhook_kinds: str | None` (Text, JSON
    lista), `webhook_failures: int` (SmallInteger, default 0, server_default "0").
  - `KINDS: tuple[str, ...] = ("due", "monthly", "weekly", "daily", "messages", "alerts")`
  - `MAX_FAILURES = 5`, `TIMEOUT = 5`
  - `validate_url(url: str) -> str` — devolve o endereço limpo ou levanta `AppError`.
  - `url_hint(url: str) -> str` — `"discord.com/…a8F2"` (host + `…` + 4 últimos caracteres).
  - `service_of(url: str) -> Literal["discord", "slack", "generic"]`
  - `kinds_of(user) -> list[str]`, `wants(user, kind: str) -> bool` (falso se sem URL ou pausado)
  - `paused(user) -> bool` (`webhook_failures >= MAX_FAILURES`)
  - `build_payload(service, kind, title, body, link, sections: list[Section] | None) -> dict`
  - `send(db, user, kind, title, body, link="/", sections=None, force=False) -> bool`
  - Internos para mock nos testes: `_resolve(host: str) -> list[str]`, `_post(url, payload) -> bool`

- [ ] **Step 1: Testes que falham** em `test_v19_webhook.py`:
  - `test_validate_rejeita_http_e_credenciais`: `http://x.com/a`, `https://u:p@x.com/a`, `ftp://…`,
    endereço com 501 caracteres → `AppError` com `error == "webhook_invalido"`.
  - `test_validate_rejeita_ip_interno` (parametrizado): com `_resolve` devolvendo `127.0.0.1`,
    `10.0.0.5`, `192.168.1.1`, `169.254.169.254`, `::1`, `fd00::1` → `AppError`; com
    `["93.184.216.34"]` → devolve o endereço.
  - `test_validate_rejeita_host_inexistente`: `_resolve` levanta `OSError` → `AppError`.
  - `test_service_of`: `https://discord.com/api/webhooks/1/abc` e `https://discordapp.com/api/webhooks/1/abc`
    → `"discord"`; `https://hooks.slack.com/services/T/B/X` → `"slack"`; `https://n8n.meu.dev/w` → `"generic"`.
  - `test_url_hint`: `"https://discord.com/api/webhooks/1/xyza8F2"` → `"discord.com/…a8F2"`.
  - `test_payload_discord`: tem `embeds[0]["title"] == title`, `embeds[0]["description"]` contém o
    body, `embeds[0]["url"]` termina com o link; linhas das seções viram `fields`; sem chave `text`.
  - `test_payload_slack`: tem `text` com título em negrito (`*título*`) e o body.
  - `test_payload_generico`: chaves `event == kind`, `title`, `body`, `link` (absoluto),
    `sent_at` (ISO), `sections == [{"title", "rows": [{"description","date","value"}], "note"}]`,
    e `text == content` (texto pronto).

- [ ] **Step 2:** `cd backend && uv run pytest tests/test_v19_webhook.py -q` → FAIL (módulo não existe).

- [ ] **Step 3:** Implementar colunas, migração e `webhook.py`.
  - IP público: `ipaddress.ip_address(ip).is_global` e não `is_multicast`; todos os IPs resolvidos
    precisam passar. `_resolve` usa `socket.getaddrinfo(host, 443)`.
  - `_post`: `Request(url, data=json, headers={"Content-Type": "application/json",
    "User-Agent": "MeuOrcamento-Webhook"})`, opener com um `HTTPRedirectHandler` que recusa
    redirecionamento; status 2xx → `True`; qualquer exceção → `False`.
  - Link absoluto pela mesma regra de `notify._link`. Discord: `description` até 4096, `fields` até 25.
  - `send`: se `not force and not wants(user, kind)` → `False`. Revalida o endereço (IP) antes de
    postar. Sucesso zera `webhook_failures`; falha soma 1; ao chegar em 5 cria
    `InboxItem(kind="alert", title="Webhook pausado", body="Os avisos pararam de chegar ao seu webhook depois de 5 tentativas sem resposta. Confira o endereço em Ajustes › Preferências.")`.
    Nunca levanta exceção (loga `logger.warning`).

- [ ] **Step 4:** Testes extras e rodar:
  - `test_send_conta_falhas_e_pausa`: `_post` → `False` 5 vezes → `paused(user)` e 1 `InboxItem`
    "Webhook pausado"; 6ª chamada não chama `_post`.
  - `test_send_sucesso_zera_falhas`.
  - `test_send_revalida_ip`: `_resolve` muda para `127.0.0.1` depois de salvo → `_post` não é chamado.
  Run: `uv run pytest tests/test_v19_webhook.py -q` → PASS. `uv run alembic upgrade head && uv run alembic check` → sem diferenças.

- [ ] **Step 5:** Commit `v1.9.0: serviço de webhook (validação, formato e envio)`.

### Task 2: Ligar o webhook aos avisos

**Files:**
- Modify: `backend/app/services/push.py` (`send`)
- Modify: `backend/app/api/push.py` (rota `/test`)
- Modify: `backend/app/services/notify.py` (`run_daily`)
- Test: `backend/tests/test_v19_webhook.py`

**Interfaces:**
- Consumes: `webhook.send`, `webhook.wants` (Task 1).
- Produces: `push.send(db, user, kind, title, body, url="/", force=False, sections=None, webhook=True) -> int`
  — chama `webhook.send(db, user, kind, title, body, url, sections)` **antes** do retorno antecipado
  quando `webhook=True`; o resto igual.

- [ ] **Step 1: Testes que falham** (`_post` capturado numa lista, push desligado/sem aparelho):
  - `test_vencimento_vai_ao_webhook_sem_aparelho`: `push_due=False`, `notify_due=False`, webhook com
    `["due"]`, conta vencendo → `run_daily` posta 1 vez com `event == "due"` e linhas da seção.
  - `test_resumo_do_mes_e_disponivel_hoje`: com `["monthly","daily"]` no 1º dia do mês financeiro →
    posta `monthly` e `daily`, mesmo com `notify_monthly=False` e `push_daily=False`.
  - `test_resumo_semana_segunda`: `["weekly"]` numa segunda → 1 post `weekly`.
  - `test_mensagens_e_alertas`: resposta na caixa (`inbox`) e alerta de gasto (`alerts`) → posts `messages` e `alerts`.
  - `test_tipo_desligado_nao_envia`: webhook só com `["weekly"]` → vencimento não posta.
  - `test_esconder_valores`: `notify_hide_values=True` → nenhum payload contém `"R$"`.
  - `test_webhook_fora_do_ar_nao_quebra`: `_post` levanta/retorna `False` → e-mail de vencimento sai
    igual (`outbox`) e `run_daily` processa o segundo usuário.
  - `test_teste_do_aparelho_nao_vai_ao_webhook`: `POST /push/test` → nenhum post.
  - `test_sem_webhook_nada_muda`: os testes atuais de `test_v10_push.py` e `test_v13.py` continuam passando.

- [ ] **Step 2:** `uv run pytest tests/test_v19_webhook.py -q` → FAIL.

- [ ] **Step 3:** Implementar:
  - `push.send` como em Interfaces; `api/push.py` `/test` passa `webhook=False`.
  - `run_daily`: condições de entrada viram `notify_due or push_due or webhook.wants(user, "due")`,
    idem `weekly`; `daily` vira `push_daily or webhook.wants(user, "daily")`; `monthly` vira
    `(notify_monthly or webhook.wants(user, "monthly")) and dia certo`, e-mail só se `notify_monthly`,
    depois `webhook.send(db, user, "monthly", message.heading, message.intro, "/orcamento", message.sections)`.
  - Chamadas de `push.send` em `due` e `weekly` passam `sections=message.sections`.

- [ ] **Step 4:** `uv run pytest -q` (suíte inteira) → PASS; `uv run ruff check . && uv run ruff format --check .` → limpo.

- [ ] **Step 5:** Commit `v1.9.0: avisos do dia, caixa e alertas também no webhook`.

### Task 3: API de configuração

**Files:**
- Modify: `backend/app/api/notifications.py`
- Test: `backend/tests/test_v19_webhook.py`

**Interfaces:**
- Produces (todas exigem login):
  - `GET /notifications/webhook` → `WebhookOut {configured: bool, hint: str | None, service: "discord"|"slack"|"generic"|None, kinds: list[str], paused: bool}`
  - `PUT /notifications/webhook` corpo `{url: str}` → valida, salva, zera falhas → `WebhookOut`
  - `PATCH /notifications/webhook` corpo `{kinds: list[Literal[...6 tipos]]}` → `WebhookOut`
  - `POST /notifications/webhook/test` → `{ok: bool}`; envia `force=True`, kind `"messages"`,
    título "Webhook conectado", texto "A partir de agora os avisos que você escolher chegam aqui.";
    sucesso tira a pausa. Sem endereço → 400 `webhook_invalido`.
  - `DELETE /notifications/webhook` → apaga url, kinds e falhas → `WebhookOut`

- [ ] **Step 1: Testes que falham:** `test_api_fluxo_completo` (PUT → GET mostra `hint`,
  `kinds == []`; PATCH `["due","weekly"]`; teste ok; DELETE → `configured False`);
  `test_api_nunca_devolve_url_inteira` (o texto da URL não aparece em nenhuma resposta);
  `test_api_url_invalida_400`; `test_api_kind_desconhecido_422`; `test_api_teste_tira_pausa`.
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** rodar → PASS.
- [ ] **Step 5:** Commit `v1.9.0: configurar o webhook pela API`.

### Task 4: Tela em Ajustes › Preferências

**Files:**
- Create: `frontend/src/api/webhook.ts` (tipos + chamadas, `queryKey: ["webhook"]`)
- Create: `frontend/src/lib/webhook.ts` + `frontend/src/lib/webhook.test.ts`
- Create: `frontend/src/components/WebhookSettings.tsx`
- Modify: `frontend/src/pages/Preferences.tsx` (logo depois do cartão "Avisos por e-mail")

**Interfaces:**
- Consumes: rotas da Task 3.
- Produces: `WEBHOOK_KINDS: {key: Kind, label: string}[]` (ordem dos Global Constraints) e
  `serviceLabel(service) -> string` (`"Discord"`, `"Slack"`, `"Outro serviço"`).

- [ ] **Step 1: Teste que falha** `webhook.test.ts`: 6 tipos na ordem; rótulos:
  "Lembrete de vencimentos", "Resumo do mês", "Resumo da semana (segundas)", "Disponível hoje",
  "Mensagens da caixa", "Alertas de gastos fora do padrão"; `serviceLabel` dos 3 casos.
- [ ] **Step 2:** `cd frontend && npm test -- webhook` → FAIL. **Step 3:** implementar.
- [ ] **Step 4: Cartão** `section.card.stack`, título `<h2>` "Avisos por webhook", texto curto:
  "Receba os avisos num servidor seu: Discord, Slack ou qualquer endereço que aceite webhook."
  - Sem endereço: campo `<label htmlFor>` "Endereço do webhook" + botão "Salvar".
  - Com endereço: "Conectado a {serviceLabel} · {hint}", botões "Enviar teste" e "Remover";
    se `paused`, `Alert` "Os envios estão pausados: o endereço não respondeu 5 vezes. Envie um teste para retomar.";
    6 `label.check` com checkbox (PATCH a cada mudança, `announce` como em "Avisos por e-mail").
  - Erros pela `errorMessage` existente. Só classes/componentes já existentes (`Button`, `Alert`, `check`).
- [ ] **Step 5:** `npx tsc -b && npm test && npm run build` → PASS. Commit `v1.9.0: cartão Avisos por webhook`.

### Task 5: e2e, versão e fotos

**Files:**
- Modify: `e2e/persona.py` (novo `@step` depois de `email_notices`)
- Create: `changelog/2026-11-XX_v1.9.0.txt`; Modify: `frontend/src/release.ts`, `frontend/src/lib/releases.ts`

- [ ] **Step 1:** Passo e2e "Avisos por webhook: salvar, escolher avisos e remover": salva
  `https://hooks.slack.com/services/T000/B000/XXXX`, confere "Conectado a Slack", liga "Resumo da semana",
  confere `api(page, "/notifications/webhook")["kinds"] == ["weekly"]`, remove e confere `configured False`.
  (Sem "Enviar teste" no e2e, para não postar fora.)
- [ ] **Step 2:** rodar persona, layout, acessibilidade, cores (ver Testes e auditorias) → 0 falhas.
- [ ] **Step 3:** fotos desktop e celular do cartão para o usuário aprovar.
- [ ] **Step 4:** 3 arquivos de versão com o horário estimado (≈ 56 min depois de abrir o PR).
- [ ] **Step 5:** Commit `v1.9.0: avisos por webhook`, PR → CI → merge → Deploy → avisar no celular.
