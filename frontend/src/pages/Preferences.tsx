import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Keyboard, Mail, MessageSquarePlus } from "lucide-react";

import { api, errorMessage } from "../api/client";
import { openFeedback, openShortcuts, SHORTCUTS } from "../components/power";
import { Alert, Button, PageHeader } from "../components/ui";
import { setPrefs, usePrefs, type Prefs } from "../lib/prefs";

function Choice<K extends keyof Prefs>({
  name,
  label,
  value,
  options,
}: {
  name: K;
  label: string;
  value: Prefs[K];
  options: [Prefs[K], string][];
}) {
  return (
    <fieldset className="radios">
      <legend className="field-label">{label}</legend>
      <div className="segmented">
        {options.map(([option, text]) => (
          <label key={String(option)}>
            <input
              type="radio"
              name={String(name)}
              checked={value === option}
              onChange={() => setPrefs({ [name]: option } as Partial<Prefs>)}
            />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

type NotifyPrefs = { notify_due: boolean; notify_due_days: 1 | 3 | 7; notify_hide_values: boolean; notify_monthly: boolean };

/** Avisos por e-mail: vencimentos, resumo do mês e privacidade dos valores. */
function EmailNotices() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["notify-prefs"], queryFn: () => api.get<NotifyPrefs>("/notifications/prefs") });
  const [error, setError] = useState("");
  // Muda na hora e confirma no servidor; se falhar, volta ao que era e explica.
  async function update(changes: Partial<NotifyPrefs>) {
    const previous = queryClient.getQueryData<NotifyPrefs>(["notify-prefs"]);
    if (previous) queryClient.setQueryData(["notify-prefs"], { ...previous, ...changes });
    setError("");
    try {
      const next = await api.patch<NotifyPrefs>("/notifications/prefs", changes);
      queryClient.setQueryData(["notify-prefs"], next);
    } catch (err) {
      queryClient.setQueryData(["notify-prefs"], previous);
      setError(errorMessage(err));
    }
  }
  const p = prefs.data;
  return (
    <section className="card stack">
      <h2>
        <Mail size={18} aria-hidden /> Avisos por e-mail
      </h2>
      <Alert tone="error">{error}</Alert>
      {!p ? (
        <p className="muted small">Carregando…</p>
      ) : (
        <>
          <label className="check">
            <input type="checkbox" checked={p.notify_due} onChange={(e) => void update({ notify_due: e.target.checked })} />
            Lembrete de vencimentos (um e-mail por dia, às 8h, só quando houver contas em aberto)
          </label>
          {p.notify_due && (
            <fieldset className="radios">
              <legend className="field-label">Avisar com antecedência de</legend>
              <div className="segmented">
                {([1, 3, 7] as const).map((days) => (
                  <label key={days}>
                    <input type="radio" name="due-days" checked={p.notify_due_days === days} onChange={() => void update({ notify_due_days: days })} />
                    {days === 1 ? "1 dia" : `${days} dias`}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="check">
            <input type="checkbox" checked={p.notify_monthly} onChange={(e) => void update({ notify_monthly: e.target.checked })} />
            Resumo do mês no dia 1 (resultado, poupança, categorias e metas)
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_hide_values} onChange={(e) => void update({ notify_hide_values: e.target.checked })} />
            Ocultar valores nos e-mails
          </label>
          <p className="muted small" style={{ margin: 0 }}>
            O aviso de acesso por um aparelho novo é sempre enviado, por segurança.
          </p>
        </>
      )}
    </section>
  );
}

export default function Preferences() {
  const prefs = usePrefs();
  return (
    <>
      <PageHeader title="Preferências" subtitle="Aparência, privacidade e avisos por e-mail." />
      <div className="layout-main-side">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Aparência</h2>
            <Choice
              name="theme"
              label="Tema"
              value={prefs.theme}
              options={[
                ["system", "Automático (sistema)"],
                ["light", "Claro"],
                ["dark", "Escuro"],
              ]}
            />
            <Choice
              name="accent"
              label="Cor de destaque"
              value={prefs.accent}
              options={[
                ["verde", "Verde"],
                ["azul", "Azul"],
                ["roxo", "Roxo"],
                ["laranja", "Laranja"],
              ]}
            />
            <Choice
              name="text"
              label="Tamanho do texto"
              value={prefs.text}
              options={[
                ["normal", "Normal"],
                ["grande", "Grande"],
                ["maior", "Maior"],
              ]}
            />
            <Choice
              name="density"
              label="Espaçamento"
              value={prefs.density}
              options={[
                ["confortavel", "Confortável"],
                ["compacta", "Compacto"],
              ]}
            />
          </section>
          <EmailNotices />
          <section className="card stack">
            <h2>Privacidade</h2>
            <label className="check">
              <input type="checkbox" checked={prefs.privacy} onChange={(e) => setPrefs({ privacy: e.target.checked })} />
              Ocultar valores agora (atalho: P)
            </label>
            <label className="check">
              <input type="checkbox" checked={prefs.privacyOnStart} onChange={(e) => setPrefs({ privacyOnStart: e.target.checked })} />
              Iniciar sempre com os valores ocultos
            </label>
            <p className="muted small" style={{ margin: 0 }}>
              Oculta valores em locais públicos ou ao compartilhar a tela: valores exibidos como “R$ ••••” e gráficos desfocados.
            </p>
          </section>
        </div>
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Atalhos</h2>
            <dl className="shortcuts">
              {SHORTCUTS.map(([key, what]) => (
                <div key={key}>
                  <dt>
                    <kbd>{key}</kbd>
                  </dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
            <Button type="button" variant="secondary" onClick={openShortcuts}>
              <Keyboard size={16} /> Ver atalhos
            </Button>
          </section>
          <section className="card stack">
            <h2>Feedback</h2>
            <p className="muted" style={{ margin: 0 }}>
              Relate problemas ou envie sugestões diretamente à equipe.
            </p>
            <Button type="button" variant="secondary" onClick={openFeedback}>
              <MessageSquarePlus size={16} /> Enviar feedback
            </Button>
          </section>
        </div>
      </div>
    </>
  );
}
