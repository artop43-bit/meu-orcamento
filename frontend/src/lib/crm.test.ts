import { describe, expect, it } from "vitest";

import {
  dealBudgetState,
  dealDeleteConfirmText,
  formatCrmCell,
  formatDateBr,
  formatWidgetValue,
  percentShare,
  strategyLabel,
  widgetAriaLabel,
} from "./crm";

const nbsp = (text: string) => text.replace(/ /g, " ");

describe("utilitários do Dashboard & CRM", () => {
  it("traduz estratégias de leitura de PDF e calcula percentuais", () => {
    expect(strategyLabel("tabela_pdf")).toBe("Tabela nativa do PDF");
    expect(strategyLabel("ocr_texto")).toBe("OCR local · documento");
    expect(strategyLabel("desconhecida")).toBe("Extração local");
    expect(percentShare(25, 100)).toBe(25);
    expect(percentShare(1, 0)).toBe(0);
  });

  it("formata células e datas no padrão brasileiro", () => {
    expect(formatDateBr("2026-11-20")).toBe("20/11/2026");
    expect(formatCrmCell(1234.5, "number")).toBe("1.234,5");
    expect(formatCrmCell(true, "boolean")).toBe("Sim");
    expect(formatCrmCell(false, "boolean")).toBe("Não");
    expect(formatCrmCell(null, "text")).toBe("—");
  });
});

describe("resumo dos gráficos para leitores de tela", () => {
  const series = [
    { label: "Janeiro", value: 1200, count: 3 },
    { label: "Fevereiro", value: 300, count: 1 },
  ];

  it("lista rótulo e valor de cada barra", () => {
    expect(nbsp(widgetAriaLabel("bar", series, "currency"))).toBe(
      "Barras: Janeiro R$ 1.200,00; Fevereiro R$ 300,00",
    );
    expect(widgetAriaLabel("line", series, "number")).toBe("Linha: Janeiro 1.200; Fevereiro 300");
  });

  it("mostra a parte de cada fatia da rosca e a contagem do funil", () => {
    expect(widgetAriaLabel("donut", [...series, { label: "Zero", value: 0, count: 0 }], "number")).toBe(
      "Rosca: Janeiro 1.200 (80%); Fevereiro 300 (20%)",
    );
    expect(widgetAriaLabel("funnel", series, "number")).toBe(
      "Funil: Janeiro 1.200 (3 registro(s)); Fevereiro 300 (1 registro(s))",
    );
  });

  it("avisa quando não há dados e resume séries longas", () => {
    expect(widgetAriaLabel("bar", [], "number")).toBe("Barras: sem dados");
    expect(widgetAriaLabel("donut", [{ label: "Negativo", value: -5, count: 1 }])).toBe("Rosca: sem dados");
    const many = Array.from({ length: 15 }, (_, i) => ({ label: `M${i + 1}`, value: i, count: 1 }));
    const label = widgetAriaLabel("line", many, "number");
    expect(label.startsWith("Linha: M1 0; M2 1;")).toBe(true);
    expect(label.endsWith("M12 11; e mais 3")).toBe(true);
  });

  it("formata o valor como moeda ou número", () => {
    expect(nbsp(formatWidgetValue(1850, "currency"))).toBe("R$ 1.850,00");
    expect(formatWidgetValue(12.5)).toBe("12,5");
  });
});

describe("negócio e Meu Orçamento", () => {
  it("mostra a receita já lançada no lugar do botão", () => {
    expect(dealBudgetState({ status: "won", budget_income_id: null })).toBe("can_send");
    expect(dealBudgetState({ status: "won", budget_income_id: "abc" })).toBe("sent");
    expect(dealBudgetState({ status: "open", budget_income_id: "abc" })).toBe("sent");
    expect(dealBudgetState({ status: "open", budget_income_id: null })).toBe("hidden");
    expect(dealBudgetState({ status: "lost", budget_income_id: null })).toBe("hidden");
  });

  it("pede confirmação antes de excluir o negócio", () => {
    expect(dealDeleteConfirmText({ title: "Consultoria", budget_income_id: null })).toBe(
      'Excluir o negócio "Consultoria"? As atividades dele também serão apagadas.',
    );
    expect(dealDeleteConfirmText({ title: "Consultoria", budget_income_id: "abc" })).toBe(
      'Excluir o negócio "Consultoria"? As atividades dele também serão apagadas. A receita já lançada continua no Meu Orçamento.',
    );
  });
});
