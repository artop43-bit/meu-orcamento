import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, RotateCcw, TriangleAlert } from "lucide-react";

import { ME_KEY, useMe } from "../api/auth";
import { errorMessage } from "../api/client";
import { download } from "../api/data";
import { inboxApi, type ResetArea } from "../api/inbox";
import { announce } from "../lib/announce";
import { Alert, Button, Sheet } from "./ui";

const CONFIRMATION = "COMEÇAR DO ZERO";

const AREAS: { key: ResetArea; label: string; detail: string; effect?: string }[] = [
  {
    key: "entries",
    label: "Lançamentos",
    detail: "Receitas, despesas, parcelas, transferências, despesas previstas, comprovantes e importações.",
    effect: "As recorrências que ficarem voltam a ser lançadas nos meses que você abrir.",
  },
  { key: "recurring", label: "Recorrências", detail: "Contas e rendas fixas.", effect: "Lançamentos já feitos ficam; só deixam de ser criados nos próximos meses." },
  {
    key: "accounts",
    label: "Contas",
    detail: "Contas e saldos, e as transferências entre elas.",
    effect: "Lançamentos que ficarem passam a não ter conta.",
  },
  { key: "cards", label: "Cartões e faturas", detail: "Cartões de crédito e débito.", effect: "Compras que ficarem passam a não ter cartão." },
  { key: "goals", label: "Metas", detail: "Metas, aportes e imagens." },
  { key: "investments", label: "Investimentos", detail: "Carteira e lista de acompanhamento das cotações." },
  {
    key: "categories",
    label: "Categorias e regras",
    detail: "Categorias criadas por você, limites e regras automáticas.",
    effect: "Voltam as categorias padrão; o que usava uma categoria apagada passa para “Outros”.",
  },
  { key: "analyses", label: "Análises salvas", detail: "Análises montadas em Insights." },
];

/** Perfil › Zona de risco: escolher o que volta ao padrão, baixar backup e confirmar. */
export function StartOver() {
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const [open, setOpen] = useState(false);
  const preview = useQuery({ queryKey: ["account", "reset"], queryFn: inboxApi.resetPreview, enabled: open });
  const [chosen, setChosen] = useState<Set<ResetArea>>(new Set());
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [backupBusy, setBackupBusy] = useState(false);
  const [error, setError] = useState("");
  const counts = preview.data?.counts;
  const all = chosen.size === AREAS.length;
  const confirmed = confirmation.trim().toUpperCase() === CONFIRMATION;
  const effects = AREAS.filter((a) => chosen.has(a.key) && a.effect);

  function close() {
    setOpen(false);
    setChosen(new Set());
    setPassword("");
    setCode("");
    setConfirmation("");
    setError("");
  }

  function toggle(key: ResetArea) {
    setChosen((old) => {
      const next = new Set(old);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function backup() {
    setBackupBusy(true);
    setError("");
    try {
      await download("/export/backup", "meu-orcamento-backup.json");
      announce("Backup baixado");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBackupBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed || chosen.size === 0) return;
    setBusy(true);
    setError("");
    try {
      await inboxApi.reset({ areas: [...chosen], password, confirmation, code: code || undefined });
      announce("Dados apagados. A conta começa do zero nas áreas escolhidas.");
      close();
      await queryClient.invalidateQueries();
      await queryClient.refetchQueries({ queryKey: ME_KEY });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack danger-zone" aria-labelledby="danger-title">
      <h2 id="danger-title">
        <TriangleAlert size={18} aria-hidden /> Zona de risco
      </h2>
      <p className="muted" style={{ margin: 0 }}>
        Começar do zero apaga os dados que você cadastrou nas áreas escolhidas. A conta, o login, o perfil, as preferências e as solicitações
        continuam.
      </p>
      <div>
        <Button type="button" variant="danger" onClick={() => setOpen(true)}>
          <RotateCcw size={16} /> Começar do zero
        </Button>
      </div>

      <Sheet open={open} title="Começar do zero" onClose={close}>
        <form className="inline-form" onSubmit={submit}>
          <Alert tone="error">
            Esta ação apaga de vez os dados das áreas escolhidas e não pode ser desfeita.
          </Alert>
          <div className="backup-callout">
            <span>
              <strong>Antes, baixe um backup.</strong>
              <span className="muted small"> Com ele, dá para restaurar tudo depois em Importar e exportar.</span>
            </span>
            <Button type="button" variant="secondary" loading={backupBusy} onClick={() => void backup()}>
              <Archive size={16} /> Baixar backup
            </Button>
          </div>
          <fieldset className="radios">
            <legend className="field-label">O que volta ao padrão</legend>
            <label className="check reset-all">
              <input
                type="checkbox"
                checked={all}
                onChange={() => setChosen(all ? new Set() : new Set(AREAS.map((a) => a.key)))}
              />
              Selecionar tudo
            </label>
            <ul className="reset-areas">
              {AREAS.map((area) => (
                <li key={area.key}>
                  <label className="check">
                    <input type="checkbox" checked={chosen.has(area.key)} onChange={() => toggle(area.key)} />
                    <span className="reset-areas__text">
                      <strong>
                        {area.label}
                        {counts && <span className="muted"> · {counts[area.key]} item(ns)</span>}
                      </strong>
                      <span className="muted small">{area.detail}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
          {effects.length > 0 && (
            <div className="summary-box">
              <strong>O que acontece com o resto</strong>
              <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {effects.map((a) => (
                  <li key={a.key}>{a.effect}</li>
                ))}
              </ul>
            </div>
          )}
          {all && <p className="muted small" style={{ margin: 0 }}>Com tudo zerado, a configuração inicial guiada aparece de novo.</p>}
          <label>
            Sua senha
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {user?.totp_enabled && (
            <label>
              Código do aplicativo autenticador
              <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required maxLength={20} />
            </label>
          )}
          <label>
            Para confirmar, digite {CONFIRMATION}
            <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} autoComplete="off" spellCheck={false} required />
          </label>
          <Alert tone="error">{error}</Alert>
          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" variant="danger" loading={busy} disabled={!confirmed || chosen.size === 0 || !password}>
              Apagar {chosen.size === 0 ? "" : all ? "tudo" : `${chosen.size} área(s)`}
            </Button>
          </div>
        </form>
      </Sheet>
    </section>
  );
}
