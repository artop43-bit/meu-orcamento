import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { errorMessage } from "../../api/client";
import { crmApi, crmKeys, type ColumnDef, type ColumnType } from "../../api/crm";
import { announce } from "../../lib/announce";
import { COLUMN_TYPE_LABELS } from "../../lib/crm";
import { Alert } from "../ui";

export type PreviewDraft = {
  kind: "pdf" | "csv";
  filename: string;
  sourceName: string;
  strategyLabel: string;
  usedOcr?: boolean;
  pages?: number;
  warning?: string | null;
  columns: ColumnDef[];
  rows: Record<string, unknown>[];
  totalRows: number;
  contactMap: Record<string, string>;
  dealMap: Record<string, string>;
  recommendedTarget: "dataset" | "contacts" | "deals";
};

const CONTACT_MAP_FIELDS = [
  ["name", "Coluna de Nome *"],
  ["phone", "Coluna de Telefone"],
  ["email", "Coluna de E-mail"],
  ["company", "Coluna de Empresa"],
] as const;

const DEAL_MAP_FIELDS = [
  ["title", "Coluna de Título do negócio *"],
  ["value", "Coluna de Valor (R$)"],
  ["contact_name", "Coluna de Cliente / Contato"],
  ["expected_close_date", "Coluna de Data"],
] as const;

