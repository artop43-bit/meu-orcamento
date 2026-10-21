import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Copy, Share2 } from "lucide-react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { announce } from "../lib/announce";
import { money } from "../lib/format";
import { pixCode } from "../lib/pix";
import { Button } from "./ui";

/** Divisões › Cobrar via Pix (v1.4): código "copia e cola" e QR com o valor que a pessoa deve. */
export function PixCharge({ person, amount }: { person: string; amount: number }) {
  const me = useMe();
  const [copied, setCopied] = useState(false);
  const user = me.data;
  if (!user?.pix_key) {
    return (
      <div className="stack">
        <p style={{ margin: 0 }}>Para cobrar via Pix, cadastre a sua chave uma vez.</p>
        <Link className="btn btn--primary" to="/ajustes/preferencias#pix">
          Cadastrar chave Pix
        </Link>
      </div>
    );
  }
  const code = pixCode({
    key: user.pix_key,
    name: user.pix_name || user.display_name || "Recebedor",
    city: user.pix_city || "Brasil",
    amount,
    message: "Meu Orcamento",
  });
  const text = `Oi, ${person}! Segue o Pix de ${money(amount)} (copia e cola):\n${code}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      announce("Código Pix copiado");
    } catch {
      setCopied(false);
    }
  }

  async function share() {
    if (navigator.share) {
      await navigator.share({ text }).catch(() => undefined);
    } else {
      await navigator.clipboard.writeText(text).catch(() => undefined);
      announce("Mensagem com o Pix copiada");
    }
  }

  return (
    <div className="stack pix-charge">
      <p style={{ margin: 0 }}>
        {person} deve <strong>{money(amount)}</strong>. Mande o código abaixo: o app do banco lê o QR ou o “copia e cola” e mostra o seu nome e o
        valor antes do pagamento.
      </p>
      <div className="pix-charge__qr">
        <QRCodeSVG value={code} size={196} marginSize={2} title={`QR Code Pix de ${money(amount)}`} />
      </div>
      <label>
        Pix copia e cola
        <textarea readOnly value={code} rows={3} onFocus={(e) => e.currentTarget.select()} className="pix-charge__code" />
      </label>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <Button type="button" onClick={() => void copy()}>
          <Copy size={16} aria-hidden /> {copied ? "Copiado" : "Copiar código"}
        </Button>
        <Button type="button" variant="secondary" onClick={() => void share()}>
          <Share2 size={16} aria-hidden /> Enviar mensagem
        </Button>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Chave: {user.pix_key}. O pagamento cai direto na sua conta; o app não intermedeia nada. Depois que receber, use “Acertar contas”.
      </p>
    </div>
  );
}
