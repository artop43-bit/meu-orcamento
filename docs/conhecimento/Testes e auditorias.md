---
tags: [meu-orcamento, testes]
---
# Testes e auditorias

## Retomada da revisão do Hub — 21/11/2026
- Backend e Ruff passaram com 791 testes. TypeScript, build e os 329 testes do frontend
  passaram, assim como os 121 testes do conector do WhatsApp.
- PostgreSQL 17 isolado aplicou as migrações até `0044` e passou no `alembic check`.
  O papel dedicado da Mensageria pôde ser reaplicado e só leu a chave `wa_version`
  na tabela de configuração. O Caddy aceitou o corpo de teste de 15 MiB com margem
  para o formulário e respondeu `413` acima de 20 MB.
- O Chrome conferiu os 76 passos da persona. Houve 75 aprovações na rodada completa.
  O fluxo do mês financeiro, interrompido por uma recompilação durante a rodada,
  passou na repetição com build estável e banco independente.
- Os testes de Termos e Reforma Tributária passaram. O build final da Agenda foi
  conferido a 390 px em Padrão claro e Liquid Glass escuro, com seis cores distintas
  e sem rolagem lateral da página.
- A auditoria de cores passou em 2.520 combinações. A de fluidez passou no build final
  com conta vazia em 348 combinações, após separar o estilo do guia de Análises.
  As medianas foram 6 ms por quadro e 172 ms para abrir a tela no celular simulado.
- A rodada de layout percorreu 300 telas e formulários e encontrou cinco ocorrências
  da descrição longa cortada no pedido. Após trocar o campo por uma área de texto
  que cresce com o conteúdo, pedido e proposta passaram na repetição dirigida nos
  cinco tamanhos, com as descrições inteiras.
- A auditoria de acessibilidade passou sem ocorrências, inclusive sérias ou críticas.

## Termos de uso e Política de privacidade do Hub — 20/11/2026
- `e2e/legal.py` verifica as duas páginas públicas, seus links, a versão e o cadastro antes e
  depois de marcar o aceite, em desktop claro, Liquid Glass escuro e celular de 390 px.
- Os 33 testes de autenticação e segurança passaram, incluindo o registro da versão
  `2026-11-20` no cadastro. TypeScript e os 321 testes do frontend passaram.

## Reforma Tributária no Meu Orçamento — 20/11/2026
- Os três motores oficiais passaram nos testes de contrato em contêineres ARM64 sem rede.
  Foram conferidos IBS, CBS, Imposto Seletivo, resultado parcial, NCM, NBS, classificações,
  fundamentos, atividades do Simples e geração de DANFSe com um XML fictício.
- `e2e/rtc.py` passou no Chrome em 1366 px e 390 px com os motores reais e com respostas de
  teste. O fluxo cobre os dois regimes, busca e uso de classificação, fundamentação e download.
- Os seis testes da API fiscal passaram, incluindo autorização, bloqueio do Meu Orçamento,
  simulação parcial, consulta de tabela e limites do XML.
- TypeScript, build e os 316 testes do frontend passaram. A rodada ampla do backend apresentou
  uma falha fora da integração fiscal em `test_calendar_feed_by_secret_link`, que esperava
  acesso por link secreto sem sessão e recebeu HTTP 401.

