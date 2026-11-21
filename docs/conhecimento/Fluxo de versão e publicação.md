---
tags: [meu-orcamento, processo, deploy]
---
# Fluxo de versão e publicação

## Numeração
- `1.8.0` — versão com funcionalidades agrupadas.
- `1.8.0.1`, `1.8.0.2` — hotfix (4º número).
- Uma versão por PR. Branch de trabalho do Claude: `claude/<nome>`; reiniciar a partir da
  `main` a cada versão nova.
- Notas da versão separadas por solução (Hub, Meu Orçamento, Mensageria, Dashboard & CRM): o que
  é de uma solução não entra nas notas de outra, e uma versão já publicada não ganha itens
  novos — decisão do Arthur (2026-11-20).
- Cada solução tem a própria numeração de versão (o Meu Orçamento segue a sua; Hub, Mensageria e
  Dashboard & CRM começam em 1.0.0) — decisão do Arthur (2026-11-20).

## Arquivos que mudam em toda versão
| Arquivo | O quê |
|---|---|
| `changelog/AAAA-MM-DD_<solucao>_vX.Y.Z.txt` | Um registro detalhado por solução e versão (modelo abaixo); preservar arquivos publicados |
| `frontend/src/release.ts` | `SOLUTION_RELEASES[solucao]`: `version`, `releasedAt` (ISO com -03:00; `null` em preparação) e `notes` para o aviso "Novidades" |
| `frontend/src/lib/releases.ts` | Histórico de Ajustes › Notas da versão (a versão nova no topo) |

- Versões em preparação ficam sem data no histórico e mostram "Em preparação"; rodapé,
  Novidades e relatórios de erro usam a solução atual — evita atribuir uma publicação
  inexistente ou a versão de outra solução (2026-11-20).

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

## Branch de teste do Hub
- `exp/hub-solucoes` é o teste do futuro update do Hub: commits e push **só nesse branch**,
  **sem merge na `main`** até o Arthur liberar (2026-11-21).

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
