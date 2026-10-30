import type { PaymentMethod } from "../api/budget";
import { normalizeText } from "./text";

/**
 * Lançamento numa frase: "mercado 120 pix ontem", "uber 23,50 débito",
 * "tv 1990 em 10x crédito dia 5" (valor total, 10 parcelas), "+ freelance 600" (receita).
 * Tudo o que não é valor, data, forma de pagamento ou parcelas vira a descrição.
 */
export type QuickEntry = {
  kind: "expense" | "income";
  description: string;
  amount: string | null;
  date: string | null; // AAAA-MM-DD
  payment: PaymentMethod | null;
  installments: number | null;
};

const PAYMENTS: [RegExp, PaymentMethod][] = [
  [/^pix$/, "pix"],
  [/^(debito|deb)$/, "debit"],
  [/^(credito|cred|cartao)$/, "credit"],
  [/^boleto$/, "boleto"],
  [/^(dinheiro|especie|cash)$/, "cash"],
];

const INCOME_WORDS = new Set(["recebi", "renda", "entrada", "ganhei"]);
const FILLER = new Set(["no", "na", "de", "do", "da", "em", "com", "r$", "reais"]);

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** "120", "23,50", "1.234,56", "1234.5", "R$30" → "120.00" etc. */
function parseAmount(token: string): string | null {
  const text = token.replace(/^r\$/i, "");
  if (!/^\d{1,3}(\.\d{3})*(,\d{1,2})?$|^\d+([.,]\d{1,2})?$/.test(text)) return null;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const value = Number(normalized);
  return value > 0 ? value.toFixed(2) : null;
}

/**
 * `month` (AAAA-MM): mês aberto na tela. "dia 5" cai nele; sem data na frase, `date` fica nula e
 * quem salva usa `defaultEntryDate`.
 */
export function parseQuickEntry(input: string, today: Date = new Date(), month?: string): QuickEntry {
  let text = input.trim();
  let kind: QuickEntry["kind"] = "expense";
  if (text.startsWith("+")) {
    kind = "income";
    text = text.slice(1).trim();
  }
  const words = text.split(/\s+/).filter(Boolean);
  const rest: string[] = [];
  let amount: string | null = null;
  let date: string | null = null;
  let payment: PaymentMethod | null = null;
  let installments: number | null = null;

  for (let i = 0; i < words.length; i++) {
    const raw = words[i];
    const word = normalizeText(raw);
    const next = normalizeText(words[i + 1] ?? "");
    if (i === 0 && INCOME_WORDS.has(word)) {
      kind = "income";
      continue;
    }
    if (word === "hoje") {
      date = iso(today);
      continue;
    }
    if (word === "ontem" || word === "anteontem") {
      const d = new Date(today);
      d.setDate(d.getDate() - (word === "ontem" ? 1 : 2));
      date = iso(d);
      continue;
    }
    if (word === "dia" && /^\d{1,2}$/.test(next)) {
      const [y, m] = month ? month.split("-").map(Number) : [today.getFullYear(), today.getMonth() + 1];
      const d = new Date(y, m - 1, Number(next));
      date = iso(d);
      i++;
      continue;
    }
    const dm = word.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/);
    if (dm) {
      const year = dm[3] ? Number(dm[3].length === 2 ? `20${dm[3]}` : dm[3]) : today.getFullYear();
      date = iso(new Date(year, Number(dm[2]) - 1, Number(dm[1])));
      continue;
    }
    const parcels = word.match(/^(\d{1,3})x$/);
    if (parcels && Number(parcels[1]) >= 2) {
      installments = Number(parcels[1]);
      continue;
    }
    const pay = PAYMENTS.find(([re]) => re.test(word));
    if (pay) {
      payment = pay[1];
      continue;
    }
    const value: string | null = amount === null ? parseAmount(word) : null;
    if (value !== null) {
      amount = value;
      continue;
    }
    if (FILLER.has(word) && (rest.length === 0 || i === words.length - 1)) continue;
    rest.push(raw);
  }
  // Tira preposições soltas no fim ("mercado no").
  while (rest.length && FILLER.has(normalizeText(rest[rest.length - 1]))) rest.pop();
  const description = rest.join(" ");
  return {
    kind,
    description: description ? description[0].toUpperCase() + description.slice(1) : "",
    amount,
    date,
    payment,
    installments: kind === "expense" ? installments : null,
  };
}

/** Data de um lançamento sem data na frase: hoje no mês atual; dia 1 do mês aberto, se for outro. */
export function defaultEntryDate(month: string | undefined, today: Date = new Date()): string {
  const now = iso(today);
  return month && month !== now.slice(0, 7) ? `${month}-01` : now;
}

/** Parece uma frase de lançamento? (tem valor e alguma descrição) */
export function looksLikeEntry(entry: QuickEntry): boolean {
  return entry.amount !== null && entry.description.length >= 2;
}
