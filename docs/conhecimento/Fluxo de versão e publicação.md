---
tags: [meu-orcamento, processo, deploy]
---
# Fluxo de versão e publicação

## Numeração
- `1.8.0` — versão com funcionalidades agrupadas.
- `1.8.0.1`, `1.8.0.2` — hotfix (4º número).
- Uma versão por PR. Branch de trabalho do Claude: `claude/<nome>`; reiniciar a partir da
  `main` a cada versão nova.

## Arquivos que mudam em toda versão
| Arquivo | O quê |
|---|---|
| `changelog/AAAA-MM-DD_vX.Y.Z.txt` | Registro detalhado (modelo abaixo) |
| `frontend/src/release.ts` | `RELEASE.version`, `releasedAt` (ISO com -03:00) e `RELEASE_NOTES` (2–3 itens curtos para o aviso "Novidades") |
| `frontend/src/lib/releases.ts` | Histórico de Ajustes › Notas da versão (a versão nova no topo) |

Modelo do changelog:
```
MEU ORÇAMENTO · UPDATE LOG
Versão 1.8.0.1 · <título> (hotfix)
Data: 14/11/2026 às 17:02 (horário de Brasília)

<Área>
- [x] item em linguagem do usuário

Correções
- [x] ...

Testes
- [x] ...
```

## Onde trabalhar
- Trabalhar na cópia local do repositório no PC → enviar ao GitHub → publicar no
  servidor Oracle, nessa ordem; antes de começar, `git pull` na `main` — o código local é a
  primeira parada, as sessões na nuvem deixaram de ser o padrão (2026-11-14)

## Sequência
1. Checklist aprovado → código → testes locais (backend, frontend, e2e).
2. Fotos para o usuário.
3. Estimar o horário de publicação (≈ 27 min CI do PR + 27 min CI da `main` + 2 min deploy)
   e colocar esse horário nos 3 arquivos **antes** de abrir o PR (mudar depois reinicia o CI).
4. PR → CI verde → merge → CI da `main` → workflow **Deploy** (automático após CI verde na `main`).
5. Monitorar de 10 em 10 min; ao terminar o Deploy, avisar no celular com a hora real.
6. Se a hora real diferir da estimada, corrigir nas notas da próxima versão.

## Deploy
- Workflow `Deploy` roda após o CI da `main` passar: entra por SSH na VM e executa `deploy`,
  depois confere `https://<domínio>/api/health/db`.
- Detalhes do servidor e de acesso ficam fora do repositório (público), nas notas pessoais do Arthur.
