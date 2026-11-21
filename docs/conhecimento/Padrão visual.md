---
tags: [meu-orcamento, design]
---
# Padrão visual

## Proposta e alma do produto (Padrão "Meu Orçamento")
O sistema não pode parecer um ERP pesado, uma planilha fria ou um painel genérico de botões e tabelas.
Mesmo no Hub com várias soluções, **toda tela precisa manter o toque original do Meu Orçamento**:
linguagem humana, resumo imediato do que importa agora, pílulas com contagem, listas que abrem e fecham
suavemente, prévia ao vivo antes de salvar e respeito total ao **Padrão** e ao **Liquid Glass** (claro/escuro).

## Tema
- Cores como **tokens** (`--accent`, `--surface`, `--border`, `--muted`, `--error`...) em
  `theme.css`, com claro/escuro.
- `visual.css` é a camada de forma: **sem cores fixas (hex)**, só tokens.
- Nunca aplicar `style={{ background: "var(--surface-2)" }}` em cartões estruturais no lugar de
  `.card`, `.person-row` ou `.agenda__list`: isso quebra a translucidez e a profundidade do **Liquid glass**.
- Dois estilos: **Padrão** e **Liquid glass** (`data-style`), 10 cores de destaque.

## Componentes e classes a reaproveitar
`card`, `greeting`, `card month-summary` (`.month-summary__main` / `__side` / `__bar`), `kpis`/`Kpi`,
`chips` + `chip-btn[aria-pressed]`, `segmented` (rádios), `items`/`item`, `btn btn--primary|secondary`,
`bar`/`bar__fill`, `list-tools list-tools--pills` + `list-tools__search` + `pill-group`,
`person-rows` / `person-row` (linhas expansíveis), `details`, `stats`/`stat`, `summary-box`, `badge`,
`Alert` (`alert--info|error|success`), `inline-form`, `grid-2`, `form-actions`, `Sheet` (janela/modal
que vira bottom sheet no celular), `PageHeader`, `EmptyGuide`, `Tip`, `MoneyInput`, `DateField`,
`ChargeMessage` (`.charge__text`), `crm-kanban` / `crm-deal-card`, `cal-summary`, `card reminder`,
`cal-grid` / `cal-day` / `ev` / `legend`, `agenda` / `agenda__day` / `agenda__list`.

## Receita de tela por padrão de uso (evitar telas massantes)
- **Abertura de tela**: começar com `.greeting` conversacional ("Hoje, dia X… Você tem Y em andamento…")
  seguida de um `.card.month-summary` protagonista (valor/métrica principal + `<Bar />` ou `.month-summary__bar`
  + `.stats`), em vez de abrir sempre com 4 caixas `<Kpi>` idênticas e frias.
- **Listas do dia a dia** (Catálogo, Pedidos, Propostas, Contatos, Divisões): usar **`.person-rows` /
  `.card.person-row` expansíveis** (avatar/ícone + título/subtítulo + barra de saúde/margem + destaque numérico
  + corpo com `<details className="details">` e `<ul className="items">`), acompanhadas de
  `.list-tools.list-tools--pills` (busca + filtros `.chip-btn` com contagem + `"Abrir todos"`).
  **Evitar `<table className="table">` genérica** nessas listas.
- **Quadros de execução e funil** (Projetos & Tarefas, Pipeline CRM): `.crm-kanban` / `.crm-kanban__col` /
  `.crm-deal-card` com barra de checklist (`<Bar />`), pílulas de prioridade e botões rápidos de avanço em 1 toque.
- **Calendários e agendas** (Agenda & Compromissos, Calendário do Orçamento): `.cal-summary` + `.card.reminder`
  ("Hoje e próximos 7 dias") + `.cal-grid` (`.ev` com cor, ícone e `<ul className="legend">`) no desktop
  e `.agenda` / `.agenda__day.is-today` / `.agenda__list > li` nas visões em lista e no celular.
- **Formulários com prévia ao vivo**: usar `<MoneyInput>`, `<DateField>`, `.segmented`/`.chips`, `<Tip>`
  e uma caixa `.summary-box` mostrando em tempo real margem, valor/hora ou resumo do documento antes de salvar.
- **Estado vazio acolhedor**: sempre usar `<EmptyGuide>` com explicação simples em português e exemplo concreto.
- **Celular (`390 px`)**: sem rolagem lateral fora de trilhos intencionais, botões fáceis no polegar, leitura limpa.

## Acessibilidade
- Todo campo com rótulo; para `textarea` com texto longo, usar `<label htmlFor>` separado
  (ver [[Erros comuns e correções]]).
- Regiões com rolagem horizontal (`.table-scroll`) devem levar `tabIndex={0}` e `role="region"`.
- Botões só com ícone têm `aria-label`.
