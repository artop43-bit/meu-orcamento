import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Pin, Send } from "lucide-react";

import { errorMessage } from "../api/client";
import { inboxApi } from "../api/inbox";
import { Badge } from "../components/budget";
import { Tip } from "../components/help";
import { Alert, Button, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Administração › Recados: mensagem para todos os usuários, com prévia e confirmação. */
export default function AdminAnnouncements() {
  const queryClient = useQueryClient();
  const history = useQuery({ queryKey: ["admin", "announcements"], queryFn: inboxApi.announcements });
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [important, setImportant] = useState(false);
  const [includePending, setIncludePending] = useState(false);
  const audience = useQuery({
    queryKey: ["admin", "announcements", "audience", includePending],
    queryFn: () => inboxApi.audience(includePending),
  });
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");
  const recipients = audience.data?.recipients;

  function review(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSent("");
    setReviewing(true);
  }

  async function send() {
    setBusy(true);
    setError("");
    try {
      const result = await inboxApi.announce({ title: title.trim(), body: body.trim(), important, include_pending: includePending });
      setReviewing(false);
      setTitle("");
      setBody("");
      setImportant(false);
      setIncludePending(false);
      setSent(`Recado enviado para ${result.recipients} usuário(s).`);
      announce(`Recado enviado para ${result.recipients} usuário(s)`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "announcements"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "emails"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="card stack">
        <h2>
          <Megaphone size={18} aria-hidden /> Novo recado
        </h2>
        <p className="muted small" style={{ margin: 0 }}>
          O recado chega na caixa de Mensagens de cada usuário e por e-mail (para quem não desligou a cópia por e-mail).
        </p>
        <Alert tone="success">{sent}</Alert>
        <form className="inline-form" onSubmit={review}>
          <label>
            Título
            <input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} maxLength={120} placeholder="Ex.: Nova versão disponível" />
          </label>
          <label>
            Mensagem
            <textarea value={body} onChange={(e) => setBody(e.target.value)} required minLength={3} maxLength={5000} rows={6} />
          </label>
          <label className="check">
            <input type="checkbox" checked={important} onChange={(e) => setImportant(e.target.checked)} />
            <span>
              Importante{" "}
              <Tip>Fica fixado no topo da caixa até ser lido e o e-mail é enviado mesmo para quem desligou as cópias. Use só para avisos do serviço.</Tip>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={includePending} onChange={(e) => setIncludePending(e.target.checked)} />
            Enviar também para quem está aguardando a liberação do acesso
          </label>
          <div className="form-actions form-actions--split">
            <span className="muted small" aria-live="polite">
              {recipients === undefined ? "Contando destinatários…" : `${recipients} destinatário(s)`}
            </span>
            <Button type="submit" disabled={!recipients}>
              <Send size={16} /> Revisar e enviar
            </Button>
          </div>
        </form>
      </section>

      <section className="card stack">
        <h2>Recados enviados</h2>
        {history.isPending && <Skeleton height={100} />}
        {history.isError && <Alert tone="error">{errorMessage(history.error)}</Alert>}
        {history.data && history.data.length === 0 && <p className="muted" style={{ margin: 0 }}>Nenhum recado enviado ainda.</p>}
        {history.data && history.data.length > 0 && (
          <ul className="items">
            {history.data.map((a) => (
              <li key={a.id} className="item">
                <span className="item__main">
                  <span className="item__title">
                    {a.title} {a.important && <Badge tone="warn">Importante</Badge>}
                  </span>
                  <span className="item__meta">
                    {when(a.created_at)} · {a.recipients} destinatário(s) · lido por {a.read}
                    {a.replies > 0 && ` · ${a.replies} resposta(s) em Solicitações`}
                    {a.include_pending && " · incluiu quem aguarda liberação"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Sheet open={reviewing} title="Revisar recado" onClose={() => setReviewing(false)}>
        <div className="stack">
          <Alert tone="error">{error}</Alert>
          <div className="announcement-preview">
            <p className="announcement-preview__title">
              {important && <Pin size={14} aria-hidden />} {title.trim()}
            </p>
            <p className="announcement-preview__body">{body.trim()}</p>
          </div>
          <p className="muted small" style={{ margin: 0 }}>
            Vai para a caixa de Mensagens e por e-mail{important ? " (inclusive para quem desligou as cópias)" : ""}. Depois de enviado, não dá para
            editar nem apagar.
          </p>
          <div className="form-actions">
            <Button type="button" variant="secondary" onClick={() => setReviewing(false)}>
              Voltar e editar
            </Button>
            <Button type="button" loading={busy} onClick={() => void send()}>
              <Send size={16} /> Enviar para {recipients} usuário(s)
            </Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