## Decisões D1–D4 e Fase D (`/cofre` e `/caderno`) — 21/11/2026
- **Backend**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → **791 testes aprovados**, 0 falhas, 0 pulados (**279 arquivos** formatados; 1 advertência conhecida de depreciação Python 3.12 em `tests/test_v1100_limite_cartao.py`); `alembic upgrade head && alembic check` até `0044` sem pendências.
- **Frontend**: `npx tsc -b && npm test && npm run build` → **36 arquivos de teste / 327 testes aprovados**, 0 falhas; build Vite concluído em 979 ms.
- **Conector WhatsApp (`integrations/whatsapp`)**: `npm test` → **121 testes aprovados (22 suítes)**, 0 falhas, 0 pulados.
- **Playwright E2E (`127.0.0.1:15173`/`18000` isolado em SQLite, com `/api/rtc/**` simulado via `_resposta_exemplo`)**:
  - `e2e/legal.py`: **3/3 OK** (1366 px padrão claro, 1366 px Liquid Glass escuro, 390 px padrão claro).
  - `e2e/persona.py`: **76 ok, 0 falhas** (inclui D2 em Propostas, D3 em Projetos, `Cofre & Garantias` com OCR/validade/desfazer, `Caderno & Conhecimento` com `[[wikilinks]]`/BM25/desfazer e camada `cofre` na `Agenda 360°`).
  - `e2e/rtc.py`: **OK em 1366 px e 390 px** (respostas simuladas `_resposta_exemplo`).
  - `e2e/layout.py`: **300 telas e formulários em 5 tamanhos, 0 problemas**.
  - `e2e/acessibilidade.py`: **0 problemas no total; 0 sérios ou críticos**.
  - `e2e/cores.py`: **63 telas × 2 estilos × claro/escuro × 10 cores = 2.520 combinações, 0 problemas**.
  - `e2e/fluidez.py`: **58 telas × 2 estilos × 3 larguras = 348 combinações, 0 problemas** (mediana de **12 ms** por quadro e **303 ms** no cenário de celular básico).
- **Checagens locais de segurança e concorrência (E6, `hunt_checks.py` após a última edição em `common.py`, instância isolada `127.0.0.1:18000`)**: concorrência 10× (pedido, proposta, negócio CRM, `client_ref` na Mensageria e `GET /api/months/<novo_mes>` sem lock no SQLite), IDOR entre contas incluindo `/cofre` e `/caderno`, upload falso SVG/HTML rejeitado, SSRF, bloqueio de governança e CSV > 10 MB — todos aprovados.

## Revisão geral 21/11/2026 — Hub, Fases A–C e Reforma Tributária (execução local isolada anterior)
- **Backend**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → **787 testes aprovados**, 0 falhas, 0 pulados (**271 arquivos** formatados; 1 advertência conhecida de depreciação do adaptador de datas SQLite/Python 3.12 em `tests/test_v1100_limite_cartao.py`).
- **Frontend**: `npx tsc -b && npm test && npm run build` → **35 arquivos de teste / 325 testes aprovados**, 0 falhas; build Vite aprovado.
- **Conector WhatsApp (`integrations/whatsapp`)**: `npm test` → **121 testes aprovados (22 suítes)**, 0 falhas, 0 pulados.
- **Playwright E2E (`127.0.0.1:15173`/`18000` isolado em SQLite, com `/api/rtc/**` simulado via `_resposta_exemplo`)**:
  - `e2e/legal.py`: **3/3 OK** (1366 px padrão claro, 1366 px Liquid Glass escuro, 390 px padrão claro).
  - `e2e/persona.py`: **74 ok, 0 falhas** (inclui as 8 soluções em `/notas`, Catálogo, Propostas, Projetos e Agenda com desfazer D9).
  - `e2e/rtc.py`: **OK em 1366 px e 390 px** (respostas simuladas `_resposta_exemplo`).
  - `e2e/layout.py`: **290 telas e formulários em 5 tamanhos, 0 problemas** (incluindo detectores `legend-on-card-border`, `escapes-card-bounds` e `control-text-overflow`).
  - `e2e/acessibilidade.py`: **0 problemas no total; 0 sérios ou críticos**.
  - `e2e/cores.py`: **61 telas × 2 estilos × claro/escuro × 10 cores = 2.440 combinações, 0 problemas**.
  - `e2e/fluidez.py`: **56 telas × 2 estilos × 3 larguras = 336 combinações, 0 problemas** (mediana de **12 ms** por quadro e **295 ms** no cenário de celular básico).
- **Checagens locais de segurança e concorrência (E6, `hunt_checks.py` em instância isolada SQLite `127.0.0.1:18000`)**: concorrência 10× (confirmação de pedido, aprovação de proposta, sincronização CRM e `client_ref` da Mensageria), IDOR entre contas, upload SVG/HTML disfarçado, SSRF (`127.0.0.1`, `[::1]`, metadata, `http://`), bloqueio de governança em pontes/timeline, teto de 92 dias na Agenda, `/calendar-feed` inválido (`404`) e CSV > 10 MB recusado — todos aprovados localmente (Postgres 17 em produção e pareamento QR real com WhatsApp seguem em [[Pendências]]).

