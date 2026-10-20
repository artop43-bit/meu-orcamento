import type { ReactNode } from "react";
import { BookOpen, Car, HeartPulse, Home, Landmark, PiggyBank, Plane, ShieldCheck, ShoppingBag, Target, Wallet } from "lucide-react";

import type { Goal, GoalKind } from "../api/budget";
import { money, monthLabel } from "./format";

export const GOAL_KINDS: { value: GoalKind; label: string; icon: ReactNode; example: string }[] = [
  { value: "emergency", label: "Reserva de emergência", icon: <ShieldCheck size={18} />, example: "Reserva de emergência" },
  { value: "purchase", label: "Compra de um bem", icon: <ShoppingBag size={18} />, example: "MacBook Pro" },
  { value: "travel", label: "Viagem", icon: <Plane size={18} />, example: "Viagem a Lisboa" },
  { value: "health", label: "Saúde", icon: <HeartPulse size={18} />, example: "Cirurgia ortopédica" },
  { value: "education", label: "Educação", icon: <BookOpen size={18} />, example: "Pós-graduação" },
  { value: "home", label: "Imóvel", icon: <Home size={18} />, example: "Entrada do apartamento" },
  { value: "vehicle", label: "Veículo", icon: <Car size={18} />, example: "Troca do carro" },
  { value: "debt", label: "Quitar dívida", icon: <Wallet size={18} />, example: "Quitar o cartão" },
  { value: "retirement", label: "Aposentadoria", icon: <PiggyBank size={18} />, example: "Independência financeira" },
  { value: "other", label: "Outro objetivo", icon: <Target size={18} />, example: "Meu objetivo" },
];

export function goalKind(kind: GoalKind | undefined) {
  return GOAL_KINDS.find((k) => k.value === kind) ?? GOAL_KINDS[GOAL_KINDS.length - 1]!;
}

export const GoalIcon = Landmark;

function monthsText(n: number): string {
  return n === 1 ? "1 mês" : `${n} meses`;
}

/** Frase da projeção, objetiva: status + data prevista + o que fazer quando estiver abaixo. */
export function projectionText(goal: Goal): { tone: "ok" | "warn" | "info" | "done"; text: string } {
  const p = goal.projection;
  if (!p) return { tone: "info", text: "" };
  const eta = p.eta ? monthLabel(p.eta.slice(0, 7)) : "";
  const source =
    p.pace_source === "surplus"
      ? " considerando a sobra média do orçamento"
      : p.pace_source === "plan"
        ? ` com aportes de ${money(p.pace)} por mês`
        : "";
  switch (p.status) {
    case "completed":
      return { tone: "done", text: "Meta concluída." };
    case "ahead":
      return { tone: "ok", text: `Adiantada: no ritmo atual, conclusão em ${eta} (${monthsText(p.months_needed ?? 0)}), antes do prazo.` };
    case "on_track":
      return { tone: "ok", text: `No ritmo: conclusão prevista para ${eta} (${monthsText(p.months_needed ?? 0)})${source}.` };
    case "behind":
      return {
        tone: "warn",
        text: `Abaixo do ritmo: para concluir no prazo, o aporte mensal precisa ser de ${money(p.required_monthly)}${
          p.pace ? `; a média atual é ${money(p.pace)}` : ""
        }.${eta ? ` No ritmo atual, conclusão em ${eta}.` : ""}`,
      };
    case "estimate":
      return { tone: "info", text: `Conclusão prevista para ${eta} (${monthsText(p.months_needed ?? 0)})${source}.` };
    default:
      return {
        tone: "info",
        text: p.required_monthly
          ? `Para concluir no prazo, guarde ${money(p.required_monthly)} por mês.`
          : "Sem aportes recentes. Defina um valor mensal para estimar a conclusão.",
      };
  }
}
