# Meu Orçamento

Plataforma de finanças pessoais multiusuário: orçamento mensal, contas e parcelas,
metas, análises e investimentos.

## Estrutura

```
meu-orcamento/
├── backend/                 API em Python (FastAPI + SQLAlchemy + Alembic)
├── frontend/                Aplicação web (React + Vite + TypeScript)
├── deploy/                  Produção: Caddy, backup e scripts do servidor
├── docs/DEPLOY.md           Guia de deploy na Oracle Cloud
├── docker-compose.yml       Ambiente de desenvolvimento (Postgres + API + Web)
├── docker-compose.prod.yml  Produção
└── .github/                 CI, deploy automático e Dependabot
```

## Testes

| O quê | Comando |
|---|---|
| Backend (SQLite, rápido) | `cd backend && uv run pytest` |
| Backend no PostgreSQL | `TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost/banco_vazio uv run pytest` |
| Frontend | `cd frontend && npm test` |
| Produção completa (Docker, Linux/WSL) | `bash deploy/scripts/smoke-test.sh` |

O CI roda tudo isso a cada PR, incluindo a build das imagens para ARM (VM da Oracle).

## Rodando em desenvolvimento

Pré-requisitos: Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:5173
- API: http://localhost:8000/api/health
- Documentação da API: http://localhost:8000/docs

### Sem Docker (opcional)

Backend (requer Python 3.12+ e [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

Frontend (requer Node.js 22+):

```bash
cd frontend
npm install
npm run dev
```

### E-mails em desenvolvimento

Com `EMAIL_BACKEND=console`, os e-mails (confirmação de cadastro, redefinição de senha)
são impressos no log da API em vez de enviados. Para ver os links:

```bash
docker compose logs -f backend
```

## Autenticação

- Sessão em cookie `httpOnly` (`SameSite=Lax`, `Secure` em produção), guardada no banco
  como hash e revogável (logout, troca/redefinição de senha).
- Senhas com Argon2; mínimo de 10 caracteres.
- Proteção CSRF: toda requisição que altera dados precisa do cabeçalho `X-Requested-With: fetch`.
- Bloqueio de 15 min após 5 tentativas erradas (senha ou código 2FA).
- Links de e-mail de uso único com validade (24 h para confirmação, 1 h para redefinição).
- 2FA por TOTP com segredo criptografado no banco, proteção contra reuso de código
  e 10 códigos de recuperação.
- Cadastro e "esqueci a senha" não revelam se um e-mail está cadastrado.

> A `SECRET_KEY` também deriva a chave que criptografa os segredos de 2FA.
> Trocá-la invalida o 2FA de todos os usuários.

## Migrações do banco

```bash
docker compose exec backend alembic revision --autogenerate -m "descricao"
docker compose exec backend alembic upgrade head
```

## Roadmap

1. Base do projeto ✅
2. Contas de usuário (cadastro, login, 2FA, recuperação de senha) ✅
3. Núcleo do orçamento (renda, contas, parcelas, categorias, metas, histórico) ✅
4. Análises (score, 50/30/20, comparar meses, projeção, simulador, investimentos) ✅
5. Importação/exportação (JSON do app antigo, extratos, CSV/Excel/PDF) ✅
6. Deploy na Oracle Cloud (Docker, Caddy/HTTPS, backups) 🛠️ preparado, aguardando a VM: veja [docs/DEPLOY.md](docs/DEPLOY.md)
7. Produto público (LGPD, termos, rate limiting, e-mails) ✅ (falta preencher `frontend/src/legal.ts`)

