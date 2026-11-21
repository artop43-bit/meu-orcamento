import { FilePlus2 } from "lucide-react";

import type { NotebookNoteSummary } from "../../api/memory";
import { shortDate } from "../../lib/format";

/** Barra lateral com a lista de notas filtradas do Caderno. */
export function NotebookList({
  notes,
  selectedId,
  onSelect,
  onOpenTemplate,
}: {
  notes: NotebookNoteSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenTemplate: () => void;
}) {
  return (
    <aside className="card stack nb-sidebar" aria-label="Lista de notas">
      <div className="split">
        <strong>Notas ({notes.length})</strong>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={onOpenTemplate}
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
                onClick={() => onSelect(n.id)}
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
  );
}
