import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarPlus,
  CreditCard,
  Eye,
  EyeOff,
  Keyboard,
  MessageSquarePlus,
  Plus,
  Search,
  Sparkles,
  Wallet,
  Zap,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router";

import { useCategories } from "../api/budget";
import { errorMessage } from "../api/client";
import { saveQuickEntry, useCards } from "../api/extras";
import { KIND_LABEL, supportApi, type ThreadKind } from "../api/support";
import { announce } from "../lib/announce";
import { haptic } from "../lib/haptics";
import { getPrefs, togglePrivacy } from "../lib/prefs";
import { looksLikeEntry, parseQuickEntry } from "../lib/quickEntry";
import { normalizeText } from "../lib/text";
import { money } from "../lib/format";
import { RELEASE, RELEASE_NOTES } from "../release";
import { ImagePicker } from "./media";
import { Alert, Button, Sheet } from "./ui";
import { useUndo } from "./undo";

const OPEN_PALETTE = "abrir-comandos";
const OPEN_FEEDBACK = "abrir-sugestao";
const OPEN_SHORTCUTS = "abrir-atalhos";

export function openPalette() {
  window.dispatchEvent(new Event(OPEN_PALETTE));
}

export type FeedbackOptions = { kind?: "idea" | "bug" | "other"; context?: string };

/** Abre a janela de nova solicitação (opcionalmente já com o tipo e uma referência). */
export function openFeedback(options?: FeedbackOptions | unknown) {
  const detail = options && typeof options === "object" && !("nativeEvent" in options) ? (options as FeedbackOptions) : {};
  window.dispatchEvent(new CustomEvent<FeedbackOptions>(OPEN_FEEDBACK, { detail }));
}

export function openShortcuts() {
  window.dispatchEvent(new Event(OPEN_SHORTCUTS));
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
}

function useWindowEvent(name: string, fn: (event: Event) => void) {
  useEffect(() => {
    window.addEventListener(name, fn);
    return () => window.removeEventListener(name, fn);
  }, [name, fn]);
}

// ---------------------------------------------------------------- atalhos de teclado

export const SHORTCUTS: [string, string][] = [
  ["Ctrl + K", "Comandos e lançamento rápido"],
  ["N", "Nova despesa"],
  ["/", "Buscar na lista da tela"],
  ["P", "Ocultar ou exibir valores"],
  ["Ctrl + B", "Recolher ou expandir o menu lateral"],
  ["Ctrl + Z", "Desfazer a última exclusão ou alteração"],
  ["?", "Exibir a lista de atalhos"],
];

/** Atalhos globais. Letras soltas só valem fora de campos de texto. */
export function useShortcuts() {
  const navigate = useNavigate();
  const undo = useUndo();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
        return;
      }
      if (mod && e.key.toLowerCase() === "z" && !e.shiftKey && !isTyping(e.target)) {
        if (undo.undoLast()) e.preventDefault();
        return;
      }
      if (mod || e.altKey || isTyping(e.target) || document.querySelector("dialog[open]")) return;
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        navigate(`/orcamento?novo=conta`);
      } else if (e.key === "/") {
        const search = document.querySelector<HTMLInputElement>("input[type=search]");
        if (search) {
          e.preventDefault();
          search.focus();
        }
      } else if (e.key === "p" || e.key === "P") {
        const hidden = togglePrivacy();
        announce(hidden ? "Valores escondidos" : "Valores visíveis");
      } else if (e.key === "?") {
        openShortcuts();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, undo]);
}

