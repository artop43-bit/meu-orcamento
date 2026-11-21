import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpenText,
  CalendarClock,
  CalendarPlus,
  Check,
  Copy,
  Download,
  Search,
  Tag,
  UserRound,
  Wallet,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import type { MessagingChat, MessagingMessage } from "../../api/messaging";
import { notebookApi, vaultApi } from "../../api/memory";
import {
  chatPhoneLabel,
  followupStatus,
  groupMessagesByDay,
  SERVICE_STATUS_LABELS,
  serviceStatusTone,
} from "../../lib/messaging";
import { announce } from "../../lib/announce";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { Alert, Sheet } from "../ui";
import { BudgetEntrySheet } from "./BudgetEntrySheet";
import { ChatAvatar } from "./ChatAvatar";
import { copyImageUrlToClipboard, MessageBubble } from "./MessageBubble";
import { WorkActionSheet } from "./WorkActionSheet";

type ModalTrigger = { seq: number; message?: MessagingMessage } | null;

/** Cabeçalho da conversa aberta + linha do tempo das mensagens + atalhos 360°. */
export function ChatThread({
  chat,
  messages,
  loading,
  onBack,
  onOpenInfo,
  onReply,
  onFileDrop,
  onInsertDraft,
  canUseCaderno = true,
  canUseCofre = true,
}: {
  chat: MessagingChat;
  messages: MessagingMessage[];
  loading: boolean;
  onBack: () => void;
  onOpenInfo: () => void;
  onReply: (message: MessagingMessage) => void;
  onFileDrop?: (file: File) => void;
  onInsertDraft?: (text: string) => void;
  canUseCaderno?: boolean;
  canUseCofre?: boolean;
}) {
  const qc = useQueryClient();
  const endRef = useRef<HTMLDivElement>(null);
  const [zoomMedia, setZoomMedia] = useState<{ url: string; alt: string; fileName?: string | null } | null>(null);
  const [zoomCopied, setZoomCopied] = useState(false);
  const [draggingFile, setDraggingFile] = useState(false);

  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [budgetTrigger, setBudgetTrigger] = useState<ModalTrigger>(null);
  const [workModalOpen, setWorkModalOpen] = useState(false);
  const [workTrigger, setWorkTrigger] = useState<ModalTrigger>(null);
  const [scriptsOpen, setScriptsOpen] = useState(false);
  const [scriptSearch, setScriptSearch] = useState("");
  const debouncedScriptSearch = useDebouncedValue(scriptSearch, 300);
  const [loadingScriptId, setLoadingScriptId] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [bridgeBanner, setBridgeBanner] = useState<{ tone: "info" | "error"; text: string } | null>(null);

  const scriptsQuery = useQuery({
    queryKey: ["caderno", "chat-scripts", debouncedScriptSearch],
    queryFn: () => notebookApi.list({ q: debouncedScriptSearch, limit: 20 }),
    enabled: scriptsOpen,
  });

  const saveToVault = useMutation({
    mutationFn: (msg: MessagingMessage) =>
      vaultApi.archiveFromMessaging(msg.media_id!, {
        title: msg.media_name || `Arquivo · ${chat.name}`,
      }),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["cofre"] });
      setBridgeBanner({
        tone: "info",
        text: res.archived
          ? `"${res.document.title}" protegido no Cofre permanente.`
          : `"${res.document.title}" já estava guardado no Cofre.`,
      });
      announce("Mídia protegida no Cofre.");
    },
    onError: (e) => setBridgeBanner({ tone: "error", text: errorMessage(e) }),
  });

  const groups = useMemo(() => groupMessagesByDay(messages), [messages]);
  const fStatus = useMemo(() => followupStatus(chat.followup_at), [chat.followup_at]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "auto" });
  }, [chat.id, messages.length]);

  useEffect(() => {
    setZoomMedia(null);
    setZoomCopied(false);
    setBudgetModalOpen(false);
    setWorkModalOpen(false);
    setScriptsOpen(false);
    setScriptError(null);
    setLoadingScriptId(null);
    setBridgeBanner(null);
  }, [chat.id]);

  async function handleInsertScript(noteId: string, title: string) {
    if (loadingScriptId) return;
    setScriptError(null);
    setLoadingScriptId(noteId);
    try {
      const full = await notebookApi.get(noteId);
      onInsertDraft?.(full.content.trim());
      setScriptsOpen(false);
      announce(`Roteiro "${title}" inserido na caixa de mensagem.`);
    } catch (e) {
      setScriptError(errorMessage(e));
    } finally {
      setLoadingScriptId(null);
    }
  }

  function openBudgetLaunch(message?: MessagingMessage) {
    setBudgetTrigger((prev) => ({ seq: (prev?.seq ?? 0) + 1, message }));
    setBudgetModalOpen(true);
  }

  function openWorkModal(message?: MessagingMessage) {
    setWorkTrigger((prev) => ({ seq: (prev?.seq ?? 0) + 1, message }));
    setWorkModalOpen(true);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    if (e.dataTransfer?.types.includes("Files")) {
      e.preventDefault();
      if (!draggingFile) setDraggingFile(true);
    }
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    if (e.currentTarget === e.target) setDraggingFile(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    setDraggingFile(false);
    const f = e.dataTransfer?.files?.[0];
    if (f && onFileDrop) {
      e.preventDefault();
      onFileDrop(f);
    }
  }

  async function handleCopyZoomed() {
    if (!zoomMedia) return;
    const ok = await copyImageUrlToClipboard(zoomMedia.url);
    if (ok) {
      setZoomCopied(true);
      window.setTimeout(() => setZoomCopied(false), 2000);
    }
  }

  return (
    <>
      <header className="wa-thread__head">
        <button type="button" className="icon-btn wa-thread__back" onClick={onBack} aria-label="Voltar para conversas">
          <ArrowLeft size={18} aria-hidden />
        </button>
        <ChatAvatar name={chat.name} avatarUrl={chat.avatar_url} />
        <div className="wa-thread__peer">
          <div className="wa-thread__title-row">
            <strong className="wa-thread__name">{chat.name}</strong>
            {chat.service_status && chat.service_status !== "open" && (
              <span className={`badge ${serviceStatusTone(chat.service_status)}`}>
                {SERVICE_STATUS_LABELS[chat.service_status] ?? chat.service_status}
              </span>
            )}
            {fStatus && (
              <span
                className={`badge ${fStatus.tone === "overdue" ? "badge--error" : fStatus.tone === "today" ? "badge--warn" : "badge--muted"}`}
                title={chat.followup_note || fStatus.label}
              >
                <CalendarClock size={11} aria-hidden />
                {fStatus.label}
              </span>
            )}
            {(chat.tags ?? []).slice(0, 3).map((tag) => (
              <span key={tag} className="wa-tag-pill">
                <Tag size={10} aria-hidden />
                {tag}
              </span>
            ))}
          </div>
          <span className="muted small wa-thread__sub">
            {chatPhoneLabel(chat)}
            {chat.budget_person ? ` · ${chat.budget_person}` : ""}
            {chat.followup_note ? ` · ${chat.followup_note}` : ""}
          </span>
        </div>
        <div className="row row--tight">
          {onInsertDraft && canUseCaderno && (
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setScriptsOpen(true)}
              title="Puxar roteiro ou nota do Caderno para o atendimento"
            >
              <BookOpenText size={14} aria-hidden />
              <span className="wa-conn-btn__label">Roteiro</span>
            </button>
          )}
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={() => openWorkModal()}
            title="Criar tarefa em Projetos ou compromisso na Agenda"
          >
            <CalendarPlus size={14} aria-hidden />
            <span className="wa-conn-btn__label">Ação</span>
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={() => openBudgetLaunch()}
            title="Lançar receita ou despesa desta conversa no Meu Orçamento"
          >
            <Wallet size={14} aria-hidden />
            <span className="wa-conn-btn__label">Lançar</span>
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={onOpenInfo}
            aria-label="Dados do contato e CRM 360°"
            title="Etiquetas, follow-up, Funil CRM e Meu Orçamento"
          >
            <UserRound size={15} aria-hidden />
            <span className="wa-conn-btn__label">CRM 360°</span>
          </button>
        </div>
      </header>

      <div
        className={`wa-messages ${draggingFile ? "wa-messages--drop" : ""}`}
        role="log"
        aria-live="polite"
        aria-label="Mensagens da conversa"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {bridgeBanner && (
          <Alert tone={bridgeBanner.tone}>
            <div className="split">
              <span>{bridgeBanner.text}</span>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => setBridgeBanner(null)}
              >
                Fechar
              </button>
            </div>
          </Alert>
        )}
        {draggingFile && (
          <div className="wa-drop-banner" role="status">
            Solte o arquivo aqui para anexar à conversa
          </div>
        )}
        {loading ? (
          <p className="muted small wa-messages__empty">Carregando mensagens…</p>
        ) : groups.length === 0 ? (
          <p className="muted small wa-messages__empty">Nenhuma mensagem ainda.</p>
        ) : (
          groups.map((group) => (
            <div key={group.day} className="wa-day-group">
              <div className="wa-day-pill">
                <span>{group.label}</span>
              </div>
              {group.items.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onReply={onReply}
                  onZoomImage={setZoomMedia}
                  onLaunchBudget={openBudgetLaunch}
                  onWorkAction={openWorkModal}
                  canSaveToVault={canUseCofre}
                  onSaveToVault={
                    canUseCofre
                      ? (m) => {
                          if (m.media_id && !saveToVault.isPending) saveToVault.mutate(m);
                        }
                      : undefined
                  }
                />
              ))}
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>

      <Sheet open={Boolean(zoomMedia)} title={zoomMedia?.alt || "Imagem"} onClose={() => setZoomMedia(null)}>
        {zoomMedia && (
          <div className="stack">
            <img src={zoomMedia.url} alt={zoomMedia.alt} className="wa-zoom-img" />
            <div className="row row--right">
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => void handleCopyZoomed()}
              >
                {zoomCopied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
                {zoomCopied ? "Imagem copiada!" : "Copiar imagem"}
              </button>
              <a
                href={zoomMedia.url}
                download={zoomMedia.fileName ?? "imagem"}
                className="btn btn--primary btn--sm"
              >
                <Download size={15} aria-hidden />
                Baixar imagem
              </a>
            </div>
          </div>
        )}
      </Sheet>

      <BudgetEntrySheet
        chat={chat}
        trigger={budgetTrigger}
        open={budgetModalOpen}
        onClose={() => setBudgetModalOpen(false)}
      />

      <WorkActionSheet
        chat={chat}
        trigger={workTrigger}
        open={workModalOpen}
        onClose={() => setWorkModalOpen(false)}
      />

      {canUseCaderno && (
        <Sheet
          open={scriptsOpen}
          title="Roteiros & notas do Caderno"
          onClose={() => setScriptsOpen(false)}
        >
        <div className="stack">
          <label className="list-tools__search">
            <Search size={16} aria-hidden />
            <span className="sr-only">Buscar roteiro ou anotação no Caderno</span>
            <input
              type="search"
              value={scriptSearch}
              onChange={(e) => setScriptSearch(e.target.value)}
              placeholder="Buscar roteiro, POP ou anotação..."
            />
          </label>
          {scriptsQuery.isError && <Alert tone="error">{errorMessage(scriptsQuery.error)}</Alert>}
          {scriptError && <Alert tone="error">{scriptError}</Alert>}
          {!scriptsQuery.isPending && (scriptsQuery.data?.notes.length ?? 0) === 0 && (
            <p className="muted small">
              Nenhuma nota encontrada no Caderno. Crie roteiros e atas em /caderno pelo Hub.
            </p>
          )}
          <ul className="items">
            {(scriptsQuery.data?.notes ?? []).map((note) => (
              <li key={note.id} className="item">
                <span className="item__main">
                  <strong className="item__title">{note.title}</strong>
                  <span className="item__meta">
                    {note.folder} · {note.excerpt.slice(0, 90).replace(/\s+/g, " ")}
                  </span>
                </span>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  disabled={loadingScriptId !== null}
                  onClick={() => void handleInsertScript(note.id, note.title)}
                >
                  {loadingScriptId === note.id ? "Abrindo…" : "Inserir"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Sheet>
      )}
    </>
  );
}
