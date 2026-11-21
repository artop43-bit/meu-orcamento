import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { crmApi, crmKeys, type ApiPreviewResponse } from "../../api/crm";
import { announce } from "../../lib/announce";
import { formatCrmCell } from "../../lib/crm";
import { Alert, Sheet } from "../ui";

/** Folha modal para testar e conectar uma API externa REST/JSON via HTTPS. */
export function ApiSourceModal({
  open,
  onClose,
  onConnected,
}: {
  open: boolean;
  onClose: () => void;
  onConnected: (message: string) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState<"GET" | "POST">("GET");
  const [dataPath, setDataPath] = useState("");
  const [authType, setAuthType] = useState<"none" | "bearer" | "api_key" | "basic">("none");
  const [authValue, setAuthValue] = useState("");
  const [headerName, setHeaderName] = useState("X-API-Key");
  const [preview, setPreview] = useState<ApiPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      setPreview(null);
    }
  }, [open]);

  const testApi = useMutation({
    mutationFn: () =>
      crmApi.previewApi({
        url,
        method,
        data_path: dataPath || undefined,
        auth_type: authType,
        auth_value: authValue || undefined,
        header_name: headerName || undefined,
      }),
    onSuccess: (res) => {
      setPreview(res);
      setError(null);
    },
    onError: (err) => {
      setPreview(null);
      setError(errorMessage(err));
    },
  });

  const saveApi = useMutation({
    mutationFn: () =>
      crmApi.createApiSource({
        name,
        url,
        method,
        data_path: dataPath || undefined,
        auth_type: authType,
        auth_value: authValue || undefined,
        header_name: headerName || undefined,
        sync_now: true,
      }),
    onSuccess: (src) => {
      setName("");
      setUrl("");
      setDataPath("");
      setAuthValue("");
      setPreview(null);
      setError(null);
      onClose();
      onConnected(`API "${src.name}" conectada com ${src.row_count} registro(s).`);
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce(`API "${src.name}" conectada.`);
    },
    onError: (err) => setError(errorMessage(err)),
  });

  function submitApi(event: FormEvent) {
    event.preventDefault();
    saveApi.mutate();
  }

  return (
    <Sheet open={open} title="Conectar API externa (REST/JSON)" onClose={onClose} wide>
      <form className="inline-form stack" onSubmit={submitApi}>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="grid-2">
          <label className="field">
            <span className="field-label">Nome da conexão</span>
            <input
              type="text"
              required
              placeholder="Ex.: ERP Pedidos"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Método</span>
            <select value={method} onChange={(e) => setMethod(e.target.value as "GET" | "POST")}>
              <option value="GET">GET</option>
              <option value="POST">POST (leitura)</option>
            </select>
          </label>
        </div>
        <label className="field">
          <span className="field-label">Endereço HTTPS da API</span>
          <input
            type="url"
            required
            placeholder="https://api.suaempresa.com/v1/vendas"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">Caminho da lista JSON (opcional)</span>
            <input
              type="text"
              placeholder="Ex.: data.items"
              value={dataPath}
              onChange={(e) => setDataPath(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Autenticação</span>
            <select
              value={authType}
              onChange={(e) =>
                setAuthType(e.target.value as "none" | "bearer" | "api_key" | "basic")
              }
            >
              <option value="none">Sem autenticação</option>
              <option value="bearer">Bearer Token</option>
              <option value="api_key">API Key em cabeçalho</option>
              <option value="basic">Basic (usuario:senha)</option>
            </select>
          </label>
        </div>
        {authType !== "none" && (
          <div className="grid-2">
            {authType === "api_key" && (
              <label className="field">
                <span className="field-label">Nome do cabeçalho</span>
                <input
                  type="text"
                  value={headerName}
                  onChange={(e) => setHeaderName(e.target.value)}
                />
              </label>
            )}
            <label className="field">
              <span className="field-label">Token / Chave (cifrada no banco)</span>
              <input
                type="password"
                value={authValue}
                onChange={(e) => setAuthValue(e.target.value)}
              />
            </label>
          </div>
        )}

        <div className="split">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={!url || testApi.isPending}
            onClick={() => testApi.mutate()}
          >
            {testApi.isPending ? "Testando…" : "Testar e visualizar"}
          </button>
          <div className="row">
            <button type="button" className="btn btn--secondary" onClick={onClose}>
              Cancelar
            </button>
            <button type="submit" className="btn btn--primary" disabled={saveApi.isPending}>
              {saveApi.isPending ? "Salvando…" : "Salvar conexão"}
            </button>
          </div>
        </div>

        {preview && (
          <div className="stack stack--tight">
            <Alert tone="success">
              Conexão validada: {preview.total_rows} registro(s) e {preview.columns.length} coluna(s).
            </Alert>
            <div className="table-scroll" tabIndex={0} role="region" aria-label="Amostra da API">
              <table className="crm-data-table">
                <thead>
                  <tr>
                    {preview.columns.map((c) => (
                      <th key={c.name}>{c.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 5).map((row, idx) => (
                    <tr key={idx}>
                      {preview.columns.map((c) => (
                        <td key={c.name}>{formatCrmCell(row[c.name], c.type)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </form>
    </Sheet>
  );
}
