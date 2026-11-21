import type { FormEvent } from "react";
import { Pin, PinOff, Trash2 } from "lucide-react";

import type { NotebookNote } from "../../api/memory";
import { parseInlineMarkdown } from "../../lib/memory";
import { Badge } from "../budget";
import { Tip } from "../help";
import { Alert, Button, LoadingRegion, Skeleton } from "../ui";

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

/** Área de edição, visualização Markdown e conexões [[...]] da nota selecionada. */
export function NotebookEditor({
  activeNote,
  selectedId,
  isLoading,
  errorText,
  previewMode,
  onPreviewModeChange,
  draftTitle,
  onDraftTitleChange,
  draftFolder,
  onDraftFolderChange,
  draftTags,
  onDraftTagsChange,
  draftContent,
  onDraftContentChange,
  saving,
  onSave,
  onTogglePin,
  onDelete,
  onFollowWikilink,
  onSelectNote,
}: {
  activeNote: NotebookNote | null;
  selectedId: string | null;
  isLoading: boolean;
  errorText: string | null;
  previewMode: "edit" | "preview";
  onPreviewModeChange: (mode: "edit" | "preview") => void;
  draftTitle: string;
  onDraftTitleChange: (value: string) => void;
  draftFolder: string;
  onDraftFolderChange: (value: string) => void;
  draftTags: string;
  onDraftTagsChange: (value: string) => void;
  draftContent: string;
  onDraftContentChange: (value: string) => void;
  saving: boolean;
  onSave: (e: FormEvent) => void;
  onTogglePin: (note: NotebookNote) => void;
  onDelete: (note: NotebookNote) => void;
  onFollowWikilink: (label: string) => void;
  onSelectNote: (id: string) => void;
}) {
  if (!activeNote) {
    if (selectedId && isLoading) {
      return (
        <section className="card stack">
          <LoadingRegion label="Carregando conteúdo da nota">
            <Skeleton height={220} />
          </LoadingRegion>
        </section>
      );
    }
    if (selectedId && errorText) {
      return (
        <section className="card">
          <Alert tone="error">{errorText}</Alert>
        </section>
      );
    }
    return (
      <section className="card">
        <p className="muted">Selecione uma nota à esquerda ou crie uma nova.</p>
      </section>
    );
  }

  return (
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
              onClick={() => onPreviewModeChange("edit")}
            >
              Editar
            </button>
            <button
              type="button"
              className={`chip-btn ${previewMode === "preview" ? "is-active" : ""}`}
              aria-pressed={previewMode === "preview"}
              onClick={() => onPreviewModeChange("preview")}
            >
              Leitura & Links
            </button>
          </div>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={() => onTogglePin(activeNote)}
            aria-label={activeNote.pinned ? "Desafixar nota" : "Fixar nota no topo"}
          >
            {activeNote.pinned ? <PinOff size={14} /> : <Pin size={14} />}
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            aria-label={`Excluir ${activeNote.title}`}
            onClick={() => onDelete(activeNote)}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {previewMode === "edit" ? (
        <form className="inline-form stack" onSubmit={onSave}>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Título da nota</span>
              <input
                value={draftTitle}
                onChange={(e) => onDraftTitleChange(e.target.value)}
                required
                maxLength={160}
              />
            </label>
            <label className="field">
              <span className="field-label">Caderno / pasta</span>
              <input
                value={draftFolder}
                onChange={(e) => onDraftFolderChange(e.target.value)}
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
              onChange={(e) => onDraftTagsChange(e.target.value)}
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
              onChange={(e) => onDraftContentChange(e.target.value)}
            />
          </div>

          <div className="form-actions">
            <Button type="submit" loading={saving}>
              Salvar nota
            </Button>
          </div>
        </form>
      ) : (
        <div className="stack">
          <h2 className="m-0">{draftTitle}</h2>
          <div className="summary-box nb-preview">
            {draftContent.split("\n").map((line, idx) => (
              <MarkdownLine key={idx} line={line} onFollowLink={onFollowWikilink} />
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
                  onClick={() => onFollowWikilink(lk.label)}
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
                  onClick={() => onSelectNote(bl.id)}
                >
                  ← {bl.title}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
