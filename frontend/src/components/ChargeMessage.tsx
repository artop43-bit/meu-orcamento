import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { Copy, MessageCircle, Share2 } from "lucide-react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { SPLITS_KEY, sharingApi, type FriendLoan, type Share } from "../api/sharing";
import { announce } from "../lib/announce";
import { money } from "../lib/format";
import { pixCode } from "../lib/pix";
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

/** Valor que a mensagem cobra (também vai no Pix copia e cola). */
function amountFor(kind: Kind, loan: FriendLoan | null, balance: number): number {
  if (!loan) return balance;
  if (kind === "late") return Number(loan.late_amount);
  if (kind === "summary") return Number(loan.remaining);
  return loan.next ? Number(loan.next.open) + Number(loan.next.late_charge) : Number(loan.remaining);
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
 * Cobrar (v1.8.0.1): mensagem pronta com a chave Pix de Preferências, para mandar pelo WhatsApp,
 * copiar ou compartilhar. Opcionalmente com o Pix "copia e cola" no valor exato (sem banco: o código
 * é gerado no aparelho e qualquer app de banco lê).
 */
export function ChargeMessage({ person, loan, items, balance }: { person: string; loan: FriendLoan | null; items: Share[]; balance: number }) {
  const me = useMe();
  const user = me.data;
  const queryClient = useQueryClient();
  const suggested: Kind = !loan ? "balance" : loan.late_count > 0 ? "late" : "reminder";
  const [kind, setKind] = useState<Kind>(suggested);
  const [withCode, setWithCode] = useState(true);
  const [phone, setPhone] = useState(loan?.phone ?? "");
  const [copied, setCopied] = useState(false);
  const value = amountFor(kind, loan, balance);
  const key = user?.pix_key ?? "";
  const code = useMemo(
    () =>
      key
        ? pixCode({
            key,
            name: user?.pix_name || user?.display_name || "Recebedor",
            city: user?.pix_city || "Brasil",
            amount: value,
            message: "Meu Orcamento",
          })
        : "",
    [key, user?.pix_name, user?.display_name, user?.pix_city, value],
  );
  const pixLine = key
    ? `Pix: ${key}${user?.pix_name ? ` (${user.pix_name})` : ""}` + (withCode && code ? `\n\nPix copia e cola (${money(value)}):\n${code}` : "")
    : "";
  const generated = buildText(kind, person, loan, items, balance, pixLine);
  const [text, setText] = useState(generated);
  // Trocar o tipo ou o copia e cola refaz o texto (o que foi editado à mão é substituído).
  useEffect(() => setText(generated), [generated]);

  const digits = phone.replace(/\D/g, "");
  const waNumber = digits.length >= 10 ? (digits.length <= 11 ? `55${digits}` : digits) : "";

  async function savePhone() {
    if (!loan || (loan.phone ?? "") === digits) return;
    await sharingApi.setPhone(loan.id, digits).catch(() => undefined);
    await queryClient.invalidateQueries({ queryKey: SPLITS_KEY });
  }

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

  const canShare = typeof navigator.share === "function" && window.matchMedia("(pointer: coarse)").matches;
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
      <label>
        Mensagem
        <textarea className="charge__text" rows={9} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {key && (
        <label className="check">
          <input type="checkbox" checked={withCode} onChange={(e) => setWithCode(e.target.checked)} />
          Incluir código Pix copia e cola ({money(value)})
        </label>
      )}
      {loan && (
        <label>
          Telefone de {person.split(" ")[0]} (opcional, para abrir direto no WhatsApp)
          <input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} onBlur={() => void savePhone()} placeholder="(62) 99999-0000" />
        </label>
      )}
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <a
          className="btn btn--primary"
          href={`https://wa.me/${waNumber}?text=${encodeURIComponent(text)}`}
          target="_blank"
          rel="noreferrer"
          onClick={() => void savePhone()}
        >
          <MessageCircle size={16} aria-hidden /> Abrir no WhatsApp
        </a>
        <Button type="button" variant="secondary" onClick={() => void copy()}>
          <Copy size={16} aria-hidden /> {copied ? "Mensagem copiada" : "Copiar"}
        </Button>
        {canShare && (
          <Button type="button" variant="secondary" onClick={() => void navigator.share({ text }).catch(() => undefined)}>
            <Share2 size={16} aria-hidden /> Compartilhar
          </Button>
        )}
      </div>
      {copied && (
        <p className="tone--ok small" role="status" style={{ margin: 0 }}>
          Mensagem copiada. É só colar na conversa.
        </p>
      )}
      {code && (
        <details className="details">
          <summary>Mostrar QR Code do Pix</summary>
          <div className="pix-charge__qr">
            <QRCodeSVG value={code} size={196} marginSize={2} title={`QR Code Pix de ${money(value)}`} />
          </div>
        </details>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        O Pix cai direto na sua conta; o site não confirma sozinho. Quando receber, use “Recebi a parcela”.
      </p>
    </div>
  );
}
