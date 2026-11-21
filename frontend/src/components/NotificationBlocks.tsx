import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Mail } from "lucide-react";
import { Link } from "react-router";

import { api, errorMessage } from "../api/client";
import { currentSubscription, disablePush, enablePush, PUSH_KEY, pushApi, pushSupported, type PushConfig } from "../api/push";
import { announce } from "../lib/announce";
import { Alert, Button } from "./ui";

export type NotificationScope = "account" | "budget";

type NotifyPrefs = {
  notify_due: boolean;
  notify_due_days: 1 | 3 | 7;
  notify_hide_values: boolean;
  notify_monthly: boolean;
  notify_messages: boolean;
  notify_alerts: boolean;
  notify_weekly: boolean;
};

/** Avisos por e-mail: separados entre conta (Hub) e alertas financeiros (Meu Orçamento). */
export function EmailNoticesSection({ scope }: { scope: NotificationScope }) {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["notify-prefs"], queryFn: () => api.get<NotifyPrefs>("/notifications/prefs") });
  const [error, setError] = useState("");

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
      ) : scope === "account" ? (
        <>
          <label className="check">
            <input type="checkbox" checked={p.notify_messages} onChange={(e) => void update({ notify_messages: e.target.checked })} />
            Cópia por e-mail das mensagens (respostas às solicitações e recados da administração)
          </label>
          <p className="muted small" style={{ margin: 0 }}>
            O aviso de acesso por um aparelho novo é sempre enviado, por segurança.
          </p>
        </>
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
          <label className="check">
            <input type="checkbox" checked={p.notify_alerts} onChange={(e) => void update({ notify_alerts: e.target.checked })} />
            Alertas de gastos fora do padrão e de assinaturas
          </label>
          <label className="check">
            <input type="checkbox" checked={p.notify_weekly} onChange={(e) => void update({ notify_weekly: e.target.checked })} />
            Resumo da semana, às segundas às 8h (gastos da semana e as contas que vencem na semana)
          </label>
        </>
      )}
    </section>
  );
}

/** Notificações no aparelho (push): ativação do aparelho no Hub e alertas específicos no Meu Orçamento. */
export function PushNotificationsSection({ scope }: { scope: NotificationScope }) {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: PUSH_KEY, queryFn: pushApi.config });
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const supported = pushSupported();

  useEffect(() => {
    if (scope !== "account") return;
    void currentSubscription().then((s) => setSubscribed(Boolean(s)));
  }, [scope]);

  function store(data: PushConfig | null) {
    if (data) queryClient.setQueryData(PUSH_KEY, data);
  }

  async function toggle() {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      if (subscribed) {
        store(await disablePush());
        setSubscribed(false);
        announce("Notificações desativadas neste aparelho");
      } else {
        store(await enablePush(config.data!.public_key));
        setSubscribed(true);
        announce("Notificações ativadas neste aparelho");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setError("");
    try {
      const { sent } = await pushApi.test();
      setInfo(sent > 0 ? "Notificação de teste enviada." : "Nenhum aparelho recebeu. Ative as notificações neste aparelho primeiro.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function pref(key: "push_due" | "push_messages" | "push_alerts" | "push_weekly" | "push_daily", value: boolean) {
    const previous = config.data;
    if (previous) queryClient.setQueryData(PUSH_KEY, { ...previous, [key]: value });
    try {
      store(await pushApi.prefs({ [key]: value }));
    } catch (err) {
      if (previous) queryClient.setQueryData(PUSH_KEY, previous);
      setError(errorMessage(err));
    }
  }

  const data = config.data;
  if (scope === "budget") {
    return (
      <section className="card stack">
        <h2>
          <BellRing size={18} aria-hidden /> Notificações no aparelho
        </h2>
        <Alert tone="error">{error}</Alert>
        {!data ? (
          <p className="muted small">Carregando…</p>
        ) : !data.enabled ? (
          <Alert tone="info">As notificações no aparelho ainda não estão disponíveis no servidor.</Alert>
        ) : (
          <>
            <p className="muted small" style={{ margin: 0 }}>
              {data.devices === 0 ? (
                <>
                  Nenhum aparelho ativado. <Link to="/app">Ativar neste aparelho</Link>.
                </>
              ) : (
                `${data.devices} aparelho(s) recebendo notificações.`
              )}
            </p>
            <fieldset className="radios">
              <legend className="field-label">Alertas do Meu Orçamento</legend>
              <label className="check">
                <input type="checkbox" checked={data.push_due} onChange={(e) => void pref("push_due", e.target.checked)} />
                Contas a vencer
              </label>
              <label className="check">
                <input type="checkbox" checked={data.push_alerts} onChange={(e) => void pref("push_alerts", e.target.checked)} />
                Alertas de gastos e assinaturas
              </label>
              <label className="check">
                <input type="checkbox" checked={data.push_weekly} onChange={(e) => void pref("push_weekly", e.target.checked)} />
                Resumo da semana (segundas, 8h)
              </label>
              <label className="check">
                <input type="checkbox" checked={data.push_daily} onChange={(e) => void pref("push_daily", e.target.checked)} />
                Disponível hoje (todo dia às 8h)
              </label>
            </fieldset>
          </>
        )}
      </section>
    );
  }

  return (
    <section className="card stack">
      <h2>
        <BellRing size={18} aria-hidden /> Notificações no aparelho
      </h2>
      <p className="muted small" style={{ margin: 0 }}>
        Avisos na tela do celular ou do computador, mesmo com o app fechado. Funcionam no app Android, no Chrome e no Edge; no iPhone, só com o app
        adicionado à tela de início (exigência da Apple).
      </p>
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{info}</Alert>
      {!supported && <Alert tone="info">Este navegador não aceita notificações. No iPhone, adicione o app à tela de início e abra por lá.</Alert>}
      {supported && data && !data.enabled && <Alert tone="info">As notificações no aparelho ainda não estão disponíveis no servidor.</Alert>}
      {supported && data?.enabled && (
        <>
          <div className="row">
            <Button type="button" variant={subscribed ? "secondary" : "primary"} loading={busy} onClick={() => void toggle()}>
              {subscribed ? "Desativar neste aparelho" : "Ativar neste aparelho"}
            </Button>
            {subscribed && (
              <Button type="button" variant="secondary" onClick={() => void test()}>
                Enviar notificação de teste
              </Button>
            )}
          </div>
          <label className="check">
            <input type="checkbox" checked={data.push_messages} onChange={(e) => void pref("push_messages", e.target.checked)} />
            Mensagens (respostas às solicitações e recados da administração)
          </label>
          <p className="muted small" style={{ margin: 0 }}>
            {data.devices === 0 ? "Nenhum aparelho ativado." : `${data.devices} aparelho(s) recebendo notificações.`} Recados marcados como
            importantes chegam sempre.
          </p>
        </>
      )}
    </section>
  );
}
