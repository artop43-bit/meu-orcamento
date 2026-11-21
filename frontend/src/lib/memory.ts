import type { VaultCategory, VaultExpiryStatus } from "../api/memory";

export const VAULT_CATEGORY_OPTIONS: { value: VaultCategory; label: string }[] = [
  { value: "warranty", label: "Garantia" },
  { value: "contract", label: "Contrato" },
  { value: "fiscal", label: "Nota fiscal" },
  { value: "receipt", label: "Comprovante / Recibo" },
  { value: "certificate", label: "Certificado / Apólice" },
  { value: "identity", label: "Documento pessoal" },
  { value: "other", label: "Outro documento" },
];

export const EXPIRY_FILTER_LABELS: Record<"all" | VaultExpiryStatus, string> = {
  all: "Todos",
  expiring_soon: "Vencendo",
  expired: "Vencidos",
  valid: "Na validade",
  no_expiry: "Sem prazo",
};

export function expiryBadgeInfo(
  status: VaultExpiryStatus,
  daysLeft: number | null,
): { label: string; tone: "accent" | "warn" | "neutral" } {
  if (status === "expired") {
    const abs = daysLeft !== null ? Math.abs(daysLeft) : 0;
    return { label: abs === 0 ? "Vence hoje" : `Vencido há ${abs}d`, tone: "warn" };
  }
  if (status === "expiring_soon") {
    return {
      label: daysLeft === 0 ? "Vence hoje" : `Vence em ${daysLeft ?? 0}d`,
      tone: "warn",
    };
  }
  if (status === "valid") {
    return { label: daysLeft !== null ? `Válido (${daysLeft}d)` : "Válido", tone: "accent" };
  }
  return { label: "Permanente", tone: "neutral" };
}

export function formatVaultSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

export type MarkdownSegment =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string }
  | { kind: "wikilink"; label: string };

const INLINE_TOKEN_RE = /(\[\[[^[\]|]+(?:\|[^[\]]+)?\]\]|\*\*[^*]+\*\*|`[^`]+`)/g;

/** Divide uma linha de Markdown em segmentos seguros (sem HTML cru) com suporte a `[[links]]`. */
export function parseInlineMarkdown(line: string): MarkdownSegment[] {
  const out: MarkdownSegment[] = [];
  let cursor = 0;
  for (const match of line.matchAll(INLINE_TOKEN_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      out.push({ kind: "text", text: line.slice(cursor, start) });
    }
    const token = match[0];
    if (token.startsWith("[[") && token.endsWith("]]")) {
      const inner = token.slice(2, -2).split("|")[0]?.trim() ?? "";
      if (inner) out.push({ kind: "wikilink", label: inner });
    } else if (token.startsWith("**") && token.endsWith("**")) {
      out.push({ kind: "bold", text: token.slice(2, -2) });
    } else if (token.startsWith("`") && token.endsWith("`")) {
      out.push({ kind: "code", text: token.slice(1, -1) });
    }
    cursor = start + token.length;
  }
  if (cursor < line.length) {
    out.push({ kind: "text", text: line.slice(cursor) });
  }
  return out;
}

const WIKILINK_RE = /\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]/g;

/** Remove acentos e normaliza espaços para busca local e resolução de `[[links]]`. */
export function foldMemoryText(raw: string | null | undefined): string {
  return (raw ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Extrai destinos únicos de links `[[Nota]]` ou `[[Nota|Apelido]]` preservando a ordem. */
export function extractWikilinks(content: string | null | undefined): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const match of (content ?? "").matchAll(WIKILINK_RE)) {
    const label = (match[1] ?? "").replace(/\s+/g, " ").trim().slice(0, 160);
    const key = foldMemoryText(label);
    if (label && !seen.has(key)) {
      seen.add(key);
      out.push(label);
    }
  }
  return out;
}

/** Resolve quais notas citam `targetId` via `[[Título]]`, ignorando acentos e maiúsculas. */
export function buildNoteBacklinks<
  T extends { id: string; title: string; content?: string; excerpt?: string },
>(notes: readonly T[], targetId: string): { id: string; title: string }[] {
  const target = notes.find((n) => n.id === targetId);
  if (!target) return [];
  const targetKey = foldMemoryText(target.title);
  if (!targetKey) return [];
  const backlinks: { id: string; title: string }[] = [];
  for (const source of notes) {
    if (source.id === target.id) continue;
    const links = extractWikilinks(source.content ?? source.excerpt ?? "");
    if (links.some((label) => foldMemoryText(label) === targetKey)) {
      backlinks.push({ id: source.id, title: source.title });
    }
  }
  return backlinks;
}

/** Confere se a nota corresponde à busca ignorando acentos e diferenças de maiúsculas. */
export function noteMatchesQuery(
  note: {
    title: string;
    folder?: string;
    tags?: readonly string[];
    content?: string;
    excerpt?: string;
  },
  query: string,
): boolean {
  const needle = foldMemoryText(query);
  if (!needle) return true;
  const haystack = foldMemoryText(
    [note.title, note.folder ?? "", ...(note.tags ?? []), note.content ?? note.excerpt ?? ""].join(" "),
  );
  return haystack.includes(needle);
}
