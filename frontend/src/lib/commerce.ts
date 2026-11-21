import type {
  CommercialDocument,
  CommercialDocType,
  CommercialOrder,
  LineItemDraft,
} from "../api/commerce";

export const DOC_TYPE_OPTIONS: { value: CommercialDocType; label: string; plural: string }[] = [
  { value: "proposal", label: "Proposta", plural: "Propostas" },
  { value: "service_order", label: "Ordem de Serviço", plural: "Ordens de Serviço" },
  { value: "contract", label: "Contrato", plural: "Contratos" },
  { value: "receipt", label: "Recibo", plural: "Recibos" },
];

export const DOC_STATUS_LABELS: Record<CommercialDocument["status"], string> = {
  draft: "Rascunho",
  sent: "Enviada",
  approved: "Aprovada",
  rejected: "Recusada",
  cancelled: "Cancelada",
};

export const ORDER_STATUS_LABELS: Record<CommercialOrder["status"], string> = {
  draft: "Rascunho",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
};

export const MOVEMENT_KIND_LABELS: Record<"in" | "out" | "adjust", string> = {
  in: "Entrada",
  out: "Saída",
  adjust: "Ajuste de saldo",
};

export function formatQty(val: number | string): string {
  const num = Number(val);
  if (!Number.isFinite(num)) return "0";
  if (Number.isInteger(num)) return String(num);
  if (Math.round(num * 1000) % 10 !== 0) {
    return num.toFixed(3).replace(".", ",");
  }
  return num.toFixed(2).replace(".", ",");
}

/** Arredonda em centavos com ROUND_HALF_UP exato, igual ao Decimal do backend. */
export function roundHalfUp(val: number): number {
  if (!Number.isFinite(val)) return 0;
  const sign = val < 0 ? -1 : 1;
  const scaled = Math.abs(val) * 100;
  const floored = Math.floor(scaled + 1e-9);
  const frac = scaled - floored;
  const roundedInt = frac >= 0.5 - 1e-9 ? floored + 1 : floored;
  return (sign * roundedInt) / 100;
}

export function calcDraftTotals(
  items: LineItemDraft[],
  discount: number,
): { subtotal: number; discount: number; total: number } {
  const subtotalCents = items.reduce((acc, row) => {
    const rawQ = Number(row.qty);
    const rawP = Number(row.unit_price);
    const q = Number.isFinite(rawQ) && rawQ > 0 ? Math.round(rawQ * 1000) / 1000 : 0;
    const p = Number.isFinite(rawP) && rawP >= 0 ? roundHalfUp(rawP) : 0;
    return acc + roundHalfUp(q * p);
  }, 0);
  const roundedSub = roundHalfUp(subtotalCents);
  const cleanDisc = Number.isFinite(discount) && discount > 0 ? roundHalfUp(discount) : 0;
  const total = roundHalfUp(roundedSub - cleanDisc);
  return { subtotal: roundedSub, discount: cleanDisc, total };
}

export function defaultWhatsappCaption(doc: CommercialDocument): string {
  const code = String(doc.number).padStart(4, "0");
  return `Olá, ${doc.customer_name}! Segue em anexo o documento #${code}: ${doc.title}.`;
}
