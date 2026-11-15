import { describe, expect, it } from "vitest";

import { serviceLabel, WEBHOOK_KINDS } from "./webhook";

describe("webhook", () => {
  it("lista os 6 avisos na ordem da tela", () => {
    expect(WEBHOOK_KINDS.map((k) => k.key)).toEqual(["due", "monthly", "weekly", "daily", "messages", "alerts"]);
    expect(WEBHOOK_KINDS.map((k) => k.label)).toEqual([
      "Lembrete de vencimentos",
      "Resumo do mês",
      "Resumo da semana (segundas)",
      "Disponível hoje",
      "Mensagens da caixa",
      "Alertas de gastos fora do padrão",
    ]);
  });

  it("dá nome ao serviço reconhecido pelo endereço", () => {
    expect(serviceLabel("discord")).toBe("Discord");
    expect(serviceLabel("slack")).toBe("Slack");
    expect(serviceLabel("generic")).toBe("Outro serviço");
  });
});
