import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Inbox, Mail, Megaphone, MessageSquare, ShieldAlert, Users } from "lucide-react";
import { useSearchParams } from "react-router";

import { errorMessage } from "../api/client";
import { moneyApi, type AdminAction, type AdminUser } from "../api/money";
import { Alert, Button, Kpi, LoadingRegion, PageHeader, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";
import AdminAnnouncements from "./AdminAnnouncements";
import AdminSupport from "./AdminSupport";

const TABS = [
  { key: "usuarios", label: "Usuários", icon: <Users size={16} /> },
  { key: "emails", label: "E-mails enviados", icon: <Mail size={16} /> },
  { key: "solicitacoes", label: "Solicitações", icon: <MessageSquare size={16} /> },
  { key: "recados", label: "Recados", icon: <Megaphone size={16} /> },
] as const;
type Tab = (typeof TABS)[number]["key"];

const STATUS: Record<AdminUser["access_status"], { label: string; tone: string }> = {
  pending: { label: "Aguardando liberação", tone: "badge--warn" },
  approved: { label: "Ativo", tone: "badge--ok" },
  blocked: { label: "Bloqueado", tone: "badge--error" },
};

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function UsersTab() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: moneyApi.adminUsers });
  const [filter, setFilter] = useState<"all" | "pending" | "blocked">("all");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function act(user: AdminUser, action: AdminAction, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setError("");
    setBusy(`${user.id}-${action}`);
    try {
      await moneyApi.adminAction(user.id, action);
      announce("Ação concluída");
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const list = (users.data ?? []).filter((u) => filter === "all" || u.access_status === filter);
  const button = (user: AdminUser, action: AdminAction, label: string, variant: "primary" | "secondary" | "danger" = "secondary", confirmText?: string) => (
    <Button type="button" variant={variant} loading={busy === `${user.id}-${action}`} onClick={() => void act(user, action, confirmText)}>
      {label}
    </Button>
  );

  return (
    <section className="card stack">
      <div className="split">
        <h2>Usuários</h2>
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="Filtrar usuários">
          <option value="all">Todos</option>
          <option value="pending">Aguardando liberação</option>
          <option value="blocked">Bloqueados</option>
        </select>
      </div>
      <Alert tone="error">{error}</Alert>
      {users.isPending && <Skeleton height={160} />}
      {users.data && list.length === 0 && <p className="muted">Nenhum usuário neste filtro.</p>}
      <ul className="admin-users">
        {list.map((u) => (
          <li key={u.id} className="admin-user">
            <div className="admin-user__head">
              <strong className="admin-user__email">{u.email}</strong>
              <span className={`badge ${STATUS[u.access_status].tone}`}>{STATUS[u.access_status].label}</span>
              {u.is_admin && <span className="badge badge--accent">Admin</span>}
              {!u.email_verified && <span className="badge">E-mail não confirmado</span>}
              {u.totp_enabled && <span className="badge">2FA</span>}
            </div>
            <dl className="admin-user__facts">
              <div>
                <dt>Cadastro</dt>
                <dd>{when(u.created_at)}</dd>
              </div>
              <div>
                <dt>Último acesso</dt>
                <dd>{when(u.last_seen_at)}</dd>
              </div>
              <div>
                <dt>Sessões ativas</dt>
                <dd>{u.active_sessions}</dd>
              </div>
              <div>
                <dt>Lançamentos</dt>
                <dd>{u.entries}</dd>
              </div>
            </dl>
            <div className="admin-user__actions">
              {u.access_status === "pending" && button(u, "approve", "Liberar acesso", "primary")}
              {u.access_status === "pending" && button(u, "block", "Recusar", "danger")}
              {u.access_status === "approved" && button(u, "block", "Bloquear", "danger", `Bloquear ${u.email}? A pessoa é desconectada.`)}
              {u.access_status === "blocked" && button(u, "unblock", "Desbloquear")}
              {!u.email_verified && button(u, "resend_verification", "Reenviar confirmação")}
              {!u.email_verified && button(u, "verify_email", "Marcar e-mail como confirmado")}
              {u.active_sessions > 0 && button(u, "revoke_sessions", "Encerrar sessões")}
              {!u.is_admin && button(u, "make_admin", "Tornar admin", "secondary", `Dar acesso de administração a ${u.email}?`)}
              {u.is_admin && button(u, "revoke_admin", "Remover admin")}
              {button(u, "delete", "Excluir conta", "danger", `Excluir a conta ${u.email} e todos os dados? Não é possível desfazer.`)}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EmailsTab() {
  const emails = useQuery({ queryKey: ["admin", "emails"], queryFn: moneyApi.adminEmails, refetchInterval: 30_000 });
  const [open, setOpen] = useState<string | null>(null);
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      announce("Link copiado");
    } catch {
      window.prompt("Copie o link:", text);
    }
  }
  return (
    <section className="card stack">
      <h2>E-mails enviados</h2>
      <p className="muted small" style={{ margin: 0 }}>
        Cópia dos e-mails dos últimos 30 dias, com o link de cada um. Atualiza a cada 30 segundos.
      </p>
      {emails.isPending && <Skeleton height={160} />}
      {emails.data && emails.data.length === 0 && <p className="muted">Nenhum e-mail enviado ainda.</p>}
      <ul className="items">
        {emails.data?.map((e) => (
          <li key={e.id} className="item item--stack">
            <button type="button" className="item__main" onClick={() => setOpen(open === e.id ? null : e.id)} aria-expanded={open === e.id}>
              <span className="item__title">{e.subject}</span>
              <span className="item__meta">
                {e.to} · {when(e.created_at)}
              </span>
            </button>
            {e.link && (
              <Button type="button" variant="secondary" onClick={() => void copy(e.link!)}>
                <Copy size={15} /> Copiar link
              </Button>
            )}
            {open === e.id && <pre className="email-body">{e.body}</pre>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function AdminPage() {
  const [params, setParams] = useSearchParams();
  // "feedback" é o endereço antigo da aba (links e favoritos de antes da v0.7.5).
  const requested = params.get("aba") === "feedback" ? "solicitacoes" : params.get("aba");
  const tab = (TABS.find((t) => t.key === requested)?.key ?? "usuarios") as Tab;
  const overview = useQuery({ queryKey: ["admin", "overview"], queryFn: moneyApi.adminOverview, refetchInterval: 60_000 });
  const data = overview.data;
  return (
    <>
      <PageHeader title="Administração" subtitle="Usuários, liberação de acesso, e-mails, solicitações e recados." />
      {overview.isError && <Alert tone="error">{errorMessage(overview.error)}</Alert>}
      {overview.isPending && (
        <LoadingRegion label="Carregando">
          <Skeleton height={100} />
        </LoadingRegion>
      )}
      {data && (
        <div className="kpis" style={{ marginBottom: 20 }}>
          <Kpi icon={<Users size={17} />} label="Usuários" value={String(data.users)} foot={`${data.new_7d} novo(s) em 7 dias`} />
          <Kpi icon={<ShieldAlert size={17} />} tone="expense" label="Aguardando liberação" value={String(data.pending)} foot={data.signup_approval ? "Beta fechado ativo" : "Cadastro livre"} />
          <Kpi icon={<Users size={17} />} tone="neutral" label="Ativos em 7 dias" value={String(data.active_7d)} foot={`${data.blocked} bloqueado(s)`} />
          <Kpi icon={<Inbox size={17} />} tone="neutral" label="Solicitações não lidas" value={String(data.feedback_new)} foot={`${data.unverified} e-mail(s) sem confirmação`} />
        </div>
      )}
      <nav className="page-tabs no-print" aria-label="Seções da administração" style={{ marginBottom: 20 }}>
        {TABS.map((t) => (
          <a
            key={t.key}
            href={`?aba=${t.key}`}
            aria-current={tab === t.key ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              setParams({ aba: t.key });
            }}
          >
            {t.label}
          </a>
        ))}
      </nav>
      {tab === "usuarios" && <UsersTab />}
      {tab === "emails" && <EmailsTab />}
      {tab === "solicitacoes" && <AdminSupport />}
      {tab === "recados" && <AdminAnnouncements />}
    </>
  );
}