/** Painel de prévia editável de PDF/CSV, mapeamento de colunas e salvamento no CRM/Fontes. */
export function DataPreviewPanel({
  preview,
  onChange,
  onDiscard,
  onError,
  onSuccess,
}: {
  preview: PreviewDraft;
  onChange: (updater: (curr: PreviewDraft | null) => PreviewDraft | null) => void;
  onDiscard: () => void;
  onError: (msg: string) => void;
  onSuccess: (msg: string) => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [saveTarget, setSaveTarget] = useState<"dataset" | "contacts" | "deals">("dataset");
  const [createAutoDash, setCreateAutoDash] = useState(true);

  const saveDataset = useMutation({
    mutationFn: () =>
      crmApi.saveTabularSource({
        name: preview.sourceName.trim() || preview.filename,
        kind: preview.kind,
        columns: preview.columns,
        rows: preview.rows,
        create_dashboard: createAutoDash,
      }),
    onSuccess: (res) => {
      onDiscard();
      onSuccess(
        res?.dashboard
          ? `Fonte "${res.source.name}" salva e painel automático criado.`
          : `Fonte "${res?.source.name}" salva com sucesso.`,
      );
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      void qc.invalidateQueries({ queryKey: crmKeys.dashboards });
      announce("Fonte salva.");
      if (res?.dashboard) navigate("/crm");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  const importCrm = useMutation({
    mutationFn: () =>
      crmApi.importToCrm({
        target: saveTarget === "contacts" ? "contacts" : "deals",
        rows: preview.rows,
        mapping: saveTarget === "contacts" ? preview.contactMap : preview.dealMap,
        origin: `${preview.kind.toUpperCase()} · ${preview.sourceName}`,
      }),
    onSuccess: (res) => {
      onDiscard();
      onSuccess(
        saveTarget === "contacts"
          ? `Importação concluída: ${res?.created ?? 0} contato(s) criado(s) e ${res?.updated ?? 0} atualizado(s).`
          : `Importação concluída: ${res?.created ?? 0} negócio(s) adicionado(s) ao funil.`,
      );
      void qc.invalidateQueries({ queryKey: ["crm", "contacts"] });
      void qc.invalidateQueries({ queryKey: crmKeys.pipeline });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce("Dados importados para o CRM.");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  function updateCol(idx: number, patch: Partial<ColumnDef>) {
    onChange((curr) => {
      if (!curr) return null;
      return { ...curr, columns: curr.columns.map((c, i) => (i === idx ? { ...c, ...patch } : c)) };
    });
  }

  function updateCell(rowIdx: number, colName: string, value: string) {
    onChange((curr) => {
      if (!curr) return null;
      return {
        ...curr,
        rows: curr.rows.map((r, i) => (i === rowIdx ? { ...r, [colName]: value } : r)),
      };
    });
  }

  return (
    <section className="card stack" aria-label="Prévia dos dados extraídos">
      <div className="split">
        <div>
          <h2>Prévia e tradução · {preview.filename}</h2>
          <div className="row">
            <span className="badge badge--accent">{preview.strategyLabel}</span>
            {preview.usedOcr && <span className="badge badge--warn">OCR local ativado</span>}
            {preview.pages && <span className="badge badge--muted">{preview.pages} pág.</span>}
            <span className="badge badge--ok">{preview.totalRows} linha(s) traduzida(s)</span>
          </div>
        </div>
        <button type="button" className="btn btn--secondary btn--sm" onClick={onDiscard}>
          Descartar prévia
        </button>
      </div>

      {preview.warning && <Alert tone="info">{preview.warning}</Alert>}

      <div className="chips" role="group" aria-label="Destino dos dados">
        {(
          [
            ["dataset", "Salvar como Fonte de Dashboard"],
            ["contacts", "Importar para Contatos do CRM"],
            ["deals", "Importar para Negócios do CRM"],
          ] as const
        ).map(([val, label]) => (
          <button
            key={val}
            type="button"
            className="chip-btn"
            aria-pressed={saveTarget === val}
            onClick={() => setSaveTarget(val)}
          >
            {label}
          </button>
        ))}
      </div>

      {saveTarget === "dataset" && (
        <div className="grid-2">
          <label className="field">
            <span className="field-label">Nome da fonte</span>
            <input
              type="text"
              value={preview.sourceName}
              onChange={(e) => onChange((curr) => (curr ? { ...curr, sourceName: e.target.value } : null))}
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={createAutoDash}
              onChange={(e) => setCreateAutoDash(e.target.checked)}
            />
            <span>Criar painel automático com gráficos ao salvar</span>
          </label>
        </div>
      )}

      {saveTarget === "contacts" && (
        <div className="grid-2">
          {CONTACT_MAP_FIELDS.map(([field, label]) => (
            <label key={field} className="field">
              <span className="field-label">{label}</span>
              <select
                value={preview.contactMap[field] ?? ""}
                onChange={(e) =>
                  onChange((curr) =>
                    curr
                      ? { ...curr, contactMap: { ...curr.contactMap, [field]: e.target.value } }
                      : null,
                  )
                }
              >
                <option value="">Ignorar</option>
                {preview.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      {saveTarget === "deals" && (
        <div className="grid-2">
          {DEAL_MAP_FIELDS.map(([field, label]) => (
            <label key={field} className="field">
              <span className="field-label">{label}</span>
              <select
                value={preview.dealMap[field] ?? ""}
                onChange={(e) =>
                  onChange((curr) =>
                    curr ? { ...curr, dealMap: { ...curr.dealMap, [field]: e.target.value } } : null,
                  )
                }
              >
                <option value="">Ignorar</option>
                {preview.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      <div className="crm-schema-editor">
        {preview.columns.map((col, idx) => (
          <div key={col.name} className="crm-schema-chip">
            <input
              type="text"
              aria-label={`Nome da coluna ${col.label}`}
              value={col.label}
              onChange={(e) => updateCol(idx, { label: e.target.value })}
            />
            <select
              aria-label={`Tipo da coluna ${col.label}`}
              value={col.type}
              onChange={(e) => updateCol(idx, { type: e.target.value as ColumnType })}
            >
              {(Object.entries(COLUMN_TYPE_LABELS) as [ColumnType, string][]).map(([k, lbl]) => (
                <option key={k} value={k}>
                  {lbl}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <div className="table-scroll">
        <table className="crm-data-table">
          <thead>
            <tr>
              {preview.columns.map((col) => (
                <th key={col.name}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.slice(0, 12).map((row, rIdx) => (
              <tr key={rIdx}>
                {preview.columns.map((col) => (
                  <td key={col.name}>
                    <input
                      type="text"
                      className="crm-cell-input"
                      aria-label={`${col.label} linha ${rIdx + 1}`}
                      value={row[col.name] == null ? "" : String(row[col.name])}
                      onChange={(e) => updateCell(rIdx, col.name, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="form-actions">
        {saveTarget === "dataset" ? (
          <button
            type="button"
            className="btn btn--primary"
            disabled={saveDataset.isPending}
            onClick={() => saveDataset.mutate()}
          >
            {saveDataset.isPending ? "Salvando…" : "Confirmar e salvar fonte"}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn--primary"
            disabled={importCrm.isPending}
            onClick={() => importCrm.mutate()}
          >
            {importCrm.isPending ? "Importando…" : "Importar para o CRM"}
          </button>
        )}
      </div>
    </section>
  );
}
