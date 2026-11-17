---
tags: [meu-orcamento, regras, claude]
---
# Regras de trabalho com o Claude

Regras definidas pelo usuário. Valem para todas as sessões e projetos, salvo aviso em contrário.

## Antes de agir
1. **Nunca partir para a ação sem antes enviar um checklist** do que será feito e esperar a
   aprovação explícita ("Pode seguir", "Sim, prossiga"). Ver [[Modelo de checklist]].
2. **Responder a uma pergunta não é aprovação.** Se o usuário ajusta o checklist ("deixe só X"),
   mandar o checklist revisado e perguntar de novo.
3. **Não incluir nada que não foi pedido.** Ideias extras vão como sugestão no checklist, nunca
   direto no código. (Ver [[Mudanças rejeitadas pelo usuário]].)

## O que pode e o que não pode
4. **Nada que gere custo.** Sem plano pago (APIs pagas, serviços de terceiros). Exceção: a conta
   Oracle pode ser **Pay As You Go**, desde que tudo fique dentro do **Always Free** — liberado
   pelo usuário para facilitar a criação da VM A1 (2026-11-14).
5. **Sem IA dentro do produto** (o bot "Tire sua dúvida" é por regras locais).
6. **Nada que dependa de integração externa** que não temos (banco, WhatsApp, gateways de
   pagamento). Só o que roda dentro do site.
7. **Manter a estética atual.** Novas telas usam os componentes e classes existentes
   (ver [[Padrão visual]]). "Tudo precisa funcionar da exata mesma maneira."

## Como entregar
8. **Atualizações agrupadas** numa versão. **Hotfix** (ex.: 1.8.0.1) só para problema que
   trava o uso ou correção pedida pelo usuário logo depois de uma versão.
9. **Fotos da tela antes do PR** (desktop e celular quando a tela muda).
10. **Monitorar de 10 em 10 minutos** o CI e o deploy e **avisar no celular** (notificação)
    quando a versão estiver publicada, com a hora real.
11. **Corrigir o horário de publicação** nas notas da versão quando a hora real diferir da
    estimada (na própria versão, se der, ou na seguinte).

## Comunicação
12. Sempre em **português do Brasil**, linguagem simples, sem jargão.
13. Ser honesto sobre o que não funciona ou não foi testado; não "alucinar" capacidades.
14. Mensagens curtas de status durante tarefas longas.
