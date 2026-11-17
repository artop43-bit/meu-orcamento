---
tags: [meu-orcamento, design]
---
# Padrão visual

## Tema
- Cores como **tokens** (`--accent`, `--surface`, `--border`, `--muted`, `--error`...) em
  `theme.css`, com claro/escuro.
- `visual.css` é a camada de forma: **sem cores fixas (hex)**, só tokens.
- Dois estilos: **Padrão** e **Liquid glass** (`data-style`), 10 cores de destaque.

## Componentes e classes a reaproveitar
`card`, `kpis`/`Kpi`, `chips` + `chip-btn[aria-pressed]`, `segmented` (rádios), `items`/`item`,
`btn btn--primary|secondary`, `bar`/`bar__fill`, `list-tools list-tools--pills` +
`list-tools__search` + `pill-group`, `details`, `stats`/`stat`, `badge`, `Alert`
(`alert--info|error|success`), `inline-form`, `grid-2`, `form-actions`, `Sheet` (janela/modal
que vira bottom sheet no celular), `PageHeader`, `EmptyGuide`.

## Padrões de tela aprovados
- **Listas do dia a dia**: uma linha por item (ex.: pessoa), que **abre e fecha**, com busca,
  filtros em pílulas com contagem e "Abrir todos" (tela Divisões, v1.8).
- Formulários com prévia ao vivo do resultado antes de salvar.
- Celular: sem rolagem lateral, botões ocupando a largura, KPIs em 2 colunas.

## Acessibilidade
- Todo campo com rótulo; para `textarea` com texto longo, usar `<label htmlFor>` separado
  (ver [[Erros comuns e correções]]).
- Botões só com ícone têm `aria-label`.
