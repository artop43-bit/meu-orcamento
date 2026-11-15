# v1.9.0 · Avisos por webhook — desenho

## Por quê
A pessoa quer receber os avisos do Meu Orçamento num servidor dela (Discord, Slack, automação),
escolhendo o que chega. Resolve a pendência "Notificações no Discord".

## Objetivo
Terceiro canal de avisos, ao lado do e-mail e do aparelho, em Ajustes › Preferências.

## O que entra
- Um endereço de webhook por pessoa. Aceita **qualquer endereço `https`**.
- Formato pelo endereço: `discord.com/api/webhooks/…` (e `discordapp.com`) → cartão (embed);
  `hooks.slack.com/…` → mensagem do Slack; qualquer outro → JSON completo com o texto pronto
  em `text` e `content`.
- Seis tipos, cada um com sua caixinha, **todas desligadas por padrão**: vencimentos, resumo
  do mês, resumo da semana, "Disponível hoje", mensagens da caixa, alertas de gasto.
- "Esconder valores" (já existente) vale também para o webhook.
- Endereço salvo aparece só em parte (`discord.com/…a8F2`); botão "Enviar teste"; botão "Remover".
- 5 falhas seguidas → envios pausam e chega um aviso na caixa de mensagens. Salvar o endereço
  de novo ou um teste que funciona tira a pausa.

## Segurança (obrigatório)
- Só `https`, sem usuário/senha no endereço, até 500 caracteres.
- Recusar endereços que resolvem para IP não público (loopback, rede privada, link-local —
  inclui `169.254.169.254` da Oracle —, multicast, reservado). Conferido ao salvar **e a cada envio**.
- Não seguir redirecionamentos; tempo limite de 5 s; não ler a resposta além do status.

## Não entra
- Telegram (precisa de bot e chat_id, não é webhook), assinatura HMAC, vários webhooks,
  fila de reenvio. O aviso de novo acesso continua só por e-mail.

## Restrições
- Sem custo, sem dependência nova (HTTP com `urllib` da biblioteca padrão, como `indicators.py`).
- Estética atual: um cartão `card stack` igual a "Avisos por e-mail".

## Abordagens consideradas
- **Só Discord**: mais simples e seguro, mas limita a pessoa. Descartada pelo usuário.
- **Universal com formato pelo endereço** (escolhida): Discord e Slack bonitos, o resto recebe os
  dados; exige a proteção de rede acima.
- **Universal só JSON**: Discord recusaria (precisa de `content`/`embeds` no formato dele).

## Decisões minhas (o usuário pode mudar)
- Dados guardados na tabela `users` (`webhook_url`, `webhook_kinds` em JSON, `webhook_failures`).
- O envio entra pelo `push.send` (todos os avisos já passam por lá, menos o resumo do mês,
  que ganha a chamada no `run_daily`).
