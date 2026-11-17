---
tags: [meu-orcamento, processo]
---
# Como trabalhamos

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
