import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenText,
  FilePlus2,
  Link2,
  Pin,
  PinOff,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  notebookApi,
  useNotebookBridges,
  useNotebookNote,
  useNotebookNotes,
  useNotebookTemplates,
  type NotebookNote,
  type NoteTemplateKind,
} from "../../api/memory";
import { Badge } from "../../components/budget";
import { EmptyGuide, Tip } from "../../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { announce } from "../../lib/announce";
import { formatDateHeading, shortDate } from "../../lib/format";
import { parseInlineMarkdown } from "../../lib/memory";

function MarkdownLine({
  line,
  onFollowLink,
}: {
  line: string;
  onFollowLink: (label: string) => void;
}) {
  const trimmed = line.trim();
  if (!trimmed) return <br />;
  const isH1 = trimmed.startsWith("# ");
  const isH2 = trimmed.startsWith("## ");
  const body = isH1 ? trimmed.slice(2) : isH2 ? trimmed.slice(3) : trimmed;
  const segs = parseInlineMarkdown(body);
  const content = segs.map((seg, i) => {
    if (seg.kind === "bold") return <strong key={i}>{seg.text}</strong>;
    if (seg.kind === "code") return <code key={i}>{seg.text}</code>;
    if (seg.kind === "wikilink") {
      return (
        <button
          key={i}
          type="button"
          className="nb-wikilink"
          onClick={() => onFollowLink(seg.label)}
        >
          [[{seg.label}]]
        </button>
      );
    }
    return <span key={i}>{seg.text}</span>;
  });

  if (isH1) return <h3 className="nb-md__h1">{content}</h3>;
  if (isH2) return <h4 className="nb-md__h2">{content}</h4>;
  return <p className="nb-md__p">{content}</p>;
}

