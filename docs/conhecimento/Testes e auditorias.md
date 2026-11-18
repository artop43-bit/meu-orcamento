---
tags: [meu-orcamento, testes]
---
# Testes e auditorias

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

Execução dos e2e: `uv run --no-project --with playwright python e2e/<teste>.py`, com
`QA_CREDENTIALS` e `QA_OUT` definidos e o app rodando (build do front + API + conta de
demonstração `seed-demo --vazia`).

Regras:
- Toda funcionalidade nova ganha teste de backend **e** um passo no e2e persona.
- Não rodar o pytest ao mesmo tempo que os e2e (falhas falsas).
- Nunca pular/desligar teste para ficar verde.