export function ShortcutsSheet() {
  const [open, setOpen] = useState(false);
  useWindowEvent(OPEN_SHORTCUTS, () => setOpen(true));
  return (
    <Sheet open={open} title="Atalhos de teclado" onClose={() => setOpen(false)}>
      <dl className="shortcuts">
        {SHORTCUTS.map(([key, what]) => (
          <div key={key}>
            <dt>
              <kbd>{key}</kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </Sheet>
  );
}

// ---------------------------------------------------------------- busca de comandos (Ctrl+K)

type Command = { id: string; label: string; hint?: string; icon: ReactNode; keywords?: string; run: () => void | Promise<void> };

const PAGES: [string, string, string][] = [
  ["/orcamento", "Orçamento", "mes contas renda"],
  ["/calendario", "Calendário", "vencimentos agenda planejados"],
  ["/analises", "Insights", "analise consultor score graficos"],
  ["/investimentos", "Investimentos", "carteira"],
  ["/investimentos?secao=cotacoes", "Cotações", "mercado dolar bitcoin bolsa"],
  ["/contas", "Contas", "saldo banco transferencia"],
  ["/revisar", "Para revisar", "importados extrato"],
  ["/busca", "Busca", "procurar lancamentos"],
  ["/cartoes", "Cartões de crédito", "fatura limite"],
  ["/metas", "Metas", "objetivos guardar"],
  ["/historico", "Histórico", "meses anteriores"],
  ["/ajustes", "Ajustes", "configuracoes"],
  ["/ajustes/recorrencias", "Recorrências e assinaturas", "fixas"],
  ["/ajustes/categorias", "Categorias e regras", "limites"],
  ["/ajustes/dados", "Importar e exportar", "extrato ofx csv excel"],
  ["/ajustes/preferencias", "Preferências", "tema cor texto privacidade aparencia atalhos teclado teclas"],
  ["/ajustes/seguranca", "Segurança", "senha 2fa"],
  ["/ajustes/ajuda", "Central de ajuda", "como usar tour"],
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const categories = useCategories();
  const cards = useCards();
  const undo = useUndo();
  const inputRef = useRef<HTMLInputElement>(null);

  useWindowEvent(OPEN_PALETTE, () => {
    setQuery("");
    setError("");
    setActive(0);
    setOpen(true);
  });

  // A janela foca o botão de fechar ao abrir; aqui o foco vai direto para o campo.
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open]);

  function close() {
    setOpen(false);
  }

  const entry = parseQuickEntry(query);
  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => navigate(to);
    const list: Command[] = [
      { id: "nova-conta", label: "Nova despesa", icon: <Plus size={16} />, keywords: "gasto conta lancar", run: go("/orcamento?novo=conta") },
      { id: "nova-renda", label: "Nova receita", icon: <Wallet size={16} />, keywords: "salario renda", run: go("/orcamento?novo=renda") },
      { id: "planejar", label: "Agendar despesa prevista", icon: <CalendarPlus size={16} />, keywords: "futuro calendario planejar", run: go("/calendario?novo=1") },
      { id: "cartao", label: "Novo cartão de crédito", icon: <CreditCard size={16} />, run: go("/cartoes?novo=1") },
      {
        id: "privacidade",
        label: getPrefs().privacy ? "Exibir valores" : "Ocultar valores",
        hint: "P",
        icon: getPrefs().privacy ? <Eye size={16} /> : <EyeOff size={16} />,
        keywords: "privacidade ocultar",
        run: () => void togglePrivacy(),
      },
      { id: "sugestao", label: "Nova solicitação (sugestão ou problema)", icon: <MessageSquarePlus size={16} />, keywords: "feedback sugestao problema bug solicitacao", run: openFeedback },
      { id: "atalhos", label: "Atalhos de teclado", hint: "?", icon: <Keyboard size={16} />, run: openShortcuts },
      ...PAGES.map(([to, label, words]) => ({ id: to, label: `Ir para ${label}`, icon: <ArrowRight size={16} />, keywords: words, run: go(to) })),
    ];
    return list;
  }, [navigate, open]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = normalizeText(query);
  const filtered = q ? commands.filter((c) => normalizeText(`${c.label} ${c.keywords ?? ""}`).includes(q)) : commands;
  const quick: Command | null = looksLikeEntry(entry)
    ? {
        id: "lancar",
        label: `Lançar ${entry.kind === "income" ? "receita" : "despesa"}: ${entry.description} · ${money(entry.amount)}${entry.installments ? ` em ${entry.installments}x` : ""}`,
        hint: [entry.payment && { pix: "Pix", debit: "Débito", credit: "Crédito", boleto: "Boleto", cash: "Dinheiro" }[entry.payment], entry.installments && `${entry.installments}x`, entry.date && entry.date.split("-").reverse().slice(0, 2).join("/")]
          .filter(Boolean)
          .join(" · "),
        icon: <Zap size={16} />,
        run: async () => {
          setBusy(true);
          try {
            const saved = await saveQuickEntry(query, categories.data ?? [], cards.data ?? []);
            await queryClient.invalidateQueries({ queryKey: ["budget"] });
            haptic("success");
            undo.done(saved);
          } finally {
            setBusy(false);
          }
        },
      }
    : null;
  const searchCommand: Command | null =
    !quick && query.trim().length >= 2
      ? {
          id: "buscar",
          label: `Buscar lançamentos: “${query.trim()}”`,
          icon: <Search size={16} />,
          run: () => navigate(`/busca?q=${encodeURIComponent(query.trim())}`),
        }
      : null;
  const results = quick ? [quick, ...filtered] : searchCommand ? [...filtered, searchCommand] : filtered;

  async function run(command: Command | undefined) {
    if (!command) return;
    setError("");
    try {
      await command.run();
      close();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void run(results[Math.min(active, results.length - 1)]);
  }

  return (
    <Sheet open={open} title="Comandos" onClose={close}>
      <form className="palette" onSubmit={submit}>
        <label className="list-tools__search palette__input">
          <Search size={18} aria-hidden />
          <span className="sr-only">Comando ou lançamento</span>
          <input
            ref={inputRef}
            autoFocus
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              }
            }}
            placeholder="Ex.: mercado 120 pix ontem, ou o nome de uma tela"
            autoComplete="off"
          />
        </label>
        <Alert tone="error">{error}</Alert>
        <ul className="palette__list" id="palette-list" role="listbox" aria-label="Resultados">
          {results.map((c, i) => (
            <li
              key={c.id}
              id={`cmd-${c.id}`}
              role="option"
              aria-selected={i === active}
              className={`${i === active ? "is-active" : ""} ${c.id === "lancar" ? "palette__quick" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => void run(c)}
            >
              <span className="palette__icon" aria-hidden>
                {c.icon}
              </span>
              <span className="palette__label">{c.label}</span>
              {c.hint && <kbd>{c.hint}</kbd>}
            </li>
          ))}
          {results.length === 0 && <li className="muted small">Nenhum resultado. Para lançar, informe a descrição e o valor.</li>}
        </ul>
        <p className="muted small" style={{ margin: 0 }}>
          {busy ? "Salvando…" : "Enter executa · ↑↓ navegam · Esc fecha"}
        </p>
      </form>
    </Sheet>
  );
}

// ---------------------------------------------------------------- o que há de novo

const SEEN_KEY = "novidades-vistas";

export function WhatsNew() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  useEffect(() => {
    try {
      const seen = localStorage.getItem(SEEN_KEY);
      // Quem acabou de chegar (sem versão vista) vê o tour, não as novidades.
      if (seen === null) localStorage.setItem(SEEN_KEY, RELEASE.version);
      else if (seen !== RELEASE.version && !navigator.webdriver) setOpen(true);
    } catch {
      // Sem armazenamento: não mostra.
    }
  }, []);
  function close() {
    try {
      localStorage.setItem(SEEN_KEY, RELEASE.version);
    } catch {
      // ok
    }
    setOpen(false);
  }
  return (
    <Sheet open={open} title={`Novidades da versão ${RELEASE.version}`} onClose={close}>
      <div className="stack">
        <ul className="whats-new">
          {RELEASE_NOTES.map((note) => (
            <li key={note.title}>
              <Sparkles size={16} aria-hidden />
              <span>
                <strong>{note.title}</strong> {note.text}
              </span>
            </li>
          ))}
        </ul>
        <div className="form-actions">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              close();
              navigate("/ajustes/notas");
            }}
          >
            Ver todas as notas
          </Button>
          <Button type="button" onClick={close}>
            Continuar
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- sugestões e problemas

export function FeedbackSheet() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ThreadKind>("idea");
  const [message, setMessage] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [sentNumber, setSentNumber] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [context, setContext] = useState("");
  useWindowEvent(OPEN_FEEDBACK, (event) => {
    const detail = (event as CustomEvent<FeedbackOptions>).detail ?? {};
    setSent(null);
    setError("");
    if (detail.kind) setKind(detail.kind);
    setContext(detail.context ?? "");
    setOpen(true);
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const thread = await supportApi.create(
        {
          kind,
          message: context ? `${message.trim()}

(${context})` : message.trim(),
          page: location.pathname + location.search,
          app_version: RELEASE.version,
        },
        images,
      );
      setMessage("");
      setImages([]);
      setSent(thread.id);
      setSentNumber(thread.number);
      haptic("success");
      await queryClient.invalidateQueries({ queryKey: ["support"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} title="Nova solicitação" onClose={() => setOpen(false)}>
      {sent ? (
        <div className="stack">
          <Alert tone="success">
            Solicitação enviada{sentNumber ? `, com o número #${sentNumber}` : ""}. Acompanhe o andamento e a resposta da administração em Mensagens ›
            Solicitações.
          </Alert>
          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Fechar
            </Button>
            <Button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate(`/mensagens/conversas/${sent}`);
              }}
            >
              Acompanhar solicitação
            </Button>
          </div>
        </div>
      ) : (
        <form className="inline-form" onSubmit={submit}>
          <Alert tone="error">{error}</Alert>
          {context && <p className="muted small" style={{ margin: 0 }}>Referente a: {context}</p>}
          <fieldset className="radios">
            <legend className="field-label">Tema</legend>
            <div className="chips topic-chips">
              {(Object.keys(KIND_LABEL) as ThreadKind[]).map((value) => (
                <label key={value} className="chip-radio">
                  <input type="radio" name="kind" checked={kind === value} onChange={() => setKind(value)} />
                  {KIND_LABEL[value]}
                </label>
              ))}
            </div>
          </fieldset>
          <label>
            Mensagem
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={5}
              maxLength={1000}
              required
              placeholder={
                kind === "bug"
                  ? "O que você fez, o que esperava e o que aconteceu."
                  : kind === "question"
                    ? "Qual é a sua dúvida?"
                    : kind === "praise"
                      ? "O que você mais gostou?"
                      : "Conte a sua ideia ou o que você gostaria de ver no app."
              }
            />
            <small className={`muted ${message.length >= 950 ? "tone--warn" : ""}`} aria-live="polite" style={{ alignSelf: "flex-end" }}>
              {message.length} / 1000
            </small>
          </label>
          <ImagePicker files={images} onChange={setImages} />
          <p className="muted small" style={{ margin: 0 }}>
            São enviados também a tela atual ({location.pathname}) e a versão {RELEASE.version}. Nenhum valor financeiro é incluído.
          </p>
          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={busy}>
              Enviar solicitação
            </Button>
          </div>
        </form>
      )}
    </Sheet>
  );
}

/** Tudo o que é global: atalhos, Ctrl+K, novidades, sugestões. Fica dentro do Shell. */
export function PowerLayer() {
  useShortcuts();
  return (
    <>
      <CommandPalette />
      <ShortcutsSheet />
      <WhatsNew />
      <FeedbackSheet />
    </>
  );
}