export default function NotebookPage() {
  const qc = useQueryClient();
  const undo = useUndo();
  const [search, setSearch] = useState("");
  const [folderFilter, setFolderFilter] = useState("all");
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  // Estado do formulário do editor da nota selecionada
  const [draftTitle, setDraftTitle] = useState("");
  const [draftFolder, setDraftFolder] = useState("Geral");
  const [draftTags, setDraftTags] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [previewMode, setPreviewMode] = useState<"edit" | "preview">("edit");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // Estado do modal Nova Nota
  const [tplKind, setTplKind] = useState<NoteTemplateKind>("blank");
  const [newTitle, setNewTitle] = useState("");
  const [newFolder, setNewFolder] = useState("Geral");
  const [newContactId, setNewContactId] = useState("");
  const [newProjectId, setNewProjectId] = useState("");

  const notesQuery = useNotebookNotes(search, folderFilter, pinnedOnly, 50);
  const templatesQuery = useNotebookTemplates();
  const bridges = useNotebookBridges(newOpen).data;

  const notes = useMemo(
    () => (notesQuery.data?.notes ?? []).filter((n) => !undo.isHidden(n.id)),
    [notesQuery.data, undo],
  );
  const summary = notesQuery.data?.summary;

  useEffect(() => {
    if (!selectedId && notes.length > 0) {
      setSelectedId(notes[0]!.id);
    } else if (selectedId && notes.length > 0 && !notes.some((n) => n.id === selectedId)) {
      setSelectedId(notes[0]!.id);
    } else if (notes.length === 0) {
      setSelectedId(null);
    }
  }, [notes, selectedId]);

  const activeNoteQuery = useNotebookNote(selectedId);
  const activeNote: NotebookNote | null = useMemo(() => {
    if (!selectedId || activeNoteQuery.data?.id !== selectedId) return null;
    return activeNoteQuery.data;
  }, [activeNoteQuery.data, selectedId]);

  const syncedNoteIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId) {
      syncedNoteIdRef.current = null;
      return;
    }
    if (!activeNote || syncedNoteIdRef.current === activeNote.id) return;
    syncedNoteIdRef.current = activeNote.id;
    setDraftTitle(activeNote.title);
    setDraftFolder(activeNote.folder);
    setDraftTags(activeNote.tags.join(", "));
    setDraftContent(activeNote.content);
  }, [selectedId, activeNote]);

  function invalidateAll() {
    void qc.invalidateQueries({ queryKey: ["caderno"] });
  }

  const createNote = useMutation({
    mutationFn: (payload: Parameters<typeof notebookApi.create>[0]) => notebookApi.create(payload),
    onSuccess: (created) => {
      setNewOpen(false);
      setFolderFilter("all");
      setPinnedOnly(false);
      setSearch("");
      qc.setQueryData(["caderno", "note", created.id], created);
      syncedNoteIdRef.current = null;
      setSelectedId(created.id);
      invalidateAll();
      setFeedback(`Nota "${created.title}" criada.`);
      announce("Nota criada no Caderno");
    },
    onError: (e) => setErrMsg(errorMessage(e)),
  });

  const saveNote = useMutation({
    mutationFn: (e: FormEvent) => {
      e.preventDefault();
      if (!activeNote) return Promise.resolve(null);
      return notebookApi.update(activeNote.id, {
        title: draftTitle.trim() || activeNote.title,
        folder: draftFolder.trim() || "Geral",
        tags: draftTags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        content: draftContent,
      });
    },
    onSuccess: (updated) => {
      if (!updated) return;
      qc.setQueryData(["caderno", "note", updated.id], updated);
      invalidateAll();
      setErrMsg(null);
      setFeedback(`"${updated.title}" salva com links atualizados.`);
      announce("Nota salva");
    },
    onError: (e) => setErrMsg(errorMessage(e)),
  });

  const togglePin = useMutation({
    mutationFn: (note: NotebookNote) => notebookApi.update(note.id, { pinned: !note.pinned }),
    onSuccess: (updated) => {
      qc.setQueryData(["caderno", "note", updated.id], updated);
      invalidateAll();
    },
  });

  function deleteNoteWithUndo(note: NotebookNote) {
    undo.remove({
      ids: [note.id],
      message: `Nota "${note.title}" excluída`,
      commit: async () => {
        await notebookApi.delete(note.id);
        setSelectedId((prev) => (prev === note.id ? null : prev));
        invalidateAll();
      },
    });
  }

  function handleFollowWikilink(label: string) {
    const linkedTargetId = activeNote?.links.find(
      (lk) => lk.label.trim().toLowerCase() === label.trim().toLowerCase(),
    )?.target_id;
    if (linkedTargetId) {
      setSelectedId(linkedTargetId);
      return;
    }
    const existing = notes.find(
      (n) => n.title.trim().toLowerCase() === label.trim().toLowerCase(),
    );
    if (existing) {
      setSelectedId(existing.id);
      return;
    }
    createNote.mutate({
      title: label,
      folder: draftFolder || "Geral",
      template_kind: "blank",
      content: `# ${label}\n\nCriada a partir do link em [[${draftTitle || "outra nota"}]].\n`,
    });
  }

  function openNewModal(defaultKind: NoteTemplateKind = "blank") {
    const tpl = (templatesQuery.data ?? []).find((t) => t.id === defaultKind);
    setTplKind(defaultKind);
    setNewTitle(tpl?.title ?? "");
    setNewFolder(tpl?.folder ?? "Geral");
    setNewContactId("");
    setNewProjectId("");
    setErrMsg(null);
    setNewOpen(true);
  }

  function submitNewNote(e: FormEvent) {
    e.preventDefault();
    createNote.mutate({
      title: newTitle.trim() || undefined,
      folder: newFolder.trim() || undefined,
      template_kind: tplKind,
      contact_id: newContactId || null,
      project_id: newProjectId || null,
    });
  }

  const folders = summary?.folders ?? [];

  return (
    <div className="stack">
      <PageHeader
        title="Caderno & Conhecimento"
        subtitle="Notas em Markdown, links [[...]] entre ideias, roteiros de atendimento e busca BM25 100% local."
        actions={
          <Button type="button" onClick={() => openNewModal("blank")}>
            <Plus size={16} /> Nova nota
          </Button>
        }
      />

      {errMsg && <Alert tone="error">{errMsg}</Alert>}
      {feedback && (
        <Alert tone="info">
          <div className="split">
            <span>{feedback}</span>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setFeedback(null)}
            >
              Fechar
            </button>
          </div>
        </Alert>
      )}

      {summary && (
        <>
          <div className="greeting">
            <span className="greeting__date">{formatDateHeading()}</span>
            <p className="greeting__hello">
              {summary.total_notes === 0
                ? "Comece seu caderno com atas, POPs e roteiros para o WhatsApp."
                : `Você organiza ${summary.total_notes} nota(s) em ${Math.max(folders.length, 1)} caderno(s).`}
            </p>
            <p className="greeting__text">
              Conecte assuntos digitando{" "}
              <code style={{ whiteSpace: "nowrap" }}>[[Nome da nota]]</code> — também fica acessível rápido dentro da Mensageria.
            </p>
          </div>

          <section className="card month-summary" aria-label="Resumo do Caderno">
            <div className="month-summary__main">
              <span className="month-summary__label">
                <BookOpenText size={15} aria-hidden /> Base de notas
              </span>
              <strong className="month-summary__value tone--ok">{summary.total_notes}</strong>
              <span className="muted small">
                {summary.pinned_count} fixada(s) no topo · ordenadas por relevância BM25 na busca
              </span>
            </div>
            <div className="month-summary__side">
              <dl className="month-summary__grid">
                <div>
                  <dt>
                    <Link2 size={14} aria-hidden /> Conexões
                  </dt>
                  <dd className="month-summary__num">{summary.total_links}</dd>
                  <dd className="month-summary__foot">Referências [[...]]</dd>
                </div>
                <div>
                  <dt>Cadernos</dt>
                  <dd className="month-summary__num">{folders.length}</dd>
                  <dd className="month-summary__foot">Pastas temáticas</dd>
                </div>
                <div>
                  <dt>Fixadas</dt>
                  <dd className="month-summary__num">{summary.pinned_count}</dd>
                  <dd className="month-summary__foot">Acesso rápido</dd>
                </div>
              </dl>
            </div>
          </section>
        </>
      )}

      {notesQuery.isPending && (
        <LoadingRegion label="Carregando notas do Caderno">
          <Skeleton height={180} />
        </LoadingRegion>
      )}
      {notesQuery.isError && <Alert tone="error">{errorMessage(notesQuery.error)}</Alert>}

      {!notesQuery.isPending && summary && summary.total_notes === 0 && !search ? (
        <section className="card stack">
          <EmptyGuide
            icon={<BookOpenText size={22} />}
            title="Nenhuma anotação criada ainda"
            text="Crie atas de reunião, procedimentos operacionais (POP) e roteiros comerciais de WhatsApp que você pode copiar direto no chat ou ligar a clientes e projetos."
            example={<>Ex.: “Roteiro · Primeiro contato” com [[Checklist Pós-Venda]] ligado.</>}
            action={
              <Button type="button" onClick={() => openNewModal("sales_script")}>
                <Sparkles size={16} /> Criar com modelo de Roteiro WhatsApp
              </Button>
            }
          />
        </section>
      ) : (
        <>
          <div
            className="list-tools list-tools--pills person-tools"
            role="search"
            aria-label="Buscar no Caderno"
          >
            <label className="list-tools__search">
              <Search size={16} aria-hidden />
              <span className="sr-only">Buscar notas por título, etiqueta ou texto</span>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar no Caderno (título, #etiqueta ou conteúdo)..."
              />
            </label>
            <span className="pill-group" role="group" aria-label="Filtrar por caderno">
              <button
                type="button"
                className="chip-btn"
                aria-pressed={folderFilter === "all" && !pinnedOnly}
                onClick={() => {
                  setFolderFilter("all");
                  setPinnedOnly(false);
                }}
              >
                Todas ({summary?.total_notes ?? notes.length})
              </button>
              <button
                type="button"
                className="chip-btn"
                aria-pressed={pinnedOnly}
                onClick={() => setPinnedOnly((p) => !p)}
              >
                Fixadas ({summary?.pinned_count ?? 0})
              </button>
              {folders.map((f) => (
                <button
                  key={f}
                  type="button"
                  className="chip-btn"
                  aria-pressed={folderFilter === f}
                  onClick={() => setFolderFilter(folderFilter === f ? "all" : f)}
                >
                  {f}
                </button>
              ))}
            </span>
          </div>

          <div className="notebook-grid">
            <aside className="card stack nb-sidebar" aria-label="Lista de notas">
              <div className="split">
                <strong>Notas ({notes.length})</strong>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => openNewModal("meeting")}
                >
                  <FilePlus2 size={14} /> Modelo
                </button>
              </div>
              {notes.length === 0 ? (
                <p className="muted small">Nenhuma nota corresponde a essa busca.</p>
              ) : (
                <ul className="items">
                  {notes.map((n) => (
                    <li
                      key={n.id}
                      className={`item nb-note-item ${selectedId === n.id ? "is-selected" : ""}`}
                    >
                      <button
                        type="button"
                        className="nb-note-pick"
                        onClick={() => setSelectedId(n.id)}
                        aria-current={selectedId === n.id ? "true" : undefined}
                      >
                        <span className="item__main">
                          <strong className="item__title">
                            {n.pinned ? "📌 " : ""}
                            {n.title}
                          </strong>
                          <span className="item__meta">
                            {n.folder} · {shortDate(n.updated_at.slice(0, 10))}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </aside>

            {activeNote ? (
              <section className="card stack" aria-label={`Editor da nota ${activeNote.title}`}>
                <div className="split">
                  <div className="row row--tight">
                    <Badge tone="accent">{activeNote.folder}</Badge>
                    {activeNote.tags.map((t) => (
                      <Badge key={t} tone="neutral">
                        #{t}
                      </Badge>
                    ))}
                  </div>
                  <div className="row row--tight">
                    <div className="segmented" role="group" aria-label="Modo de exibição">
                      <button
                        type="button"
                        className={`chip-btn ${previewMode === "edit" ? "is-active" : ""}`}
                        aria-pressed={previewMode === "edit"}
                        onClick={() => setPreviewMode("edit")}
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        className={`chip-btn ${previewMode === "preview" ? "is-active" : ""}`}
                        aria-pressed={previewMode === "preview"}
                        onClick={() => setPreviewMode("preview")}
                      >
                        Leitura & Links
                      </button>
                    </div>
                    <button
                      type="button"
                      className="btn btn--secondary btn--sm"
                      onClick={() => togglePin.mutate(activeNote)}
                      aria-label={activeNote.pinned ? "Desafixar nota" : "Fixar nota no topo"}
                    >
                      {activeNote.pinned ? <PinOff size={14} /> : <Pin size={14} />}
                    </button>
                    <button
                      type="button"
                      className="btn btn--secondary btn--sm"
                      aria-label={`Excluir ${activeNote.title}`}
                      onClick={() => deleteNoteWithUndo(activeNote)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {previewMode === "edit" ? (
                  <form className="inline-form stack" onSubmit={(e) => saveNote.mutate(e)}>
                    <div className="grid-2">
                      <label className="field">
                        <span className="field-label">Título da nota</span>
                        <input
                          value={draftTitle}
                          onChange={(e) => setDraftTitle(e.target.value)}
                          required
                          maxLength={160}
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">Caderno / pasta</span>
                        <input
                          value={draftFolder}
                          onChange={(e) => setDraftFolder(e.target.value)}
                          maxLength={60}
                        />
                      </label>
                    </div>

                    <label className="field">
                      <span className="field-label">
                        Etiquetas (separadas por vírgula){" "}
                        <Tip>Pesquisadas junto no ranking BM25 do Caderno.</Tip>
                      </span>
                      <input
                        value={draftTags}
                        onChange={(e) => setDraftTags(e.target.value)}
                        placeholder="Ex.: whatsapp, vendas, checklist"
                      />
                    </label>

                    <div className="field">
                      <label htmlFor="nb-editor-body" className="field-label">
                        Conteúdo em Markdown (use [[Nome de outra nota]] para ligar ideias)
                      </label>
                      <textarea
                        id="nb-editor-body"
                        rows={11}
                        value={draftContent}
                        onChange={(e) => setDraftContent(e.target.value)}
                      />
                    </div>

                    <div className="form-actions">
                      <Button type="submit" loading={saveNote.isPending}>
                        Salvar nota
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="stack">
                    <h2 className="m-0">{draftTitle}</h2>
                    <div className="summary-box nb-preview">
                      {draftContent.split("\n").map((line, idx) => (
                        <MarkdownLine key={idx} line={line} onFollowLink={handleFollowWikilink} />
                      ))}
                    </div>
                  </div>
                )}

                {(activeNote.links.length > 0 || activeNote.backlinks.length > 0) && (
                  <div className="summary-box stack--compact">
                    {activeNote.links.length > 0 && (
                      <div className="row row--tight">
                        <span className="muted small">Links [[…]]:</span>
                        {activeNote.links.map((lk) => (
                          <button
                            key={lk.label}
                            type="button"
                            className="chip-btn"
                            onClick={() => handleFollowWikilink(lk.label)}
                          >
                            {lk.target_id ? `↗ ${lk.target_title}` : `+ Criar "${lk.label}"`}
                          </button>
                        ))}
                      </div>
                    )}
                    {activeNote.backlinks.length > 0 && (
                      <div className="row row--tight">
                        <span className="muted small">Citada por:</span>
                        {activeNote.backlinks.map((bl) => (
                          <button
                            key={bl.id}
                            type="button"
                            className="chip-btn"
                            onClick={() => setSelectedId(bl.id)}
                          >
                            ← {bl.title}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </section>
            ) : selectedId && activeNoteQuery.isPending ? (
              <section className="card stack">
                <LoadingRegion label="Carregando conteúdo da nota">
                  <Skeleton height={220} />
                </LoadingRegion>
              </section>
            ) : selectedId && activeNoteQuery.isError ? (
              <section className="card">
                <Alert tone="error">{errorMessage(activeNoteQuery.error)}</Alert>
              </section>
            ) : (
              <section className="card">
                <p className="muted">Selecione uma nota à esquerda ou crie uma nova.</p>
              </section>
            )}
          </div>
        </>
      )}

      <Sheet open={newOpen} title="Nova nota no Caderno" onClose={() => setNewOpen(false)}>
        <form className="inline-form stack" onSubmit={submitNewNote}>
          <label className="field">
            <span className="field-label">Modelo inicial</span>
            <select
              value={tplKind}
              onChange={(e) => {
                const k = e.target.value as NoteTemplateKind;
                setTplKind(k);
                const found = (templatesQuery.data ?? []).find((t) => t.id === k);
                if (found) {
                  setNewTitle(found.title);
                  setNewFolder(found.folder);
                }
              }}
            >
              {(templatesQuery.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid-2">
            <label className="field">
              <span className="field-label">Título</span>
              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Ex.: Roteiro de fechamento"
                maxLength={160}
              />
            </label>
            <label className="field">
              <span className="field-label">Caderno / pasta</span>
              <input
                value={newFolder}
                onChange={(e) => setNewFolder(e.target.value)}
                placeholder="Geral"
                maxLength={60}
              />
            </label>
          </div>

          <div className="grid-2">
            <label className="field">
              <span className="field-label">Contato CRM (opcional)</span>
              <select value={newContactId} onChange={(e) => setNewContactId(e.target.value)}>
                <option value="">Sem vínculo</option>
                {(bridges?.contacts ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Projeto (opcional)</span>
              <select value={newProjectId} onChange={(e) => setNewProjectId(e.target.value)}>
                <option value="">Sem vínculo</option>
                {(bridges?.projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => setNewOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={createNote.isPending}>
              Criar nota
            </Button>
          </div>
        </form>
      </Sheet>
    </div>
  );
}
