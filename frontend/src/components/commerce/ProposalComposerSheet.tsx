import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import {
  proposalsApi,
  type CommercialDocType,
  type CommercialDocument,
  type LineItemDraft,
  type ProposalBridges,
} from "../../api/commerce";
import { announce } from "../../lib/announce";
import { calcDraftTotals, DOC_TYPE_OPTIONS } from "../../lib/commerce";
import { money, moneyToNumber } from "../../lib/format";
import { LineItemsEditor } from "../../pages/commerce/LineItemsEditor";
import { DateField } from "../DateField";
import { MoneyInput } from "../budget";
import { Tip } from "../help";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para emitir uma proposta comercial, OS, contrato ou recibo em PDF local. */
export function ProposalComposerSheet({
  open,
  initialType,
  bridges,
  onClose,
  onCreated,
}: {
  open: boolean;
  initialType: CommercialDocType;
  bridges: ProposalBridges | undefined;
  onClose: () => void;
  onCreated: (doc: CommercialDocument) => void;
}) {
  const [docType, setDocType] = useState<CommercialDocType>(initialType);
  const [title, setTitle] = useState("");
  const [contactId, setContactId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerDoc, setCustomerDoc] = useState("");
  const [customerContact, setCustomerContact] = useState("");
  const [lines, setLines] = useState<LineItemDraft[]>([
    { name: "", unit: "un", qty: 1, unit_price: 0 },
  ]);
  const [discount, setDiscount] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [termsText, setTermsText] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDocType(initialType);
    setTitle("");
    setContactId("");
    setOrderId("");
    setCustomerName("");
    setCustomerDoc("");
    setCustomerContact("");
    setLines([{ name: "", unit: "un", qty: 1, unit_price: 0 }]);
    setDiscount("");
    setValidUntil("");
    setTermsText("Prazo e condições combinados diretamente entre as partes.");
    setFormErr(null);
  }, [open, initialType]);

  const createDoc = useMutation({
    mutationFn: () =>
      proposalsApi.create({
        doc_type: docType,
        title: title.trim() || undefined,
        contact_id: contactId || null,
        order_id: orderId || null,
        customer_name: customerName.trim() || undefined,
        customer_doc: customerDoc.trim() || undefined,
        customer_contact: customerContact.trim() || undefined,
        items: lines,
        discount: moneyToNumber(discount),
        valid_until: validUntil || null,
        terms_text: termsText.trim() || undefined,
      }),
    onSuccess: (doc) => {
      onClose();
      onCreated(doc);
      announce("Documento comercial criado");
    },
    onError: (e) => setFormErr(errorMessage(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!contactId && !orderId && !customerName.trim()) {
      setFormErr("Informe o cliente ou selecione um contato/pedido.");
      return;
    }
    createDoc.mutate();
  }

  const draftTotals = calcDraftTotals(lines, moneyToNumber(discount));

  return (
    <Sheet open={open} title="Emitir documento comercial em PDF" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {formErr && <Alert tone="error">{formErr}</Alert>}

        <div className="field">
          <span className="field-label">Tipo do documento</span>
          <div className="chips" role="group" aria-label="Tipo de documento">
            {DOC_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className="chip-btn"
                aria-pressed={docType === opt.value}
                onClick={() => setDocType(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Validade</span>
            <DateField
              value={validUntil}
              onChange={setValidUntil}
              label="Validade do documento"
            />
          </label>
          <label className="field">
            <span className="field-label">Título</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: Projeto rede corporativa"
            />
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Importar contato CRM</span>
            <select
              value={contactId}
              onChange={(e) => {
                const id = e.target.value;
                setContactId(id);
                const found = bridges?.contacts.find((c) => c.id === id);
                if (found) {
                  setCustomerName(found.name);
                  if (found.phone_display || found.email) {
                    setCustomerContact(found.phone_display || found.email || "");
                  }
                }
              }}
            >
              <option value="">Preencher manualmente</option>
              {(bridges?.contacts ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.phone_display ? `(${c.phone_display})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Vincular pedido do Catálogo</span>
            <select
              value={orderId}
              onChange={(e) => {
                const id = e.target.value;
                setOrderId(id);
                const ord = bridges?.orders.find((o) => o.id === id);
                if (ord) {
                  if (!customerName) setCustomerName(ord.customer_name);
                  if (ord.items.length > 0) setLines(ord.items);
                  setDiscount(Number(ord.discount) > 0 ? String(ord.discount).replace(".", ",") : "");
                }
              }}
            >
              <option value="">Sem vínculo com pedido</option>
              {(bridges?.orders ?? []).map((o) => (
                <option key={o.id} value={o.id}>
                  Pedido #{String(o.number).padStart(4, "0")} — {o.customer_name} ({money(o.total_amount)})
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Nome do cliente</span>
            <input
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              placeholder="Nome completo ou empresa"
            />
          </label>
          <label className="field">
            <span className="field-label">CPF / CNPJ (opcional)</span>
            <input
              value={customerDoc}
              onChange={(e) => setCustomerDoc(e.target.value)}
              placeholder="Informado só no PDF"
            />
          </label>
        </div>

        <label className="field">
          <span className="field-label">Telefone / E-mail do cliente</span>
          <input
            value={customerContact}
            onChange={(e) => setCustomerContact(e.target.value)}
            placeholder="(11) 99999-9999 ou contato@empresa.com"
          />
        </label>

        <LineItemsEditor
          label="Itens ou serviços do documento"
          addLabel="Nova linha"
          customOptionLabel="Serviço / item livre"
          lines={lines}
          catalogItems={bridges?.catalog_items ?? []}
          onChange={setLines}
        />

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Desconto (R$)</span>
            <MoneyInput value={discount} onChange={setDiscount} placeholder="0,00" required={false} />
          </label>
          <div className="summary-box">
            <div className="split small">
              <span>Subtotal</span>
              <span>{money(draftTotals.subtotal)}</span>
            </div>
            <div className="split">
              <strong>Valor final do PDF</strong>
              <strong className="tone--ok">{money(draftTotals.total)}</strong>
            </div>
            <span className="muted small">PDF A4 local · sem dados bancários ou Pix</span>
          </div>
        </div>

        <div className="field">
          <label htmlFor="prop-terms" className="field-label">
            Condições e observações{" "}
            <Tip>Esse texto entra no rodapé do PDF A4 gerado para o cliente.</Tip>
          </label>
          <textarea
            id="prop-terms"
            rows={3}
            value={termsText}
            onChange={(e) => setTermsText(e.target.value)}
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={createDoc.isPending}>
            Emitir documento em PDF
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
