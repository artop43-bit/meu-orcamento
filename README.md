# Meu Orçamento

Plataforma de finanças pessoais multiusuário: orçamento mensal, contas e parcelas,
metas, análises e investimentos.

## Estrutura

```
meu-orcamento/
├── backend/            API em Python (FastAPI + SQLAlchemy + Alembic)
├── frontend/           Aplicação web (React + Vite + TypeScript)
├── docker-compose.yml  Ambiente de desenvolvimento (Postgres + API + Web)
└── .github/workflows/  Integração contínua (testes e build)
```

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

## Migrações do banco

```bash
docker compose exec backend alembic revision --autogenerate -m "descricao"
docker compose exec backend alembic upgrade head
```

## Roadmap

1. Base do projeto ✅
2. Contas de usuário (cadastro, login, 2FA, recuperação de senha)
3. Núcleo do orçamento (renda, contas, parcelas, categorias, metas, histórico)
4. Análises (score, 50/30/20, comparar meses, projeção, simulador, investimentos)
5. Importação/exportação (JSON do app antigo, extratos, CSV/Excel/PDF)
6. Deploy na Oracle Cloud (Docker, Caddy/HTTPS, backups)
7. Produto público (LGPD, termos, rate limiting, e-mails)
