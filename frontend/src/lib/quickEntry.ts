import type { PaymentMethod } from "../api/budget";
import { LEXICON } from "./lexicon.generated";
import { normalizeText } from "./text";

/**
 * Lançamento numa frase: "mercado 120 pix ontem", "uber 23,50 débito",
 * "tv 1990 em 10x crédito dia 5" (valor total, 10 parcelas), "+ freelance 600" (receita).
 * Tudo o que não é valor, data, forma de pagamento ou parcelas vira a descrição.
 *
 * Desde a v1.7.6 as palavras vêm do núcleo de linguagem que o Tire sua dúvida também usa
 * (`lexicon.generated.ts`, copiado do backend): "gastei 50 no mercado", "paguei 200 de luz na
 * sexta", "recebi 3 mil de salário", "almocei 35 no cartão de débito" funcionam igual. Este
 * campo só registra: uma pergunta é encaminhada para o Tire sua dúvida (`looksLikeQuestion`).
 */
export type QuickEntry = {
  kind: "expense" | "income";
  description: string;
  amount: string | null;
  date: string | null; // AAAA-MM-DD
  payment: PaymentMethod | null;
  installments: number | null;
};

const PAYMENTS = new Map<string, PaymentMethod>(Object.entries(LEXICON.payments) as [string, PaymentMethod][]);
const DATE_WORDS = new Map<string, number>(Object.entries(LEXICON.dateWords));
const WEEKDAYS = new Map<string, number>(Object.entries(LEXICON.weekdays));
const MULTIPLIERS = new Map<string, number>(Object.entries(LEXICON.multipliers));
const VERB_NOUNS = new Map<string, string>(Object.entries(LEXICON.verbNouns));
const INCOME_VERBS = new Set<string>(LEXICON.incomeVerbs);
const INCOME_NOUNS = new Set<string>(LEXICON.incomeNouns);
const ENTRY_VERBS = new Set<string>(LEXICON.entryVerbs);
const ENTRY_NOUNS = new Set<string>(LEXICON.entryNouns);
const FILLER = new Set<string>(LEXICON.filler);
const QUESTION_STARTERS = new Set<string>(LEXICON.questionStarters);
const ASK_VERBS = new Set<string>(LEXICON.askVerbs);
const MONEY = new Set(["r$", "rs", "brl", "reais", "real", "conto", "contos", "pila", "pilas", "mango", "mangos"]);
/** Antes de um dia da semana, dizem que ele é a data ("na sexta"), e não parte da descrição. */
const BEFORE_WEEKDAY = new Set(["na", "no", "de", "da", "nessa", "nesta", "essa", "esta", "ultima", "ultimo"]);
const MAX_PHRASE = 4;

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** "120", "23,50", "1.234,56", "1234.5", "R$30", "2k", "1,5k" → "120.00" etc. */
function parseAmount(token: string): string | null {
  let text = token.replace(/^r\$/i, "");
  let times = 1;
  if (/^\d+([.,]\d+)?k$/i.test(text)) {
    times = 1000;
    text = text.slice(0, -1);
  }
  if (!/^\d{1,3}(\.\d{3})*(,\d{1,2})?$|^\d+([.,]\d{1,2})?$/.test(text)) return null;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const value = Number(normalized) * times;
  return value > 0 ? value.toFixed(2) : null;
}

