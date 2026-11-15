/** v1.9.0: avisos por webhook. Os tipos seguem a ordem e os nomes de "Avisos por e-mail". */
export type WebhookKind = "due" | "monthly" | "weekly" | "daily" | "messages" | "alerts";
export type WebhookService = "discord" | "slack" | "generic";

export const WEBHOOK_KINDS: { key: WebhookKind; label: string }[] = [
  { key: "due", label: "Lembrete de vencimentos" },
  { key: "monthly", label: "Resumo do mês" },
  { key: "weekly", label: "Resumo da semana (segundas)" },
  { key: "daily", label: "Disponível hoje" },
  { key: "messages", label: "Mensagens da caixa" },
  { key: "alerts", label: "Alertas de gastos fora do padrão" },
];

export function serviceLabel(service: WebhookService): string {
  if (service === "discord") return "Discord";
  if (service === "slack") return "Slack";
  return "Outro serviço";
}
