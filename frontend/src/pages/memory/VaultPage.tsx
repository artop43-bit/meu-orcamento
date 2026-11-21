import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  Download,
  ExternalLink,
  FileSearch,
  Pencil,
  Plus,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  useVaultBridges,
  useVaultDocuments,
  vaultApi,
  type VaultCategory,
  type VaultDocument,
  type VaultExpiryStatus,
} from "../../api/memory";
import { Badge, Bar, Stat } from "../../components/budget";
import { DateField } from "../../components/DateField";
import { EmptyGuide } from "../../components/help";
import { VaultUploadSheet } from "../../components/memory/VaultUploadSheet";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { announce } from "../../lib/announce";
import { formatDateHeading } from "../../lib/format";
import {
  EXPIRY_FILTER_LABELS,
  expiryBadgeInfo,
  formatVaultSize,
  VAULT_CATEGORY_OPTIONS,
} from "../../lib/memory";
import { formatIsoDateBr } from "../../lib/work";

const EXPIRY_FILTERS: ("all" | VaultExpiryStatus)[] = [
  "all",
  "expiring_soon",
  "expired",
  "valid",
  "no_expiry",
];

export default function VaultPage() {
  const qc = useQueryClient();
  const undo = useUndo();
  const [search, setSearch] = useState("");
  const [expiryFilter, setExpiryFilter] = useState<"all" | VaultExpiryStatus>("all");
  const [categoryFilter, setCategoryFilter] = useState<"all" | VaultCategory>("all");
  const [openedIds, setOpenedIds] = useState<Set<string> | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editingDoc, setEditingDoc] = useState<VaultDocument | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editExpires, setEditExpires] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const listQuery = useVaultDocuments(search, categoryFilter, "all");
  const bridges = useVaultBridges(uploadOpen).data;

  const allFetched = (listQuery.data?.documents ?? []).filter((d) => !undo.isHidden(d.id));
  const shown = allFetched.filter((d) => expiryFilter === "all" || d.expiry_status === expiryFilter);
  const summary = listQuery.data?.summary;

  const firstId = shown[0]?.id;
  useEffect(() => {
    if (openedIds === null && firstId) {
      setOpenedIds(new Set([firstId]));
    }
  }, [openedIds, firstId]);

  const open = openedIds ?? new Set(firstId ? [firstId] : []);

  function toggleRow(id: string) {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpenedIds(next);
  }

  function invalidateAll() {
    void qc.invalidateQueries({ queryKey: ["cofre"] });
    void qc.invalidateQueries({ queryKey: ["agenda"] });
    void qc.invalidateQueries({ queryKey: ["caderno", "bridges"] });
  }

  function openEdit(doc: VaultDocument) {
    setEditingDoc(doc);
    setEditTitle(doc.title);
    setEditExpires(doc.expires_at ?? "");
    setEditNotes(doc.notes ?? "");
    setErrMsg(null);
  }

  const saveEdit = useMutation({
    mutationFn: (e: FormEvent) => {
      e.preventDefault();
      if (!editingDoc) return Promise.resolve(null);
      return vaultApi.update(editingDoc.id, {
        title: editTitle.trim(),
        expires_at: editExpires || null,
        notes: editNotes.trim() || null,
      });
    },
    onSuccess: (updated) => {
      if (!updated) return;
      setEditingDoc(null);
      invalidateAll();
      setFeedback(`"${updated.title}" atualizado no Cofre.`);
      announce("Documento atualizado");
    },
    onError: (e) => setErrMsg(errorMessage(e)),
  });

  function deleteDocWithUndo(doc: VaultDocument) {
    undo.remove({
      ids: [doc.id],
      message: `${doc.title} excluído do Cofre`,
      commit: async () => {
        await vaultApi.delete(doc.id);
        invalidateAll();
      },
    });
  }

  const allOpen = shown.length > 0 && shown.every((d) => open.has(d.id));
  const quotaBytes = (summary?.quota_mb ?? 200) * 1024 * 1024;
  const usedPct =
    summary && quotaBytes > 0
      ? Math.min(100, Math.round((summary.account_used_bytes / quotaBytes) * 100))
      : 0;

  return (
    <div className="stack">
      <PageHeader
        title="Cofre & Garantias"
        subtitle="Arquivo permanente para notas fiscais, contratos, garantias e comprovantes, com busca dentro do texto (OCR local)."
        actions={
          <Button type="button" onClick={() => setUploadOpen(true)}>
            <Plus size={16} /> Guardar documento
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
              {summary.total_docs === 0
                ? "Seu Cofre está pronto para proteger documentos importantes."
                : `Você mantém ${summary.total_docs} documento(s) protegidos neste arquivo permanente.`}
            </p>
            <p className="greeting__text">
              {summary.expired_count > 0 || summary.expiring_count > 0
                ? `Atenção: ${summary.expiring_count} vencendo em breve e ${summary.expired_count} já vencido(s).`
                : "Todas as garantias e validades acompanhadas estão em dia."}
            </p>
          </div>

          <section className="card month-summary" aria-label="Resumo do Cofre e cota">
            <div className="month-summary__main">
              <span className="month-summary__label">
                <ShieldCheck size={15} aria-hidden /> Uso da cota da conta
              </span>
              <strong className="month-summary__value tone--ok">
                {formatVaultSize(summary.account_used_bytes)}
              </strong>
              <span className="muted small">
                de {summary.quota_mb} MB liberados ({formatVaultSize(summary.vault_bytes)} só no Cofre)
              </span>
            </div>
            <div className="month-summary__side">
              <dl className="month-summary__grid">
                <div>
                  <dt>
                    <ShieldAlert size={14} aria-hidden /> Alertas
                  </dt>
                  <dd className="month-summary__num">
                    {summary.expiring_count + summary.expired_count}
                  </dd>
                  <dd className="month-summary__foot">
                    {summary.expiring_count} a vencer · {summary.expired_count} vencido(s)
                  </dd>
                </div>
                <div>
                  <dt>
                    <FileSearch size={14} aria-hidden /> Busca OCR
                  </dt>
                  <dd className="month-summary__num">{summary.ocr_indexed_count}</dd>
                  <dd className="month-summary__foot">Com texto lido localmente</dd>
                </div>
                <div>
                  <dt>Permanentes</dt>
                  <dd className="month-summary__num">{summary.no_expiry_count}</dd>
                  <dd className="month-summary__foot">Sem data de validade</dd>
                </div>
              </dl>
              <div
                className={`month-summary__bar ${usedPct >= 85 ? "is-high" : ""}`}
                role="img"
                aria-label={`${usedPct}% da cota de armazenamento utilizada`}
              >
                <span style={{ width: `${usedPct}%` }} />
              </div>
            </div>
          </section>
        </>
      )}

      {listQuery.isPending && (
        <LoadingRegion label="Carregando documentos do Cofre">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {listQuery.isError && <Alert tone="error">{errorMessage(listQuery.error)}</Alert>}

      {!listQuery.isPending && summary && summary.total_docs === 0 ? (
        <section className="card">
          <EmptyGuide
            icon={<ShieldCheck size={22} />}
            title="Seu Cofre ainda está vazio"
            text="Suba notas fiscais, garantias, contratos assinados ou certificados em PDF e imagem. O sistema lê o texto localmente para você achar qualquer papel depois, e avisa dos vencimentos na Agenda."
            example={
              <>
                Ex.: “Garantia Geladeira” até 15/11/2027 (ao buscar “FrostFree” no campo acima o PDF já aparece).
              </>
            }
            action={
              <Button type="button" onClick={() => setUploadOpen(true)}>
                <Plus size={16} /> Guardar primeiro documento
              </Button>
            }
          />
        </section>
      ) : (
        <>
          <div
            className="list-tools list-tools--pills person-tools"
            role="search"
            aria-label="Filtrar documentos do Cofre"
          >
            <label className="list-tools__search">
              <Search size={16} aria-hidden />
              <span className="sr-only">Buscar no título ou no texto extraído do documento</span>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar título, nº, emissor ou texto dentro do PDF..."
              />
            </label>
            <select
              aria-label="Filtrar por categoria"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as "all" | VaultCategory)}
            >
              <option value="all">Todas as categorias</option>
              {VAULT_CATEGORY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            <span className="pill-group" role="group" aria-label="Status de validade">
              {EXPIRY_FILTERS.map((key) => {
                const count =
                  key === "all"
                    ? allFetched.length
                    : allFetched.filter((d) => d.expiry_status === key).length;
                return (
                  <button
                    key={key}
                    type="button"
                    className="chip-btn"
                    aria-pressed={expiryFilter === key}
                    onClick={() => setExpiryFilter(key)}
                  >
                    {EXPIRY_FILTER_LABELS[key]} ({count})
                  </button>
                );
              })}
            </span>
            <button
              type="button"
              className="chip-btn person-tools__all"
              aria-pressed={allOpen}
              onClick={() =>
                setOpenedIds(allOpen ? new Set() : new Set(shown.map((d) => d.id)))
              }
            >
              {allOpen ? "Fechar todos" : "Abrir todos"}
            </button>
          </div>

          {shown.length === 0 ? (
            <p className="muted">Nenhum documento encontrado com esse filtro.</p>
          ) : (
            <div className="person-rows">
              {shown.map((doc) => {
                const isOpen = open.has(doc.id);
                const badge = expiryBadgeInfo(doc.expiry_status, doc.days_left);
                const pctBar =
                  doc.expiry_status === "expired"
                    ? 100
                    : doc.expiry_status === "expiring_soon"
                      ? 75
                      : doc.expiry_status === "valid"
                        ? 35
                        : 15;
                return (
                  <article
                    key={doc.id}
                    className={`card person-row ${isOpen ? "is-open" : ""}`}
                    data-vault-row={doc.id}
                  >
                    <button
                      type="button"
                      className="person-row__head"
                      aria-expanded={isOpen}
                      onClick={() => toggleRow(doc.id)}
                    >
                      <span className="person-row__avatar" aria-hidden>
                        <ShieldCheck size={18} />
                      </span>
                      <span className="person-row__who">
                        <strong>{doc.title}</strong>
                        <span className="muted small">
                          {doc.category_label}
                          {doc.issuer ? ` · ${doc.issuer}` : ""}
                          {doc.document_number ? ` · ${doc.document_number}` : ""}
                        </span>
                      </span>
                      <span className="person-row__progress">
                        <span className="person-row__bar">
                          <Bar
                            pct={pctBar}
                            color={badge.tone === "warn" ? "var(--warn)" : undefined}
                          />
                        </span>
                        <span className="muted small">
                          {doc.expires_at ? `Até ${formatIsoDateBr(doc.expires_at)}` : "Sem vencimento"}
                        </span>
                      </span>
                      <span className="person-row__balance">
                        <strong className={badge.tone === "warn" ? "tone--error" : "tone--ok"}>
                          {badge.label}
                        </strong>
                      </span>
                      <span className="person-row__chev" aria-hidden>
                        <ChevronDown size={18} />
                      </span>
                    </button>

                    {isOpen && (
                      <div className="person-row__body">
                        <div className="row">
                          <Badge tone={badge.tone}>{badge.label}</Badge>
                          <Badge tone="neutral">{doc.category_label}</Badge>
                          {doc.has_extracted_text && (
                            <Badge tone="accent">
                              {doc.ocr_used ? "Texto lido por OCR" : "Texto indexado"}
                            </Badge>
                          )}
                          {doc.messaging_media_id && (
                            <Badge tone="neutral">Salvo do WhatsApp</Badge>
                          )}
                          {doc.proposal_id && <Badge tone="neutral">Cópia de Proposta PDF</Badge>}
                        </div>

                        <div className="stats">
                          <Stat label="Arquivo" value={doc.file_name} />
                          <Stat label="Tamanho" value={formatVaultSize(doc.size_bytes)} />
                          <Stat
                            label="Emissão"
                            value={doc.issue_date ? formatIsoDateBr(doc.issue_date) : "—"}
                          />
                          <Stat
                            label="Validade"
                            value={doc.expires_at ? formatIsoDateBr(doc.expires_at) : "Permanente"}
                          />
                        </div>

                        {doc.extracted_preview && (
                          <div className="summary-box">
                            <span className="small muted">Trecho indexado para busca local:</span>
                            <p className="small m-0 mt-1">{doc.extracted_preview}</p>
                          </div>
                        )}

                        {doc.notes && <p className="muted small">{doc.notes}</p>}

                        <div className="person-row__actions">
                          <a
                            href={`${doc.file_url}?inline=true`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn--secondary btn--sm"
                          >
                            <ExternalLink size={14} /> Visualizar
                          </a>
                          <a
                            href={doc.file_url}
                            download={doc.file_name}
                            className="btn btn--secondary btn--sm"
                          >
                            <Download size={14} /> Baixar
                          </a>
                          <button
                            type="button"
                            className="btn btn--secondary btn--sm"
                            onClick={() => openEdit(doc)}
                          >
                            <Pencil size={14} /> Editar validade
                          </button>
                          <button
                            type="button"
                            className="btn btn--secondary btn--sm"
                            aria-label={`Excluir ${doc.title}`}
                            onClick={() => deleteDocWithUndo(doc)}
                          >
                            <Trash2 size={14} /> Excluir
                          </button>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}

      <VaultUploadSheet
        open={uploadOpen}
        bridges={bridges}
        onClose={() => setUploadOpen(false)}
        onCreated={(doc) => {
          setOpenedIds((prev) => new Set([doc.id, ...(prev ?? [])]));
          invalidateAll();
          setFeedback(
            doc.warning
              ? `"${doc.title}" guardado no Cofre. ${doc.warning}`
              : `"${doc.title}" guardado no Cofre permanente.`,
          );
        }}
      />

      <Sheet
        open={Boolean(editingDoc)}
        title={`Editar · ${editingDoc?.title ?? ""}`}
        onClose={() => setEditingDoc(null)}
      >
        {editingDoc && (
          <form className="inline-form stack" onSubmit={(e) => saveEdit.mutate(e)}>
            <label className="field">
              <span className="field-label">Título</span>
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                required
                maxLength={160}
              />
            </label>
            <label className="field">
              <span className="field-label">Data de validade</span>
              <DateField value={editExpires} onChange={setEditExpires} label="Data de validade" />
            </label>
            <div className="field">
              <label htmlFor="vault-edit-notes" className="field-label">
                Observações
              </label>
              <textarea
                id="vault-edit-notes"
                rows={3}
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
              />
            </div>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => setEditingDoc(null)}>
                Cancelar
              </Button>
              <Button type="submit" loading={saveEdit.isPending}>
                Salvar alterações
              </Button>
            </div>
          </form>
        )}
      </Sheet>
    </div>
  );
}
