import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  Download,
  FileCheck2,
  FileText,
  FolderKanban,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  downloadProposalPdf,
  proposalsApi,
  useProposalBridges,
  useProposals,
  type CommercialDocType,
  type CommercialDocument,
} from "../../api/commerce";
import { vaultApi } from "../../api/memory";
import { Badge, Bar, Stat } from "../../components/budget";
import { ProposalComposerSheet } from "../../components/commerce/ProposalComposerSheet";
import { SendProposalWhatsappSheet } from "../../components/commerce/SendProposalWhatsappSheet";
import { EmptyGuide, Tip } from "../../components/help";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../../components/ui";
import { useUndo } from "../../components/undo";
import { DOC_STATUS_LABELS, DOC_TYPE_OPTIONS, formatQty } from "../../lib/commerce";
import { formatDateHeading, money, plural, shortDate } from "../../lib/format";
import { normalizeText } from "../../lib/text";
import { formatIsoDateBr } from "../../lib/work";

export default function ProposalsPage() {
  const qc = useQueryClient();
  const undo = useUndo();
  const [filterType, setFilterType] = useState<CommercialDocType | "all">("all");
  const [search, setSearch] = useState("");
  const [openedIds, setOpenedIds] = useState<Set<string> | null>(null);

  // Busca sempre toda a carteira para manter contadores precisos nas pílulas.
  const docsQuery = useProposals("all");
  const allDocs = (docsQuery.data ?? []).filter((d) => !undo.isHidden(d.id));

  const [composerOpen, setComposerOpen] = useState(false);
  const [composerType, setComposerType] = useState<CommercialDocType>("proposal");
  const [sendTarget, setSendTarget] = useState<CommercialDocument | null>(null);
  const [approveTarget, setApproveTarget] = useState<CommercialDocument | null>(null);
  const [approveSyncBudget, setApproveSyncBudget] = useState(true);
  const [approveSyncCrm, setApproveSyncCrm] = useState(true);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errBanner, setErrBanner] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const bridges = useProposalBridges(composerOpen || Boolean(sendTarget)).data;

  const firstId = allDocs[0]?.id;
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
    void qc.invalidateQueries({ queryKey: ["proposals"] });
    void qc.invalidateQueries({ queryKey: ["crm"] });
  }

  function openComposer(type: CommercialDocType = "proposal") {
    setComposerType(type);
    setComposerOpen(true);
  }

  const approveDoc = useMutation({
    mutationFn: ({ id, syncBudget, syncCrm }: { id: string; syncBudget: boolean; syncCrm: boolean }) =>
      proposalsApi.approve(id, { sync_crm: syncCrm, sync_budget: syncBudget }),
    onSuccess: (doc, vars) => {
      setApproveTarget(null);
      invalidateAll();
      setErrBanner(null);
      const parts = [
        vars.syncCrm ? "negócio ganho no CRM" : null,
        vars.syncBudget ? "receita lançada no Meu Orçamento" : null,
      ].filter(Boolean);
      const tail = parts.length > 0 ? `: ${parts.join(" e ")}` : "";
      setFeedback(`Documento #${String(doc.number).padStart(4, "0")} aprovado${tail}.`);
    },
    onError: (e) => setErrBanner(errorMessage(e)),
  });

  const archiveToVault = useMutation({
    mutationFn: (id: string) => vaultApi.archiveFromProposal(id),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["cofre"] });
      setErrBanner(null);
      setFeedback(
        res.archived
          ? `PDF "${res.document.title}" arquivado no Cofre permanente.`
          : `PDF "${res.document.title}" já está guardado no Cofre.`,
      );
    },
    onError: (e) => setErrBanner(errorMessage(e)),
  });

  const createProjectFromDoc = useMutation({
    mutationFn: proposalsApi.createProject,
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      setErrBanner(null);
      setFeedback(
        res.created
          ? `Projeto "${res.project.name}" criado com as tarefas do documento.`
          : `Projeto "${res.project.name}" já está aberto em Projetos & Tarefas.`,
      );
    },
    onError: (e) => setErrBanner(errorMessage(e)),
  });

  function deleteDocWithUndo(doc: CommercialDocument) {
    undo.remove({
      ids: [doc.id],
      message: `${doc.title} excluído`,
      commit: async () => {
        await proposalsApi.delete(doc.id);
        invalidateAll();
      },
    });
  }

  async function handleDownload(doc: CommercialDocument) {
    setErrBanner(null);
    setDownloadingId(doc.id);
    try {
      await downloadProposalPdf(
        doc.id,
        `documento-${String(doc.number).padStart(4, "0")}.pdf`,
      );
    } catch (e) {
      setErrBanner(errorMessage(e));
    } finally {
      setDownloadingId(null);
    }
  }

  const needle = normalizeText(search);
  const shownDocs = allDocs.filter((doc) => {
    if (filterType !== "all" && doc.doc_type !== filterType) return false;
    if (!needle) return true;
    const code = String(doc.number).padStart(4, "0");
    return normalizeText(`${code} ${doc.title} ${doc.customer_name} ${doc.doc_label}`).includes(needle);
  });

  const allOpen = shownDocs.length > 0 && shownDocs.every((d) => open.has(d.id));
  const approvedDocs = allDocs.filter((d) => d.status === "approved");
  const openDocs = allDocs.filter((d) => d.status === "draft" || d.status === "sent");
  const approvedTotal = approvedDocs.reduce((acc, d) => acc + Number(d.total_amount), 0);
  const openTotal = openDocs.reduce((acc, d) => acc + Number(d.total_amount), 0);
  const totalPortfolio = allDocs.reduce((acc, d) => acc + Number(d.total_amount), 0);
  const approvalRate = allDocs.length > 0 ? Math.round((approvedDocs.length / allDocs.length) * 100) : 0;

  return (
    <div className="stack">
      <PageHeader
        title="Propostas, OS, Contratos & Recibos em PDF"
        subtitle="Gere documentos profissionais no servidor do Hub, envie pelo WhatsApp e aprove direto para o CRM e Meu Orçamento."
        actions={
          <Button type="button" onClick={() => openComposer("proposal")}>
            <Plus size={16} /> Novo documento
          </Button>
        }
      />

      {feedback && (
        <Alert tone="info">
          <div className="split">
            <span>{feedback}</span>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setFeedback(null)}>
              Fechar
            </button>
          </div>
        </Alert>
      )}
      {errBanner && <Alert tone="error">{errBanner}</Alert>}

      {docsQuery.isPending && (
        <LoadingRegion label="Carregando documentos comerciais">
          <Skeleton height={160} />
        </LoadingRegion>
      )}
      {docsQuery.isError && <Alert tone="error">{errorMessage(docsQuery.error)}</Alert>}

      {!docsQuery.isPending && (
        <>
          <div className="greeting">
            <span className="greeting__date">{formatDateHeading()}</span>
            <p className="greeting__hello">
              {allDocs.length === 0
                ? "Pronto para emitir sua primeira proposta ou recibo em PDF."
                : `Você tem ${openDocs.length} ${plural(openDocs.length, "documento", "documentos")} aguardando resposta e ${approvedDocs.length} ${plural(approvedDocs.length, "aprovado", "aprovados")}.`}
            </p>
            <p className="greeting__text">
              Os PDFs A4 são gerados localmente no servidor, sem cobrança bancária nem links de Pix.
            </p>
          </div>

          <section className="card month-summary" aria-label="Resumo comercial dos documentos">
            <div className="month-summary__main">
              <span className="month-summary__label">
                <CheckCircle2 size={15} aria-hidden /> Aprovados e fechados
              </span>
              <strong className="month-summary__value tone--ok">{money(approvedTotal)}</strong>
              <span className="muted small">
                {approvedDocs.length} de {allDocs.length} {plural(allDocs.length, "documento", "documentos")} ({approvalRate}% de aprovação)
              </span>
            </div>
            <div className="month-summary__side">
              <dl className="month-summary__grid">
                <div>
                  <dt>
                    <FileCheck2 size={14} aria-hidden /> Em aberto
                  </dt>
                  <dd className="month-summary__num">{money(openTotal)}</dd>
                  <dd className="month-summary__foot">{openDocs.length} aguardando</dd>
                </div>
                <div>
                  <dt>
                    <FileText size={14} aria-hidden /> Volume emitido
                  </dt>
                  <dd className="month-summary__num">{money(totalPortfolio)}</dd>
                  <dd className="month-summary__foot">{allDocs.length} {plural(allDocs.length, "PDF", "PDFs")} no total</dd>
                </div>
                <div>
                  <dt>Taxa de aprovação</dt>
                  <dd className="month-summary__num">{approvalRate}%</dd>
                  <dd className="month-summary__foot">Integrado ao CRM e Orçamento</dd>
                </div>
              </dl>
              <div
                className="month-summary__bar"
                role="img"
                aria-label={`${approvalRate}% dos documentos aprovados`}
              >
                <span style={{ width: `${approvalRate}%` }} />
              </div>
            </div>
          </section>
        </>
      )}

      {allDocs.length === 0 && !docsQuery.isPending ? (
        <section className="card">
          <EmptyGuide
            icon={<FileText size={22} />}
            title="Nenhum documento emitido ainda"
            text="Crie propostas comerciais, ordens de serviço, contratos ou recibos em PDF A4 limpo, envie na hora pelo WhatsApp e aprove com lançamento automático."
            example={<>Ex.: Proposta “Projeto Iluminação Comercial” para Cliente Ana no valor de R$ 2.400.</>}
            action={
              <Button type="button" onClick={() => openComposer("proposal")}>
                <Plus size={16} /> Novo documento
              </Button>
            }
          />
        </section>
      ) : (
        allDocs.length > 0 && (
          <>
            <div className="list-tools list-tools--pills person-tools" role="search" aria-label="Filtrar documentos">
              <label className="list-tools__search">
                <Search size={16} aria-hidden />
                <span className="sr-only">Buscar documento ou cliente</span>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar título, #número ou cliente..."
                />
              </label>
              <span className="pill-group" role="group" aria-label="Tipo de documento">
                <button
                  type="button"
                  className="chip-btn"
                  aria-pressed={filterType === "all"}
                  onClick={() => setFilterType("all")}
                >
                  Todos ({allDocs.length})
                </button>
                {DOC_TYPE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className="chip-btn"
                    aria-pressed={filterType === opt.value}
                    onClick={() => setFilterType(opt.value)}
                  >
                    {opt.plural} ({allDocs.filter((d) => d.doc_type === opt.value).length})
                  </button>
                ))}
              </span>
              <button
                type="button"
                className="chip-btn person-tools__all"
                aria-pressed={allOpen}
                onClick={() =>
                  setOpenedIds(allOpen ? new Set() : new Set(shownDocs.map((d) => d.id)))
                }
              >
                {allOpen ? "Fechar todos" : "Abrir todos"}
              </button>
            </div>

            {shownDocs.length === 0 ? (
              <p className="muted">Nenhum documento encontrado com esse filtro.</p>
            ) : (
              <div className="person-rows">
                {shownDocs.map((doc) => {
                  const isOpen = open.has(doc.id);
                  const code = String(doc.number).padStart(4, "0");
                  const progressPct =
                    doc.status === "approved" ? 100 : doc.status === "sent" ? 60 : doc.status === "draft" ? 25 : 0;
                  return (
                    <article
                      key={doc.id}
                      className={`card person-row person-row--long ${isOpen ? "is-open" : ""}`}
                      data-doc-row={doc.id}
                    >
                      <button
                        type="button"
                        className="person-row__head"
                        aria-expanded={isOpen}
                        onClick={() => toggleRow(doc.id)}
                      >
                        <span className="person-row__avatar" aria-hidden>
                          <FileText size={18} />
                        </span>
                        <span className="person-row__who">
                          <strong title={doc.title}>
                            #{code} · {doc.title}
                          </strong>
                          <span className="muted small">
                            {doc.doc_label} · {doc.customer_name} ·{" "}
                            {shortDate(doc.created_at.slice(0, 10))}
                          </span>
                        </span>
                        <span className="person-row__progress">
                          <span className="person-row__bar">
                            <Bar
                              pct={progressPct}
                              color={
                                doc.status === "sent"
                                  ? "var(--warn)"
                                  : doc.status === "rejected" || doc.status === "cancelled"
                                    ? "var(--error)"
                                    : undefined
                              }
                            />
                          </span>
                          <span className="muted small">{DOC_STATUS_LABELS[doc.status]}</span>
                        </span>
                        <span className="person-row__balance">
                          <strong className="tone--ok">{money(doc.total_amount)}</strong>
                        </span>
                        <span className="person-row__chev" aria-hidden>
                          <ChevronDown size={18} />
                        </span>
                      </button>

                      {isOpen && (
                        <div className="person-row__body">
                          <div className="row">
                            <Badge tone={doc.status === "approved" ? "accent" : doc.status === "sent" ? "warn" : "neutral"}>
                              {DOC_STATUS_LABELS[doc.status]}
                            </Badge>
                            {doc.valid_until && (
                              <Badge tone="neutral">Válido até {formatIsoDateBr(doc.valid_until)}</Badge>
                            )}
                            {doc.budget_income_id && <Badge tone="accent">Receita no Orçamento</Badge>}
                            {doc.crm_deal_id && <Badge tone="accent">Ganho no CRM</Badge>}
                          </div>

                          <div className="stats">
                            <Stat label="Cliente" value={doc.customer_name} />
                            <Stat label="Itens incluídos" value={`${doc.items.length} ${plural(doc.items.length, "item", "itens")}`} />
                            <Stat label="Desconto" value={money(doc.discount)} />
                            <Stat label="Total do PDF" value={money(doc.total_amount)} tone="ok" />
                          </div>

                          {doc.items.length > 0 && (
                            <ul className="items">
                              {doc.items.map((it, idx) => (
                                <li key={idx} className="item">
                                  <span className="item__main">
                                    <strong className="item__title">{it.name}</strong>
                                    <span className="item__meta">
                                      {formatQty(it.qty)} {it.unit ?? "un"} × {money(it.unit_price)}
                                    </span>
                                  </span>
                                  <span className="item__value">
                                    {money((Number(it.qty) || 0) * (Number(it.unit_price) || 0))}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}

                          {doc.terms_text && <p className="muted small">{doc.terms_text}</p>}

                          <div className="person-row__actions">
                            <button
                              type="button"
                              className="btn btn--secondary btn--sm"
                              disabled={downloadingId === doc.id}
                              onClick={() => handleDownload(doc)}
                            >
                              <Download size={14} /> PDF
                            </button>
                            <button
                              type="button"
                              className="btn btn--secondary btn--sm"
                              onClick={() => setSendTarget(doc)}
                            >
                              <MessageCircle size={14} /> WhatsApp
                            </button>
                            {(doc.status === "draft" || doc.status === "sent") && (
                              <button
                                type="button"
                                className="btn btn--primary btn--sm"
                                disabled={approveDoc.isPending}
                                onClick={() => {
                                  setApproveTarget(doc);
                                  setApproveSyncBudget(true);
                                  setApproveSyncCrm(true);
                                }}
                              >
                                <CheckCircle2 size={14} /> Aprovar
                              </button>
                            )}
                            <button
                              type="button"
                              className="btn btn--secondary btn--sm"
                              disabled={archiveToVault.isPending}
                              onClick={() => archiveToVault.mutate(doc.id)}
                            >
                              <ShieldCheck size={14} /> Cofre
                            </button>
                            {doc.status === "approved" && (
                              <button
                                type="button"
                                className="btn btn--secondary btn--sm"
                                disabled={createProjectFromDoc.isPending}
                                onClick={() => createProjectFromDoc.mutate(doc.id)}
                              >
                                <FolderKanban size={14} /> Abrir Projeto
                              </button>
                            )}
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
        )
      )}

      <ProposalComposerSheet
        open={composerOpen}
        initialType={composerType}
        bridges={bridges}
        onClose={() => setComposerOpen(false)}
        onCreated={(doc) => {
          setOpenedIds((prev) => new Set([doc.id, ...(prev ?? [])]));
          invalidateAll();
          setFeedback(`Documento #${String(doc.number).padStart(4, "0")} criado e pronto em PDF.`);
        }}
      />

      <SendProposalWhatsappSheet
        target={sendTarget}
        bridges={bridges}
        onClose={() => setSendTarget(null)}
        onSent={() => {
          invalidateAll();
          setFeedback("PDF colocado na fila da Mensageria para envio pelo WhatsApp.");
        }}
      />

      <Sheet
        open={Boolean(approveTarget)}
        title={`Aprovar #${approveTarget ? String(approveTarget.number).padStart(4, "0") : ""}`}
        onClose={() => setApproveTarget(null)}
      >
        {approveTarget && (
          <div className="stack">
            <div className="summary-box">
              <div className="split small">
                <span>
                  {approveTarget.title} · {approveTarget.customer_name}
                </span>
                <strong>{money(approveTarget.total_amount)}</strong>
              </div>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={approveSyncBudget}
                onChange={(e) => setApproveSyncBudget(e.target.checked)}
              />
              <span>
                Lançar receita no Meu Orçamento{" "}
                <Tip>Desmarque se quiser apenas aprovar o documento agora e registrar o valor quando for pago.</Tip>
              </span>
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={approveSyncCrm}
                onChange={(e) => setApproveSyncCrm(e.target.checked)}
              />
              <span>Atualizar negócio vinculado para Ganho no CRM</span>
            </label>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => setApproveTarget(null)}>
                Cancelar
              </Button>
              <Button
                type="button"
                loading={approveDoc.isPending}
                onClick={() =>
                  approveDoc.mutate({
                    id: approveTarget.id,
                    syncBudget: approveSyncBudget,
                    syncCrm: approveSyncCrm,
                  })
                }
              >
                Confirmar aprovação
              </Button>
            </div>
          </div>
        )}
      </Sheet>
    </div>
  );
}
