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
- [x] Compra no cartão de crédito diminuir o limite: correção do PR #75 publicada junto da
      1.10.0 em 17/11/2026; o hotfix separado v1.9.0.2 não foi necessário.
- [ ] Site não abre no Safari (iPhone): coletar aparelho, versão do iOS e o que aparece.
- [ ] Servidor antigo: mantê-lo parado e, depois de alguns dias sem problemas, apagá-lo (é o
      único item que pode gerar cobrança).
- [ ] App Android: gerar o APK com o endereço novo (Actions › Android).
- [ ] Avisar os usuários do endereço novo (entrar de novo, reativar notificações, reinstalar o app).
- [ ] Na sessão do Claude que roda no servidor: regra de nunca reiniciar/parar nada sem aprovação.

## Em andamento — Hub de Soluções (branch `exp/hub-solucoes`)
Várias soluções numa conta só, cada uma com número de versão e notas próprios (2026-11-20).
- [x] Hub de Soluções após o login, com transição entre as soluções (2026-11-19).
- [x] Mensageria: WhatsApp de verdade por QR Code (2026-11-19/20).
- [x] Dashboard & CRM: painéis, funil, contatos, leitor de PDF/CSV e conectores de API (2026-11-20).
- [x] Correções da revisão de 20/11 (checklist aprovado em 20/11/2026): backend, frontend,
      conector e cinco auditorias de interface validados localmente, com reexecução dos
      fluxos cujos seletores foram atualizados; ver [[Testes e auditorias]].
- [ ] Escanear o QR com um celular de verdade (ver [[Pendências]]).
- [ ] PR e publicação: Hub 1.0.0, Mensageria 1.0.0, Dashboard & CRM 1.0.0 e Meu Orçamento 1.11.0.
- [x] Reforma Tributária no Meu Orçamento com simulação em dois regimes, consulta a tabelas
      fiscais e geração de DANFSe com os motores locais da Receita (2026-11-20).

## Expansão do Hub — Governança + 6 Novas Soluções Integradas (plano aprovado em 20/11/2026)
- [x] **Fase A — Segurança, regras de uso por usuário e bloqueio de recursos no `/admin`** (2026-11-20): migração `0040`, bloqueio granular de soluções e sub-recursos (`require_solution`, `require_feature`), cota de armazenamento em MB (`assert_storage_quota`), abas de controle no `/admin` e proteção visual no Hub/`SolutionGate`.
- [x] **Fase B — Ciclo Comercial** (2026-11-20): `Catálogo, Estoque & Pedidos` (`/catalogo`, migração `0041`) + `Propostas, Contratos & Recibos em PDF` (`/propostas`, `fpdf2` local, **sem Pix**), com baixa automática de estoque, receita idempotente no Meu Orçamento, negócio ganho no CRM, envio do PDF na Mensageria e fonte `native_catalog`.
- [x] **Fase C — Execução e Tempo** (2026-11-20): `Projetos & Tarefas` (`/projetos`, Kanban, checklists, horas e rentabilidade com o Orçamento, migração `0042`) + `Agenda & Compromissos` (`/agenda`, visão 360° unificada em 5 camadas e confirmação no WhatsApp), com criação de projetos/tarefas a partir de CRM, Propostas e Mensageria.
- [x] **Revisão visual "Padrão Meu Orçamento" e atualização do Obsidian / `AGENTS.md`** (2026-11-20): adaptação integral de Catálogo, Pedidos, Propostas, Projetos e Agenda (e ajuste de `<DateField>` em Funil CRM e Mensageria) para a receita viva `.greeting`, `.card.month-summary`, `.person-row` expansíveis, `.list-tools--pills`, `.cal-grid`/`.agenda__list`, `<EmptyGuide>`, `<MoneyInput>`, `<DateField>`, `<Tip>` e `.summary-box`, validada em claro, escuro **Liquid Glass** e celular (`390 px`).
- [x] **Fase D — Memória Documental** (2026-11-21): `Cofre de Documentos & Garantias` (`/cofre`) + `Caderno & Base de Conhecimento` (`/caderno`), com migração `0044`, cota padrão de `200 MB`, OCR local de até 5 páginas, 6ª camada `"cofre"` na Agenda 360°, busca BM25 e grafo `[[...]]` + roteiro na Mensageria.

## Fase 1 — Base profissional (organização)
Deixar o projeto fácil de manter por qualquer pessoa ou IA.
- [x] `AGENTS.md` no repositório com as regras (lido por Claude, Gemini, Codex...) e esta
      pasta `docs/conhecimento/` como memória compartilhada (2026-11-17).
- [x] Skills de qualidade instaladas no PC: `security-audit`, `hunt-*` (Claude-BugHunter) e
      `hallmark` (só audit) (2026-11-20).
- [x] Auditoria de segurança, clean code e layout de todas as soluções do Hub (revisões
      20/11 e 21/11/2026, cobrindo Fases A–D e decisões D1–D4 em [[Testes e auditorias]];
      pendente apenas Postgres/ARM64 no deploy e QR real).
- [x] Retomada da revisão de 21/11: decisões D5–D7 confirmadas, D8 atualizado para as nove
      soluções, itens H1–H7 e E1 concluídos e ajustes C2/C8 preparados no código.
      A ativação em produção segue em [[Pendências]].
- [x] Frente 2 da revisão 2 (21/11/2026): teste de retentativa em `next_sequence` (R9), uso de
      `get_owned` nas consultas pontuais de Catálogo & Propostas, Projetos & Agenda e Mensageria
      (R11), e ajuste para **Hub de Soluções** nos e-mails de conta (`auth.py`).
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
- [ ] Tire sua dúvida (bot) — integração pronta, falta medição com casos reais. **Regra:** a IA pode ajudar a *escrever*
      o código; o bot não pode *chamar* IA ao responder (custo e serviço externo).
      Motor novo integrado no branch `exp/hub-solucoes` em 20/11/2026 (`app/services/bot/`),
      sem medição com casos reais ainda; sai na Meu Orçamento 1.11.0.
- [x] Leitor de cupons — feito à parte com sucesso; integrado na v1.10.0 (PR #73).
- [ ] Categorização automática — medir acerto com o histórico já categorizado.
- [ ] Importação de extrato bancário — um extrato real de cada banco como teste.
- [ ] Assinaturas e recorrências — medir acertos e alarmes falsos no histórico.

## Fase 4 — Crescimento
- [ ] Página inicial que explica o site para quem ainda não tem conta.
- [ ] Convite para amigos.
- [x] Atualizar os Termos de uso e a Política de privacidade para as soluções do Hub.
      A revisão de 20/11/2026 inclui integrações, retenção, alcance do backup e versão registrada no cadastro.

## Ritmo de versões
- Uma versão por vez: checklist → aprovação → código → testes → fotos → PR → deploy → aviso.
- Hotfix (ex.: 1.9.0.2) só para o que está quebrado.
- Ver [[Fluxo de versão e publicação]].
