---
tags: [meu-orcamento, plano]
---
# Plano do projeto

Objetivo: um site **profissional, fácil de usar e que as pessoas queiram usar**, sem custo e
sem depender de serviços de terceiros. Seguimos em fases; só passamos para a próxima quando a
anterior está fechada. Cada item vira um checklist aprovado antes de começar
([[Regras de trabalho com o Claude]]).

## Fase 0 — Estabilizar (agora)
Corrigir o que está quebrado ou pendente da mudança de servidor.
- [ ] Hotfix v1.9.0.2: compra no cartão de crédito diminuir o limite (checklist já aprovado,
      aguardando "Pode seguir").
- [ ] Site não abre no Safari (iPhone): coletar aparelho, versão do iOS e o que aparece.
- [ ] Servidor antigo: mantê-lo parado e, depois de alguns dias sem problemas, apagá-lo (é o
      único item que pode gerar cobrança).
- [ ] App Android: gerar o APK com o endereço novo (Actions › Android).
- [ ] Avisar os usuários do endereço novo (entrar de novo, reativar notificações, reinstalar o app).
- [ ] Na sessão do Claude que roda no servidor: regra de nunca reiniciar/parar nada sem aprovação.

## Fase 1 — Base profissional (organização)
Deixar o projeto fácil de manter por qualquer pessoa ou IA.
- [x] `AGENTS.md` no repositório com as regras (lido por Claude, Gemini, Codex...) e esta
      pasta `docs/conhecimento/` como memória compartilhada (2026-11-17).
- [ ] Pasta `laboratorio/` no repositório para peças desenvolvidas à parte (ver
      [[Como trabalhamos]]).
- [ ] Testar a **restauração** de um backup (backup que nunca foi restaurado não é garantia).
- [ ] Endereço definitivo: hoje depende do IP do servidor. Opções: reservar o IP na Oracle
      (conferir se é grátis) ou domínio próprio (.com.br ≈ R$ 40/ano — **tem custo, decisão do
      usuário**).

## Fase 2 — Usabilidade (o que faz as pessoas quererem usar)
- [ ] Ouvir os usuários: 3 perguntas curtas (o que mais usam, o que confunde, o que falta).
- [ ] Primeiro uso: alguém novo consegue lançar a primeira despesa e entender o mês em
      menos de 2 minutos?
- [ ] Celular em primeiro lugar: revisar as telas mais usadas no celular.
- [ ] Velocidade: telas principais abrindo em menos de 1 segundo.
- [ ] Textos e ajuda: cada tela explica em uma frase para que serve.

## Fase 3 — Peças "inteligentes" (só quando houver reclamação ou medida ruim)
Desenvolvidas à parte, com casos reais e porcentagem de acerto, depois trazidas para o sistema.
- [ ] Tire sua dúvida (bot) — em andamento à parte. **Regra:** a IA pode ajudar a *escrever*
      o código; o bot não pode *chamar* IA ao responder (custo e serviço externo).
- [ ] Leitor de cupons — feito à parte com sucesso; integração na v1.10.0 (PR #73).
- [ ] Categorização automática — medir acerto com o histórico já categorizado.
- [ ] Importação de extrato bancário — um extrato real de cada banco como teste.
- [ ] Assinaturas e recorrências — medir acertos e alarmes falsos no histórico.

## Fase 4 — Crescimento
- [ ] Página inicial que explica o site para quem ainda não tem conta.
- [ ] Convite para amigos.
- [ ] Revisar termos e privacidade (LGPD) para quem é de fora do círculo de amigos.

## Ritmo de versões
- Uma versão por vez: checklist → aprovação → código → testes → fotos → PR → deploy → aviso.
- Hotfix (ex.: 1.9.0.2) só para o que está quebrado.
- Ver [[Fluxo de versão e publicação]].
