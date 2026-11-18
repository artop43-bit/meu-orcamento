---
tags: [meu-orcamento, pendencias]
---
# Pendências (em 17/11/2026)

- [x] Limite do cartão — compra nunca entra paga e sempre ocupa o limite (PR #75, publicado junto da 1.10.0 em 17/11 21:20).
- [ ] Safari (iPhone) — falta aparelho, versão do iOS e o que aparece.
- [ ] Servidor antigo — mantê-lo parado; apagar depois de alguns dias sem problemas.
- [ ] APK novo do Android (Actions › Android).
- [ ] Avisar usuários do endereço novo.
- [ ] Regra "nunca reiniciar sem aprovação" na sessão do Claude do servidor.
- [ ] Decidir: reservar IP na Oracle ou domínio próprio (custo).
- [ ] Bot (Tire sua dúvida) à parte — confirmar que a IA só escreve o código, não roda no bot.

## Recolocadas da lista anterior (17/11/2026)
- [x] **Horário da v1.9.0.1**: corrigido para 16/11 00:44 nas notas da 1.10.0.
- [ ] **Notas da 1.10.0**: dizem 21:45, a publicação real foi 17/11 às 21:20; e falta a linha
      da correção do limite do cartão (PR #75 foi publicado junto). Corrigir na próxima versão.
- [ ] **Leitor de cupons (v1.10.0)**: medir o tempo de leitura no servidor depois do deploy.
- [ ] **Webhook, pontos menores da revisão**: DNS rebinding, faixas NAT64, menções (`@channel`),
      limite no "Enviar teste", testes de redirecionamento/HTTPError.
- [ ] **Skills rtk e graphify**: instaladas no PC local; para sessões na nuvem, colocar no
      repositório (`.claude/skills/`) ou no script de preparação do ambiente.

## Da revisão do PR 73 (leitor de cupons, 17/11/2026)
- [ ] **Sem limite de tempo na leitura**: o leitor roda dentro do processo da API e não dá para
      interromper; uma foto difícil segura a fila. Medir uma foto real de celular no servidor e,
      se demorar, levar a leitura para um processo separado com prazo.
- [ ] **Memória fixa maior**: os modelos ficam carregados no processo da API (algumas centenas
      de MB). Conferir o uso de RAM no servidor depois do deploy.
- [ ] **Duas versões do OpenCV instaladas** (`opencv-python` e `opencv-python-headless`, a
      primeira vem do RapidOCR): escrevem na mesma pasta `cv2/`. Funciona hoje; resolver no
      repositório do leitor usando só uma.
