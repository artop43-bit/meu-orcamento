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
   - Exceção: a Mensageria conecta ao WhatsApp por QR Code (Baileys, conexão não oficial e sem
     custo) — pedido do Arthur, só para essa solução (2026-11-19).
   - Exceção: os conectores de API REST/JSON do Dashboard & CRM podem chamar APIs de terceiros
     (só https, sem custo) — decisão do Arthur na revisão do branch `exp/hub-solucoes` (2026-11-20).
7. **Manter a estética atual e a originalidade do Meu Orçamento.** Novas soluções e telas do Hub usam os componentes e a receita viva de interface do Meu Orçamento (ver [[Padrão visual]]), sem visual genérico de ERP ou tabelas frias, validados em desktop, celular (390 px) e **Liquid glass** escuro/claro (2026-11-20). "Tudo precisa funcionar da exata mesma maneira."

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

## Qualidade e segurança
15. **Clean code**: código organizado, com nomes claros, funções curtas e um assunto por arquivo,
    fácil de achar e de entender para ajustes e manutenção manuais — pedido do Arthur (2026-11-20).
16. **Auditoria de segurança antes do PR** de solução nova ou de mudança com upload, login,
    conector externo ou dados de outra conta: skill `security-audit` (Cloudflare). Achado
    confirmado é corrigido antes do PR — pedido do Arthur (2026-11-20).
17. **Testes de ataque (skills `hunt-*` do Claude-BugHunter + `triage-validation`) só contra o site
    rodando no PC**, nunca contra o servidor e nunca sem aprovação (2026-11-20).
18. **Skill `hallmark` só em modo `audit`** (relatório) como conferência extra de estética; nunca
    `redesign` nem temas — vale o visual do Meu Orçamento (regra 7) (2026-11-20).
19. As skills ficam instaladas no PC (`~/.claude/skills`), fora do repositório público (2026-11-20).
