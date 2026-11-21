---
tags: [meu-orcamento, processo]
---
# Como trabalhamos

## Fluxo de trabalho (2026-11-20)
1. O Arthur tem uma ideia.
2. A ideia é formatada e desenvolvida no Claude ou no Antigravity.
3. O **Claude monta o plano de ação**, detalhando o que precisa ser feito e como (checklist
   aprovado pelo Arthur, ver [[Modelo de checklist]]).
4. O plano vai para os outros agentes executarem — cada um numa tarefa e num branch/worktree
   próprio, nunca dois agentes nos mesmos arquivos ao mesmo tempo.

O Claude atua como **segunda cabeça do projeto**, junto com o Arthur: planeja, revisa o que os
outros agentes entregaram e aponta o que corrigir.

## Memória compartilhada
- **Esta pasta (`docs/conhecimento/`) é a memória de todos os agentes** (Claude no PC, sessão
  na nuvem, Gemini, Codex...). O `AGENTS.md` na raiz manda ler daqui.
- O Arthur lê e edita as mesmas notas pelo Obsidian (a pasta está ligada ao cofre). Edição
  feita no Obsidian só chega aos outros agentes depois de commit e push.
- **Nada sensível aqui**: o repositório é público. Endereço de servidor, usuário e chave SSH,
  dados da conta Oracle, números de usuários e preferências pessoais ficam só nas notas
  pessoais do Arthur.

## Onde cada coisa roda
| Lugar | Para quê | Não usar para |
|---|---|---|
| **PC** com Claude Code | Desenvolvimento do dia a dia, ver mudanças, rodar o site local | — |
| **Sessão na nuvem** (claude.ai/code) | Tarefas longas: PR, CI, deploy, acompanhamento com aviso no celular | Acessar o servidor por SSH ou o Obsidian (não alcança) |
| **Servidor** (SSH + tmux) | Só manutenção (logs, conferir serviços) | Desenvolver; reiniciar ou atualizar sem aprovação |
| **Outra IA (Gemini etc.)** | Peças à parte, com o mesmo `AGENTS.md` | Mexer direto no repositório principal |

## Abas e tarefas
- **Uma aba = uma tarefa = um branch.** Duas abas no mesmo arquivo geram conflito.
- Abas em paralelo: cada uma num "worktree" do git (cópia separada do repositório).

## Peças desenvolvidas à parte (método do leitor de cupons)
1. A peça fica em `laboratorio/<nome>/` no próprio repositório (ou num repositório à parte,
   como o `Leitor-de-cupons`).
2. Recebe e devolve **o mesmo formato** que a peça atual do sistema.
3. Tem um arquivo de **casos reais** com a resposta esperada e mede a % de acerto.
4. Quando a % for melhor que a atual: checklist para trocar; os casos viram teste automático.

O que funciona é o método (isolar + casos reais + medir), não a ferramenta de IA. Outra IA
custa: não conhece as regras (resolvido pelo `AGENTS.md`), outra assinatura e contexto dividido.

## Roteiro padrão ao criar uma nova solução no Hub (2026-11-20)
Para manter todas as entregas futuras (ex.: Fase D e próximas evoluções) fiéis ao produto:
1. **Checklist e escopo**: enviar checklist pelo [[Modelo de checklist]] e aguardar aprovação explícita ([[Regras de trabalho com o Claude]]).
2. **Modelo de dados isolado**: criar migração Alembic sequencial, incluir `user_id` em toda tabela operacional, evitar colisões com nomes já usados pelo Meu Orçamento (`projects`, `/api/projects`) e usar `Uuid` com `uuid.UUID(...)` e somas `Decimal(..., Decimal("0.00"))`.
3. **Governança e pontes nativas**: cadastrar a solução em `HUB_SOLUTIONS` e no `/admin`, proteger rotas com `require_solution` / `require_feature` + `assert_storage_quota` e conectar as pontes entre soluções sem salto direto de rota.
4. **Interface com a alma do Meu Orçamento**: construir dentro de `SolutionShell` + `SolutionGate` aplicando a receita do [[Padrão visual]] (`.greeting`, `.card.month-summary`, `.person-row` expansíveis, `.list-tools--pills`, `.cal-grid`/`.agenda__list`, `<EmptyGuide>`, `<MoneyInput>`, `<DateField>`, `<Tip>`, prévia em `.summary-box`) sem cores fixas nem tabelas burocráticas.
5. **Validação e memória**: rodar suítes backend (`pytest` + `ruff`), front (`tsc -b`, `vitest`, `vite build`), Chrome E2E com inspeção visual no Desktop Claro, Liquid Glass Escuro e Celular (390 px), e atualizar `docs/conhecimento/` no mesmo PR.
