---
tags: [meu-orcamento, pendencias]
---
# Pendências (em 17/11/2026)

## Termos de uso e Política de privacidade do Hub (20/11/2026)
- [x] Revisar os dois textos, alinhar a versão do cadastro e registrar a atualização nas notas do Hub.

## Reforma Tributária no Meu Orçamento (20/11/2026)
- [x] Integrar as duas calculadoras, as tabelas e o gerador de DANFSe na seção Análises.
- [ ] Publicar com o Meu Orçamento após o checklist da versão.

- [x] Limite do cartão — compra nunca entra paga e sempre ocupa o limite (PR #75, publicado junto da 1.10.0 em 17/11 21:20).
- [ ] Safari (iPhone) — falta aparelho, versão do iOS e o que aparece.
- [ ] Servidor antigo — mantê-lo parado; apagar depois de alguns dias sem problemas.
- [ ] APK novo do Android (Actions › Android).
- [ ] Avisar usuários do endereço novo.
- [ ] Regra "nunca reiniciar sem aprovação" na sessão do Claude do servidor.
- [ ] Decidir: reservar IP na Oracle ou domínio próprio (custo).
- [x] Bot (Tire sua dúvida) à parte — integrado no `hub` (`app/services/bot/`) em 20/11/2026, 100% local por regras determinísticas (zero IA em produção).

## Recolocadas da lista anterior (17/11/2026)
- [x] **Horário da v1.9.0.1**: corrigido para 16/11 00:44 nas notas da 1.10.0.
- [x] **Notas da 1.10.0**: horário corrigido para 17/11 às 21:20 e incluída a correção do limite
      do cartão (PR #75); ajuste preparado no branch do Hub em 20/11, ainda sem publicação.
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

## Mensageria com WhatsApp, Dashboard & CRM e transições do Hub (20/11/2026, branch `exp/hub-solucoes`)
- [x] Decisão: o Dashboard & CRM, o bot novo e o CRM 360°/Lançar da Mensageria ficam no produto — confirmado pelo Arthur na revisão (2026-11-20).
- [x] Correções do checklist aprovado de 20/11 concluídas e validadas localmente: dinheiro,
      conversas, OCR, conector de API, CRM, bot, versões por solução e acabamento; resultados
      e reexecuções dos e2e em [[Testes e auditorias]]. PR e publicação continuam fora desta etapa.
- [ ] **Escanear o QR com um celular de verdade** e conferir: conexão abre, histórico chega com nomes corretos (sem duplicatas LID/número nem nomes mascarados), fotos de perfil carregam, recebimento e envio de foto/áudio/vídeo/documento funcionam, ✓✓/leitura sincronizam e reconexão funciona depois de reiniciar o conector.
- [ ] **Testar Dashboard & CRM em Postgres 17 e no servidor ARM64**: validar migrações `0036` a `0039` no Postgres real, medir tempo de OCR local em PDFs escaneados reais no servidor e testar limpeza semanal (`python -m app.cli cleanup`).
- [ ] **Etapa extra de passkey**: algumas contas não conseguem concluir o pareamento pela Baileys
      (issue #2672 da biblioteca, sem correção). Se acontecer com o número do Arthur, avaliar
      trocar o conector para whatsmeow (Go) numa etapa à parte.
- [ ] **Publicar**: criar `MESSAGING_CONNECTOR_TOKEN` no `.env.production` do servidor antes do
      deploy (sem ela a Mensageria só avisa "conexão indisponível"). Medir a memória real por
      número conectado no servidor.
- [x] **Versões preparadas**: Hub 1.0.0, Mensageria 1.0.0, Dashboard & CRM 1.0.0 e Meu Orçamento
      1.11.0, com changelog e Novidades próprios. Datas ficam em preparação até o checklist do PR.
- [ ] Sugestões que ficaram de fora: desempate da ordem de mensagens do mesmo segundo pela ordem
      de chegada; número do DDD 55 (RS) digitado sem o DDI vira inválido na "Nova conversa".

## Decisões do Arthur na Revisão 2 (21/11/2026)
- [x] Fase D (Cofre & Garantias e Caderno) foi pedida e fica — confirmado pelo Arthur (2026-11-21).
- [x] Reforma Tributária (`rtc`, ~1,4 GB de RAM) só vai para a produção junto com o update do Hub (2026-11-21).
- [x] D2 (caixas marcadas antes de confirmar pedido/aprovar proposta), D3 (etiqueta exclusiva de projeto) e D9 (excluir com desfazer) confirmados pelo Arthur (2026-11-21).
- [x] D4 — cota: arquivos permanentes (comprovantes, anexos, Cofre e CRM) com 100 MB por conta, que o admin pode aumentar; mídias da Mensageria fora da cota, com teto de 300 MB que apaga as mais antigas; backup remoto com 7 diárias + 4 semanais e sem as mídias temporárias — recomendação do Claude aprovada pelo Arthur (2026-11-21).
- [ ] Conferir no painel da Oracle o limite gratuito do Object Storage e criar alarme de orçamento (Budgets) antes do deploy do Hub.
- [ ] D8 — Termos e Privacidade: o Arthur vai ler e pediu revisão do Claude antes de publicar (2026-11-21).

## Revisão geral 21/11/2026 — Checklist de correções, decisões D1–D4 e Fase D
- [x] Seções **A**, **B1–B8**, **C1–C7**, **D9**, **E1–E6**, **F1–F6** e correções de layout mobile/Reforma Tributária implementadas e validadas localmente (testes backend/frontend/WhatsApp, suítes Playwright completas no Chrome e checagens de segurança locais em instância temporária isolada).
- [x] **Decisões resolvidas e aplicadas (D1–D4, 2026-11-21)**:
  - **D1 (`rtc` opcional no dev / obrigatório no CI e produção)**: `integrations/rtc/compose.yml` recebeu `profiles: ["rtc"]`, os scripts `compose.sh`, `smoke-test.sh` e `ci.yml` usam `--profile rtc`, e `e2e/rtc.py` roda no CI após `persona.py` com `--with pyotp`.
  - **D2 (confirmação explícita em Pedido e Proposta)**: confirmar pedido no Catálogo e aprovar proposta abrem janela com caixas de sincronização para Meu Orçamento e CRM (marcadas por padrão e editáveis antes de gravar).
  - **D3 (etiqueta exclusiva em Projetos & Tarefas)**: se o nome do projeto já existir nas etiquetas do Meu Orçamento, cria uma etiqueta exclusiva para não misturar despesas antigas, permitindo vincular uma existente no modal de criação.
  - **D4 (cota padrão de 200 MB + Cofre na contagem)**: `DEFAULT_STORAGE_QUOTA_MB = 200`, migração `0044` atualizando contas que estavam em `50 MB` e soma de `VaultDocument.size_bytes` no uso por usuário.
- [x] **Fase D (`/cofre` e `/caderno`)**: migração `0044`, APIs/serviços locais, UI no Padrão Meu Orçamento, 6ª camada `"cofre"` na Agenda 360°, preservação na limpeza de 7 dias da Mensageria, roteiro na conversa e cobertura de testes + E2E + auditorias visuais/segurança validados localmente.
- [x] **D5–D7**: Arthur confirmou manter os bloqueios globais e por conta, com administradores isentos,
  a confirmação de compromissos e o envio de PDFs pelo WhatsApp, e os modelos atuais de Contrato e Recibo (2026-11-21).
- [x] **D8**: Termos de uso e Política de privacidade atualizados para incluir Cofre e Caderno.
  A revisão `2026-11-21` é exibida e registrada em novos cadastros.
- [x] **C2 e C8 preparados no repositório**: teto de 20 MB no Caddy e acesso dedicado do conector
  ao PostgreSQL, com permissão sobre suas credenciais de sessão e a chave `wa_version`.
- [x] **H1–H7 e E1**: nomes e valores melhor enquadrados, textos no singular e plural,
  navegação e cores da Agenda, edição e exclusão nos cartões de Projetos, e teste das
  notas da versão conferindo as soluções do catálogo do Hub.
- [ ] **C2 e C8 em produção**: aplicar a configuração do Caddy e provisionar e ativar o papel
  dedicado do conector na janela de deploy aprovada.
