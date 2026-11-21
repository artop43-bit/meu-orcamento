import { describe, expect, it } from "vitest";

import {
  calcDraftTotals,
  defaultWhatsappCaption,
  DOC_STATUS_LABELS,
  DOC_TYPE_OPTIONS,
  formatQty,
} from "./commerce";

describe("helpers de catálogo, pedidos e documentos comerciais", () => {
  it("calcula subtotal, arredondamento ROUND_HALF_UP e preserva desconto para validação do servidor", () => {
    const res = calcDraftTotals(
      [
        { name: "Kit Solar", qty: 2, unit_price: 1200.5 },
        { name: "Instalação", qty: 1, unit_price: 350 },
      ],
      100.5,
    );
    expect(res).toEqual({ subtotal: 2751, discount: 100.5, total: 2650.5 });

    const halfUp = calcDraftTotals([{ name: "Granel", qty: 0.125, unit_price: 10.04 }], 0);
    // 0.125 * 10.04 = 1.255 -> 1.26 (meio para cima, igual Decimal ROUND_HALF_UP).
    expect(halfUp).toEqual({ subtotal: 1.26, discount: 0, total: 1.26 });

    const unclipped = calcDraftTotals([{ name: "Serviço", qty: 1, unit_price: 200 }], 999);
    expect(unclipped).toEqual({ subtotal: 200, discount: 999, total: -799 });
  });

  it("formata quantidades inteiras e decimais (até 3 casas) em pt-BR", () => {
    expect(formatQty(3)).toBe("3");
    expect(formatQty("3.000")).toBe("3");
    expect(formatQty(1.5)).toBe("1,50");
    expect(formatQty("0.125")).toBe("0,125");
  });

  it("mantém tipos e legendas sem qualquer menção a Pix ou integração bancária", () => {
    const caption = defaultWhatsappCaption({
      id: "1",
      doc_type: "proposal",
      doc_label: "PROPOSTA COMERCIAL",
      number: 7,
      title: "Projeto Elétrico",
      contact_id: null,
      crm_deal_id: null,
      order_id: null,
      customer_name: "Ana Costa",
      customer_doc: null,
      customer_contact: null,
      items: [],
      discount: "0.00",
      total_amount: "1500.00",
      valid_until: null,
      terms_text: null,
      status: "draft",
      budget_income_id: null,
      created_at: "2026-11-20T12:00:00Z",
      updated_at: "2026-11-20T12:00:00Z",
    });
    expect(caption).toContain("#0007");
    expect(caption.toLowerCase()).not.toContain("pix");
    expect(DOC_TYPE_OPTIONS.map((o) => o.value)).toEqual([
      "proposal",
      "service_order",
      "contract",
      "receipt",
    ]);
    expect(DOC_STATUS_LABELS.approved).toBe("Aprovada");
  });
});
