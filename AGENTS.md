# AGENTS.md — Meu Orçamento

Instruções para qualquer agente de IA que trabalhe neste repositório (Claude, Gemini, Codex,
Copilot...). Plataforma de finanças pessoais multiusuário: FastAPI + React, servidor ARM64.

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
  APIs pagas). **Sem IA dentro do produto.**
- **Manter a estética atual**: componentes e classes existentes, cores só por tokens.
- **Nunca reiniciar, parar ou atualizar o servidor** sem aprovação.
- **Nunca pular ou desligar teste** para ficar verde. Toda funcionalidade nova ganha teste.
- Sempre em **português do Brasil**, linguagem simples; ser honesto sobre o que não foi testado.
- Versões: changelog + `frontend/src/release.ts` + `frontend/src/lib/releases.ts`; uma versão
  por PR; hotfix só para o que trava o uso.

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