## Revisão local do Hub e das soluções — 20/11/2026
- Backend: **763 testes aprovados** em SQLite; uma advertência de depreciação do adaptador
  de datas do SQLite/Python 3.12. Ruff passou e os **237 arquivos** estavam formatados.
- Frontend: **315 testes aprovados**, TypeScript e build de produção aprovados.
- Conector WhatsApp: `npm test` aprovado com Node 24.
- Persona: **69 passos validados com reexecuções**. A rodada ampla final teve 67 passos
  aprovados e duas falhas de seletores compartilhados na Mensageria, com efeito em cascata
  no CRM. Após corrigir os seletores e as esperas, os dois fluxos foram repetidos e aprovados
  em cópia isolada dos dados financeiros de QA (**2/2**), incluindo crédito/limite/fatura,
  mídias, contato no CRM, receita do negócio ganho e painel de PDF carregado. A asserção
  antiga de data do rodapé também foi corrigida e aprovada na repetição ampla.
- Layout: **260 telas e formulários em cinco tamanhos**, nenhum problema.
- Acessibilidade: nenhum problema, inclusive nenhum sério ou crítico.
- Cores: **2.200 combinações** (55 telas, dois estilos, claro/escuro e dez cores), nenhum problema.
- Enquadramento e fluidez: **300 combinações**, nenhum problema; mediana de **8 ms** por quadro
  na troca de abas e **256 ms** para tela pronta no cenário de celular básico desta máquina.
- Migrações: banco temporário criado do zero até a **0039**; teste de upgrade/downgrade da
  0039 preservando dados aprovado em SQLite. Postgres real e ARM64 continuam em [[Pendências]].
- O conector foi simulado e os serviços locais de QA foram isolados da produção. O teste
  com QR e celular real continua pendente; estes resultados não comprovam esse pareamento.

| Teste | Comando | O que garante |
|---|---|---|
| Backend | `cd backend && uv run pytest` | ~540 testes (SQLite; CI também em Postgres) |
| Lint | `uv run ruff check . && uv run ruff format --check .` | estilo |
| Migrações | `alembic upgrade head`, `alembic check`, `downgrade`, `upgrade` | banco igual aos modelos |
| Frontend | `cd frontend && npx tsc -b && npm test` | tipos + ~250 testes |
| e2e persona | `e2e/persona.py` | 65 passos de uso real (cadastro ao empréstimo) |
| e2e layout | `e2e/layout.py` | 215 telas/formulários em 5 tamanhos |
| e2e acessibilidade | `e2e/acessibilidade.py` (rodar **da pasta do repositório**) | axe-core, 0 problemas |
| e2e cores | `e2e/cores.py` | 1.840 combinações de contraste |
| e2e fluidez | `e2e/fluidez.py` | quadros e tempo de carga |
| Conector WhatsApp | `cd integrations/whatsapp && npm ci && npm test` | ~116 testes (node:test), Node 24 |

Execução dos e2e: `uv run --no-project --with playwright python e2e/<teste>.py`, com
`QA_CREDENTIALS` e `QA_OUT` definidos e o app rodando (build do front + API + conta de
demonstração `seed-demo --vazia`).

- Sem os navegadores do Playwright instalados no PC, use o Chrome do sistema: `QA_BROWSER=chrome`
  (2026-11-20).
- Mensageria no e2e: a persona faz o papel do conector pela API (`MESSAGING_CONNECTOR_TOKEN`,
  padrão `e2e-conector`) com `MESSAGING_CONNECTOR_URL` apontando para um endereço que não responde
  — não rodar contra o Docker local, onde há um conector de verdade (2026-11-20).
- Carga da Mensageria: simular o conector como ele é (2 processos, cada um com as suas sessões,
  um lote por vez). Misturar as mesmas sessões em vários envios ao mesmo tempo cria disputa de
  linhas no banco que não existe no uso real (2026-11-20).

Regras:
- Toda funcionalidade nova ganha teste de backend **e** um passo no e2e persona.
- Toda nova rota ou tela entra na lista `PAGES` de `e2e/acessibilidade.py` e `e2e/layout.py` (além de `e2e/cores.py` e `e2e/fluidez.py` quando aplicável) — (2026-11-21).
- Não rodar o pytest ao mesmo tempo que os e2e (falhas falsas).
- Nunca pular/desligar teste para ficar verde.
