# Testando no GitHub Codespaces

O Codespace é um computador na nuvem, ligado à sua conta do GitHub, que roda o app
inteiro no navegador. O endereço é **privado**: só abre com você logado no GitHub.

## Abrir

1. No GitHub, abra o repositório e escolha a branch (botão com o nome da branch).
2. **Code → aba Codespaces → Create codespace on …**
3. Espere a instalação (3–5 min na primeira vez; depois liga em segundos).
4. O site abre sozinho numa aba nova. Se não abrir: aba **PORTS** (Portas), linha
   "Meu Orçamento" (5173), clique no ícone de globo.

## Entrar

A conta de demonstração já vem **confirmada** e **preenchida** com 6 meses de exemplo (fixas,
parcelas, metas, investimentos, limites e uma análise fixada). O que você lançar fica guardado. O e-mail
e a senha aparecem no terminal quando o Codespace liga. Para ver de novo, no terminal:

```bash
cat .devcontainer/credenciais.txt
```

A senha é **nova a cada vez que o Codespace liga** e não fica salva no repositório.

Também dá para criar outras contas pela tela de cadastro. O e-mail de confirmação não é
enviado de verdade: o link aparece no log da API:

```bash
grep -o 'http[^ ]*verificar-email[^ ]*' /tmp/api.log | tail -1
```

## Útil

| O quê | Comando |
|---|---|
| Ver logs da API | `tail -f /tmp/api.log` |
| Ver logs do site | `tail -f /tmp/web.log` |
| Reiniciar tudo | `bash .devcontainer/start.sh` |
| Apagar os dados e recomeçar | `rm backend/codespace.db && bash .devcontainer/start.sh` |
| Rodar os testes | `cd backend && uv run pytest` e `cd frontend && npm test` |

## Custo

Contas pessoais do GitHub têm **120 horas grátis por mês** (em máquina de 2 núcleos).
O Codespace **desliga sozinho após 30 minutos parado**. Para não gastar à toa, desligue
em github.com/codespaces → **⋯ → Stop codespace** quando terminar.

Para refazer a conta de demonstração do zero:

```bash
rm .devcontainer/.demo-v050 && bash .devcontainer/start.sh
```