/** Palavra para comparar: sem acento, minúscula e sem pontuação colada ("ai:" → "ai"). */
function clean(raw: string): string {
  const word = normalizeText(raw).replace(/-/g, " ");
  return /\d/.test(word) ? word.replace(/[.,;:!]+$/, "") : word.replace(/^[.,;:!"'()]+|[.,;:!"'()]+$/g, "");
}

/** A frase mais longa do vocabulário que começa na palavra `at`. */
function phraseAt<T>(words: string[], at: number, has: (phrase: string) => T | undefined): [T, number] | null {
  for (let size = Math.min(MAX_PHRASE, words.length - at); size >= 1; size--) {
    const found = has(words.slice(at, at + size).join(" "));
    if (found !== undefined) return [found, size];
  }
  return null;
}

const inSet = (set: Set<string>) => (phrase: string) => (set.has(phrase) ? phrase : undefined);

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
  const raws = text.split(/\s+/).filter(Boolean);
  // "segunda-feira" vira duas palavras para casar com o vocabulário.
  const pairs = raws.flatMap((raw) => {
    const parts = clean(raw).split(" ").filter(Boolean);
    return parts.length > 1 ? parts.map((part) => ({ raw: part, word: part })) : [{ raw, word: parts[0] ?? "" }];
  });
  const words = pairs.map((pair) => pair.word);
  const rest: string[] = [];
  const opening: string[] = []; // verbos e avisos tirados do começo ("gastei", "despesa")
  let amount: string | null = null;
  let date: string | null = null;
  let payment: PaymentMethod | null = null;
  let installments: number | null = null;

  for (let i = 0; i < words.length; i++) {
    const { raw, word } = pairs[i];
    const next = words[i + 1] ?? "";
    if (!word) continue;

    // Começo da frase: verbos de receita ("recebi"), de lançamento ("gastei", "lançar") e avisos ("despesa").
    if (rest.length === 0 && amount === null) {
      const income = phraseAt(words, i, inSet(INCOME_VERBS));
      if (income && opening.every((w) => !ENTRY_VERBS.has(w))) {
        kind = "income";
        opening.push(income[0]);
        i += income[1] - 1;
        continue;
      }
      if (ENTRY_VERBS.has(word) || ENTRY_NOUNS.has(word)) {
        opening.push(word);
        continue;
      }
    }

    // Datas: "hoje", "ontem", "antes de ontem", "amanhã", dia da semana.
    const day = phraseAt(words, i, (phrase) => DATE_WORDS.get(phrase));
    if (day) {
      const d = new Date(today);
      d.setDate(d.getDate() + day[0]);
      date = iso(d);
      i += day[1] - 1;
      continue;
    }
    const weekday = phraseAt(words, i, (phrase) => WEEKDAYS.get(phrase));
    if (weekday) {
      const after = words[i + weekday[1]] ?? "";
      const last = i + weekday[1] >= words.length;
      const marked = weekday[1] > 1 || after === "passada" || after === "passado" || BEFORE_WEEKDAY.has(words[i - 1] ?? "");
      if (marked || last) {
        // O último dia assim que já passou (hoje conta).
        const back = (((today.getDay() + 6) % 7) - weekday[0] + 7) % 7;
        const d = new Date(today);
        d.setDate(d.getDate() - back);
        date = iso(d);
        i += weekday[1] - 1;
        if (after === "passada" || after === "passado") i++;
        continue;
      }
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

    // Parcelas: "10x", "10 x", "10 vezes", "10 parcelas".
    const parcels = word.match(/^(\d{1,3})x$/);
    if (parcels && Number(parcels[1]) >= 2) {
      installments = Number(parcels[1]);
      continue;
    }
    if (/^\d{1,3}$/.test(word) && Number(word) >= 2 && /^(x|vezes|parcelas)$/.test(next)) {
      installments = Number(word);
      i++;
      continue;
    }

    const pay = phraseAt(words, i, (phrase) => PAYMENTS.get(phrase));
    if (pay) {
      payment = pay[0];
      i += pay[1] - 1;
      continue;
    }

    // "R$ 50": o símbolo solto antes do valor não entra na descrição.
    if (MONEY.has(word) && amount === null && parseAmount(next) !== null) continue;
    let value: string | null = amount === null ? parseAmount(word) : null;
    if (value === null && amount === null && MULTIPLIERS.has(word) && word !== "k") value = MULTIPLIERS.get(word)!.toFixed(2); // "mil"
    if (value !== null) {
      const times = MULTIPLIERS.get(next); // "2 mil", "3 k"
      if (times && !/k$/i.test(word) && !MULTIPLIERS.has(word)) {
        value = (Number(value) * times).toFixed(2);
        i++;
      }
      amount = value;
      // "50 reais", "50 conto": a moeda não entra na descrição.
      while (MONEY.has(words[i + 1] ?? "")) i++;
      continue;
    }
    if (FILLER.has(word) && (rest.length === 0 || i === words.length - 1)) continue;
    rest.push(raw.replace(/[;:!]+$/, ""));
  }
  // Tira preposições soltas no fim ("mercado no").
  while (rest.length && FILLER.has(clean(rest[rest.length - 1]))) rest.pop();
  let description = rest.join(" ");
  if (!description) {
    // "almocei 35" vira "Almoço"; "despesa 50" fica "Despesa".
    const verb = opening.find((w) => VERB_NOUNS.has(w));
    const noun = opening.find((w) => ENTRY_NOUNS.has(w) && w.length > 3);
    description = verb ? VERB_NOUNS.get(verb)! : (noun ?? (kind === "income" && opening.length ? "receita" : ""));
  } else if (kind === "expense") {
    // "salário 3000", "freela 600": o nome já diz que é receita.
    const names = description.split(/\s+/).map(clean);
    if (phraseAt(names, 0, inSet(INCOME_NOUNS))) kind = "income";
  }
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

/**
 * Parece uma pergunta ("quanto gastei este mês?")? O Lançamento rápido só registra: perguntas
 * vão para o Tire sua dúvida.
 */
export function looksLikeQuestion(input: string): boolean {
  const text = input.trim();
  if (!text || text.startsWith("+")) return false;
  if (text.endsWith("?")) return true;
  const words = text.split(/\s+/).map(clean).filter(Boolean);
  if (phraseAt(words, 0, inSet(QUESTION_STARTERS))) return true;
  if (phraseAt(words, 0, inSet(ASK_VERBS))) return parseQuickEntry(text).amount === null;
  return false;
}
