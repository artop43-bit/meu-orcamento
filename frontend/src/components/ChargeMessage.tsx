import { useEffect, useState } from "react";
import { Copy } from "lucide-react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import type { FriendLoan, Share } from "../api/sharing";
import { announce } from "../lib/announce";
import { money } from "../lib/format";
import { Button } from "./ui";

type Kind = "reminder" | "late" | "summary" | "balance";

const FREQ: Record<FriendLoan["frequency"], string> = { day: "por dia", week: "por semana", biweek: "a cada 15 dias", month: "por mês" };

function date(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

function short(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

function buildText(kind: Kind, person: string, loan: FriendLoan | null, items: Share[], balance: number, pixLine: string): string {
  const first = person.trim().split(/\s+/)[0] ?? person;
  const pix = pixLine ? `\n\n${pixLine}` : "";
  if (!loan) {
    const what = items.length ? ` (${items.map((s) => s.description).join(", ")})` : "";
    return `Oi, ${first}! Passando para lembrar do valor em aberto comigo: ${money(balance)}${what}.${pix}\n\nObrigado!`;
  }
  if (kind === "late") {
    const late = loan.installments.filter((i) => i.status === "late");
    const parts = late.length === 1 ? `a parcela ${late[0]!.number}/${loan.count}` : `${late.length} parcelas`;
    const charge = late.some((i) => Number(i.late_charge) > 0) ? ", já com multa e juros" : "";
    return (
      `Oi, ${first}! Tudo bem? ${late.length === 1 ? "Ficou em aberto" : "Ficaram em aberto"} ${parts} do empréstimo, ` +
      `desde ${date(late[0]!.due_date)}. O valor para acertar é ${money(loan.late_amount)}${charge}.${pix}\n\n` +
      `Qualquer coisa, me avisa.`
    );
  }
  if (kind === "summary") {
    const next = loan.installments.filter((i) => i.status !== "paid").slice(0, 3);
    const list = next.map((i) => `${short(i.due_date)}: ${money(i.open)}`).join("\n");
    return (
      `Oi, ${first}! Segue o resumo do empréstimo:\n` +
      `Emprestado: ${money(loan.principal)} · Total: ${money(loan.total)} em ${loan.count}x ${FREQ[loan.frequency]}\n` +
      `Já pago: ${money(loan.received)} (${loan.paid_count} de ${loan.count})\n` +
      `Falta: ${money(loan.remaining)}` +
      (list ? `\n\nPróximos pagamentos:\n${list}` : "") +
      pix
    );
  }
  const n = loan.next;
  if (!n) return `Oi, ${first}! O empréstimo está quitado. Obrigado!`;
  return (
    `Oi, ${first}! Passando para lembrar da parcela ${n.number}/${loan.count} do empréstimo: ` +
    `${money(n.open)}, vence em ${date(n.due_date)}.${pix}\n\nFaltam ${money(loan.remaining)} no total. Obrigado!`
  );
}

/**
 * Cobrar (v1.8.0.2): mensagem pronta com a chave Pix de Preferências, para copiar e colar na
 * conversa. Só texto: nada de código Pix, QR ou link para outros serviços.
 */
export function ChargeMessage({ person, loan, items, balance }: { person: string; loan: FriendLoan | null; items: Share[]; balance: number }) {
  const me = useMe();
  const user = me.data;
  const suggested: Kind = !loan ? "balance" : loan.late_count > 0 ? "late" : "reminder";
  const [kind, setKind] = useState<Kind>(suggested);
  const [copied, setCopied] = useState(false);
  const key = user?.pix_key ?? "";
  const pixLine = key ? `Pix: ${key}${user?.pix_name ? ` (${user.pix_name})` : ""}` : "";
  const generated = buildText(kind, person, loan, items, balance, pixLine);
  const [text, setText] = useState(generated);
  // Trocar o tipo refaz o texto (o que foi editado à mão é substituído).
  useEffect(() => setText(generated), [generated]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      announce("Mensagem copiada");
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  }

  const kinds: { value: Kind; label: string }[] = loan
    ? [
        { value: "reminder", label: "Lembrete" },
        ...(loan.late_count > 0 ? [{ value: "late" as Kind, label: "Cobrança do atraso" }] : []),
        { value: "summary", label: "Resumo" },
      ]
    : [];

  return (
    <div className="stack charge">
      {!key && (
        <div className="alert alert--info" role="note">
          Cadastre a sua chave Pix uma vez para ela ir na mensagem. <Link to="/ajustes/preferencias#pix">Cadastrar chave Pix</Link>
        </div>
      )}
      {kinds.length > 1 && (
        <div className="chips" role="group" aria-label="Tipo de mensagem">
          {kinds.map((k) => (
            <button key={k.value} type="button" className="chip-btn" aria-pressed={kind === k.value} onClick={() => setKind(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
      )}
      <div className="field">
        <label htmlFor="charge-text">Mensagem</label>
        <textarea id="charge-text" className="charge__text" rows={9} value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <Button type="button" onClick={() => void copy()}>
          <Copy size={16} aria-hidden /> {copied ? "Mensagem copiada" : "Copiar mensagem"}
        </Button>
        {copied && (
          <span className="tone--ok small" role="status">
            É só colar na conversa.
          </span>
        )}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        A pessoa paga pelo app do banco dela usando a sua chave. Quando receber, marque em “Recebi a parcela”.
      </p>
    </div>
  );
}
