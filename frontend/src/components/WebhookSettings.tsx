import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Webhook } from "lucide-react";

import { errorMessage } from "../api/client";
import { WEBHOOK_KEY, webhookApi, type WebhookConfig } from "../api/webhook";
import { announce } from "../lib/announce";
import { serviceLabel, WEBHOOK_KINDS, type WebhookKind } from "../lib/webhook";
import { Alert, Button, Field } from "./ui";

const EMPTY: WebhookConfig = { configured: false, hint: null, service: null, kinds: [], paused: false };

/** Preferências › Avisos por webhook (v1.9.0): Discord, Slack ou qualquer endereço https. */
export function WebhookSettings() {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: WEBHOOK_KEY, queryFn: webhookApi.get });
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "test" | "remove">("");

  function show(next: WebhookConfig) {
    queryClient.setQueryData(WEBHOOK_KEY, next);
  }

  async function run(kind: "save" | "test" | "remove", action: () => Promise<string>) {
    setError("");
    setDone("");
    setBusy(kind);
    try {
      const message = await action();
      setDone(message);
      announce(message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    void run("save", async () => {
      show(await webhookApi.save(url));
      setUrl("");
      return "Webhook salvo. Escolha abaixo os avisos que devem chegar lá.";
    });
  }

  function test() {
    void run("test", async () => {
      const { ok } = await webhookApi.test();
      await queryClient.invalidateQueries({ queryKey: WEBHOOK_KEY });
      if (!ok) throw new Error("O endereço não respondeu. Confira se o webhook ainda existe.");
      return "Teste enviado. Confira se a mensagem chegou.";
    });
  }

  function remove() {
    void run("remove", async () => {
      await webhookApi.remove();
      show(EMPTY);
      return "Webhook removido.";
    });
  }

  // Muda na hora e confirma no servidor; se falhar, volta ao que era e explica.
  async function toggle(kind: WebhookKind, on: boolean) {
    const previous = queryClient.getQueryData<WebhookConfig>(WEBHOOK_KEY);
    if (!previous) return;
    const kinds = on ? [...previous.kinds, kind] : previous.kinds.filter((k) => k !== kind);
    show({ ...previous, kinds });
    setError("");
    try {
      show(await webhookApi.kinds(kinds));
    } catch (err) {
      show(previous);
      setError(errorMessage(err));
    }
  }

  const c = config.data;
  return (
    <section className="card stack" id="webhook">
      <h2>
        <Webhook size={18} aria-hidden /> Avisos por webhook
      </h2>
      <p className="muted small" style={{ margin: 0 }}>
        Receba os avisos num servidor seu: Discord, Slack ou qualquer endereço que aceite webhook.
      </p>
      <Alert tone="error">{error}</Alert>
      <Alert tone="success">{done}</Alert>
      {!c ? (
        <p className="muted small">Carregando…</p>
      ) : !c.configured ? (
        <form className="stack stack--tight" onSubmit={save}>
          <Field
            id="webhook-url"
            label="Endereço do webhook"
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            maxLength={500}
            placeholder="https://discord.com/api/webhooks/…"
            autoComplete="off"
            required
          />
          <div className="row">
            <Button type="submit" loading={busy === "save"} disabled={!url.trim()}>
              Salvar
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="small" style={{ margin: 0 }}>
            Conectado a <strong>{serviceLabel(c.service ?? "generic")}</strong> · <span className="muted">{c.hint}</span>
          </p>
          {c.paused && <Alert tone="info">Os envios estão pausados: o endereço não respondeu 5 vezes. Envie um teste para retomar.</Alert>}
          {WEBHOOK_KINDS.map(({ key, label }) => (
            <label className="check" key={key}>
              <input type="checkbox" checked={c.kinds.includes(key)} onChange={(e) => void toggle(key, e.target.checked)} />
              {label}
            </label>
          ))}
          <p className="muted small" style={{ margin: 0 }}>
            A opção “Ocultar valores nos e-mails” também vale aqui.
          </p>
          <div className="row">
            <Button variant="secondary" loading={busy === "test"} onClick={test}>
              Enviar teste
            </Button>
            <Button variant="danger" loading={busy === "remove"} onClick={remove}>
              Remover
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
