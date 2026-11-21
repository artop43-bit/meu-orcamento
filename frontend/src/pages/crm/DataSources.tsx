import { useState, type ChangeEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  Eye,
  FileSpreadsheet,
  FileText,
  Globe,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import { crmApi, crmKeys, useSources, type DataSourceItem } from "../../api/crm";
import { ApiSourceModal } from "../../components/crm/ApiSourceModal";
import { DataPreviewPanel, type PreviewDraft } from "../../components/crm/DataPreviewPanel";
import { InspectSourceModal } from "../../components/crm/InspectSourceModal";
import { Alert, PageHeader } from "../../components/ui";
import { announce } from "../../lib/announce";
import { SOURCE_KIND_LABELS, strategyLabel } from "../../lib/crm";

export default function DataSources() {
  const qc = useQueryClient();
  const sourcesQuery = useSources();
  const sources = sourcesQuery.data ?? [];

  const [preview, setPreview] = useState<PreviewDraft | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [apiOpen, setApiOpen] = useState(false);
  const [inspectSource, setInspectSource] = useState<DataSourceItem | null>(null);

  const readPdf = useMutation({
    mutationFn: crmApi.previewPdf,
    onSuccess: (res) => {
      setPreview({
        kind: "pdf",
        filename: res.filename,
        sourceName: res.filename.replace(/\.pdf$/i, ""),
        strategyLabel: strategyLabel(res.strategy),
        usedOcr: res.used_ocr,
        pages: res.pages,
        warning: res.warning,
        columns: res.columns,
        rows: res.rows,
        totalRows: res.total_rows,
        contactMap: { ...res.suggestions.contact_mapping },
        dealMap: { ...res.suggestions.deal_mapping },
        recommendedTarget: res.suggestions.recommended_target,
      });
      setUploadError(null);
      setUploadSuccess(null);
      announce(`PDF lido: ${res.total_rows} linha(s) traduzida(s).`);
    },
    onError: (err) => setUploadError(errorMessage(err)),
  });

  const readCsv = useMutation({
    mutationFn: crmApi.previewCsv,
    onSuccess: (res) => {
      setPreview({
        kind: "csv",
        filename: res.filename,
        sourceName: res.filename.replace(/\.csv$/i, ""),
        strategyLabel: `CSV (delimitador "${res.delimiter}")`,
        columns: res.columns,
        rows: res.rows,
        totalRows: res.total_rows,
        contactMap: { ...res.suggestions.contact_mapping },
        dealMap: { ...res.suggestions.deal_mapping },
        recommendedTarget: res.suggestions.recommended_target,
      });
      setUploadError(null);
      setUploadSuccess(null);
      announce(`CSV lido: ${res.total_rows} linha(s).`);
    },
    onError: (err) => setUploadError(errorMessage(err)),
  });

  const syncApi = useMutation({
    mutationFn: crmApi.syncApiSource,
    onSuccess: (src) => {
      setUploadSuccess(`Fonte "${src.name}" sincronizada (${src.row_count} registros).`);
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
    },
    onError: (err) => setUploadError(errorMessage(err)),
  });

  const deleteSource = useMutation({
    mutationFn: crmApi.deleteSource,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      announce("Fonte excluída.");
    },
  });

  function onFileSelect(kind: "pdf" | "csv") {
    return (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      setUploadError(null);
      setUploadSuccess(null);
      if (kind === "pdf") readPdf.mutate(file);
      else readCsv.mutate(file);
    };
  }

  const busyUpload = readPdf.isPending || readCsv.isPending;

  return (
    <div className="stack">
      <PageHeader
        title="Fontes de Dados"
        subtitle="Suba qualquer PDF ou planilha CSV para traduzir em dados, ou conecte suas APIs externas."
        actions={
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setApiOpen(true)}
          >
            <Globe size={16} aria-hidden />
            Conectar API
          </button>
        }
      />

      <div className="grid-2">
        <label className="card crm-upload-card">
          <span className="crm-upload-card__icon" aria-hidden>
            <FileText size={22} />
          </span>
          <span className="crm-upload-card__text">
            <strong>Subir qualquer PDF</strong>
            <span className="muted small">
              Lê tabelas, extratos, fichas, contratos e PDFs escaneados (OCR local).
            </span>
          </span>
          <span className="btn btn--secondary btn--sm">
            <Upload size={15} aria-hidden />
            {readPdf.isPending ? "Lendo PDF…" : "Escolher PDF"}
          </span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            disabled={busyUpload}
            onChange={onFileSelect("pdf")}
          />
        </label>

        <label className="card crm-upload-card">
          <span className="crm-upload-card__icon" aria-hidden>
            <FileSpreadsheet size={22} />
          </span>
          <span className="crm-upload-card__text">
            <strong>Subir planilha CSV</strong>
            <span className="muted small">
              Detecta separador, datas e valores para gerar gráficos ou importar no CRM.
            </span>
          </span>
          <span className="btn btn--secondary btn--sm">
            <Upload size={15} aria-hidden />
            {readCsv.isPending ? "Lendo CSV…" : "Escolher CSV"}
          </span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            disabled={busyUpload}
            onChange={onFileSelect("csv")}
          />
        </label>
      </div>

      {uploadError && <Alert tone="error">{uploadError}</Alert>}
      {uploadSuccess && (
        <Alert tone="success">
          <CheckCircle2 size={16} aria-hidden /> {uploadSuccess}
        </Alert>
      )}

      {preview && (
        <DataPreviewPanel
          preview={preview}
          onChange={setPreview}
          onDiscard={() => setPreview(null)}
          onError={setUploadError}
          onSuccess={setUploadSuccess}
        />
      )}

      <section className="stack stack--tight">
        <h2>Fontes cadastradas</h2>
        {sourcesQuery.isError && <Alert tone="error">{errorMessage(sourcesQuery.error)}</Alert>}
        <div className="grid-2">
          {sources.map((src) => (
            <article key={src.id} className="card stack stack--tight">
              <div className="split">
                <div className="row">
                  <Database size={17} aria-hidden />
                  <strong>{src.name}</strong>
                </div>
                <span className="badge badge--muted">{SOURCE_KIND_LABELS[src.kind] ?? src.kind}</span>
              </div>
              {src.description && <p className="muted small">{src.description}</p>}
              <div className="row small muted">
                <span>{src.row_count} registro(s)</span>
                <span>{src.schema.length} coluna(s)</span>
                {src.has_credentials && <span className="badge badge--ok">Auth cifrada</span>}
              </div>
              {src.last_error && <Alert tone="error">{src.last_error}</Alert>}
              <div className="row">
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => setInspectSource(src)}
                >
                  <Eye size={14} aria-hidden />
                  Ver dados
                </button>
                {src.kind === "api" && (
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    disabled={syncApi.isPending}
                    onClick={() => syncApi.mutate(src.id)}
                  >
                    <RefreshCw size={14} aria-hidden />
                    Sincronizar
                  </button>
                )}
                {!src.kind.startsWith("native_") && (
                  <button
                    type="button"
                    className="btn btn--danger btn--sm"
                    onClick={() => deleteSource.mutate(src.id)}
                  >
                    <Trash2 size={14} aria-hidden />
                    Excluir
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      <ApiSourceModal
        open={apiOpen}
        onClose={() => setApiOpen(false)}
        onConnected={setUploadSuccess}
      />
      <InspectSourceModal source={inspectSource} onClose={() => setInspectSource(null)} />
    </div>
  );
}
