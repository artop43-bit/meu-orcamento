import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Upload } from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  vaultApi,
  type VaultBridges,
  type VaultCategory,
  type VaultDocument,
} from "../../api/memory";
import { announce } from "../../lib/announce";
import { formatVaultSize, VAULT_CATEGORY_OPTIONS } from "../../lib/memory";
import { DateField } from "../DateField";
import { Alert, Button, Sheet } from "../ui";

/** Folha modal para arquivar PDF ou imagem com validade, busca por OCR local e vínculos no Hub. */
export function VaultUploadSheet({
  open,
  bridges,
  onClose,
  onCreated,
}: {
  open: boolean;
  bridges: VaultBridges | undefined;
  onClose: () => void;
  onCreated: (doc: VaultDocument) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<VaultCategory>("warranty");
  const [issuer, setIssuer] = useState("");
  const [docNumber, setDocNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [notifyDays, setNotifyDays] = useState("30");
  const [notes, setNotes] = useState("");
  const [contactId, setContactId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setTitle("");
    setCategory("warranty");
    setIssuer("");
    setDocNumber("");
    setIssueDate("");
    setExpiresAt("");
    setNotifyDays("30");
    setNotes("");
    setContactId("");
    setProjectId("");
    setErr(null);
  }, [open]);

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Escolha um PDF ou imagem.");
      const form = new FormData();
      form.append("file", file);
      form.append("title", title.trim());
      form.append("category", category);
      if (issuer.trim()) form.append("issuer", issuer.trim());
      if (docNumber.trim()) form.append("document_number", docNumber.trim());
      if (issueDate) form.append("issue_date", issueDate);
      if (expiresAt) form.append("expires_at", expiresAt);
      form.append("notify_days_before", notifyDays || "30");
      if (notes.trim()) form.append("notes", notes.trim());
      if (contactId) form.append("contact_id", contactId);
      if (projectId) form.append("project_id", projectId);
      return vaultApi.upload(form);
    },
    onSuccess: (created) => {
      onClose();
      onCreated(created);
      announce("Documento guardado no Cofre.");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  function onFilePicked(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    setFile(picked);
    setErr(null);
    if (picked && !title.trim()) {
      setTitle(picked.name.replace(/\.[^.]+$/, ""));
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setErr("Selecione um PDF, PNG, JPG ou WebP de até 15 MB.");
      return;
    }
    upload.mutate();
  }

  return (
    <Sheet open={open} title="Guardar no Cofre" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {err && <Alert tone="error">{err}</Alert>}

        <label className="field">
          <span className="field-label">Arquivo (PDF, PNG, JPG ou WebP · até 15 MB)</span>
          <input
            type="file"
            accept=".pdf,application/pdf,image/png,image/jpeg,image/webp"
            onChange={onFilePicked}
          />
        </label>

        {file && (
          <div className="summary-box">
            <div className="split small">
              <span>{file.name}</span>
              <strong>{formatVaultSize(file.size)} · leitura local de texto pronta</strong>
            </div>
          </div>
        )}

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Título do documento</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: Garantia Geladeira Cozinha"
              maxLength={160}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">Categoria</span>
            <select value={category} onChange={(e) => setCategory(e.target.value as VaultCategory)}>
              {VAULT_CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Emissor ou loja</span>
            <input
              value={issuer}
              onChange={(e) => setIssuer(e.target.value)}
              placeholder="Ex.: Fabricante ou Cartório"
              maxLength={140}
            />
          </label>
          <label className="field">
            <span className="field-label">Nº / NF / apólice</span>
            <input
              value={docNumber}
              onChange={(e) => setDocNumber(e.target.value)}
              placeholder="Ex.: NF-4412"
              maxLength={80}
            />
          </label>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Data de emissão</span>
            <DateField value={issueDate} onChange={setIssueDate} label="Data de emissão" />
          </label>
          <label className="field">
            <span className="field-label">Validade (opcional)</span>
            <DateField value={expiresAt} onChange={setExpiresAt} label="Validade do documento" />
          </label>
        </div>
        <p className="muted small vault-field-hint">
          Quando preenchida, a validade aparece automaticamente na Agenda 360°.
        </p>

        {expiresAt && (
          <label className="field">
            <span className="field-label">Avisar quantos dias antes</span>
            <input
              type="number"
              min={0}
              max={365}
              value={notifyDays}
              onChange={(e) => setNotifyDays(e.target.value)}
            />
          </label>
        )}

        <div className="grid-2">
          <label className="field">
            <span className="field-label">Contato CRM (opcional)</span>
            <select value={contactId} onChange={(e) => setContactId(e.target.value)}>
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
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Sem vínculo</option>
              {(bridges?.projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="field">
          <label htmlFor="vault-notes" className="field-label">
            Observações (opcional)
          </label>
          <textarea
            id="vault-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Nº de série, cobertura ou local físico do papel"
          />
        </div>

        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={upload.isPending}>
            <Upload size={15} /> Guardar documento
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
