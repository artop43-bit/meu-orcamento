---
tags: [meu-orcamento, arquitetura]
---
# Stack e arquitetura

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
- Estado de servidor com TanStack Query (`queryKey`), invalidar após mutações.
- Download de arquivos pela função `download(path, nome, body?)` (POST quando há body).

## Produção (docker-compose.prod.yml)
`db` (Postgres 17), `api`, `scheduler` (rotinas diárias), `backup` (cópias cifradas com age),
`caddy` (HTTPS + site). Imagens montadas para **ARM64** (VM Oracle).

## Conceitos do domínio
- **Mês do orçamento** com dia de início configurável (`month_start_day`).
- Receitas (`incomes`) e despesas (`expenses`) por mês; parcelas, recorrências, cartões,
  contas, metas, investimentos, projetos.
- Itens gerados por outra função carregam a origem (`loan_id`, `personal_loan_id`,
  `recurring_id`) e são **refeitos** por uma função `sync` em vez de editados à mão.

## Leitura de comprovante
- Leitura de foto pelo leitor de cupons próprio (`leitor_comprovantes`, repo `artop43-bit/Leitor-de-cupons`, RapidOCR local) no lugar do Tesseract; dependência fixada por commit no `pyproject.toml`; as regras de texto do `ocr.py` ficam como reserva campo a campo e o boleto continua nelas — leitor mais completo (itens, conferência da soma) e sem serviço externo (2026-11-17)
