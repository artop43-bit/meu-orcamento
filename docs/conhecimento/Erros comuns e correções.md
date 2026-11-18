---
tags: [meu-orcamento, erros, aprendizado]
---
# Erros comuns e correções

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

## Frontend
- `useEffect` que refaz texto editável: substitui o que foi digitado (ok quando é intencional).
- Download de PDF gerado a partir de dados do formulário → POST com corpo, não GET.

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
