import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { authApi, ME_KEY, type User } from "../api/auth";
import { errorMessage } from "../api/client";
import { Alert, Button, Field } from "./ui";

const SESSIONS_KEY = ["auth", "sessions"] as const;
const EVENTS_KEY = ["auth", "events"] as const;

const EVENT_LABELS: Record<string, string> = {
  login: "Entrou na conta",
  login_failed: "Tentativa de login com senha errada",
  login_2fa_failed: "Código de verificação errado no login",
  email_verified: "E-mail confirmado",
  password_changed: "Senha alterada",
  password_reset: "Senha redefinida pelo e-mail",
  "2fa_enabled": "Verificação em duas etapas ativada",
  "2fa_disabled": "Verificação em duas etapas desativada",
  recovery_codes_regenerated: "Novos códigos de recuperação gerados",
  session_revoked: "Uma sessão foi encerrada",
  sessions_revoked: "Outras sessões foram encerradas",
};

/** "Chrome no Windows" a partir do user-agent (aproximado, só para exibição). */
export function describeDevice(userAgent: string | null): string {
  if (!userAgent) return "Dispositivo desconhecido";
  const ua = userAgent;
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /OPR\//.test(ua)
      ? "Opera"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Chrome\//.test(ua)
          ? "Chrome"
          : /Safari\//.test(ua)
            ? "Safari"
            : "Navegador";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Android/.test(ua)
      ? "Android"
      : /iPhone|iPad/.test(ua)
        ? "iOS"
        : /Mac OS X/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "sistema desconhecido";
  return `${browser} no ${os}`;
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function SessionsSection() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: SESSIONS_KEY, queryFn: authApi.sessions });
  const [error, setError] = useState("");

  async function run(action: () => Promise<void>) {
    setError("");
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
      await queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const others = (sessions.data ?? []).filter((s) => !s.current);

  return (
    <div className="stack">
      <Alert tone="error">{error}</Alert>
      {sessions.isPending && <p className="muted">Carregando…</p>}
      <ul className="items">
        {sessions.data?.map((s) => (
          <li key={s.id} className="item">
            <span className="item__main">
              <span className="item__title">
                {describeDevice(s.user_agent)} {s.current && <span className="badge badge--accent">este dispositivo</span>}
              </span>
              <span className="item__meta">
                {s.ip ?? "IP desconhecido"} · ativa em {when(s.last_seen_at)} · desde {when(s.created_at)}
              </span>
            </span>
            {!s.current && (
              <button type="button" className="link small" onClick={() => run(() => authApi.revokeSession(s.id))}>
                Encerrar
              </button>
            )}
          </li>
        ))}
      </ul>
      {others.length > 0 && (
        <div>
          <Button type="button" variant="secondary" onClick={() => run(authApi.revokeOtherSessions)}>
            Encerrar todas as outras sessões
          </Button>
        </div>
      )}
    </div>
  );
}

export function ActivitySection() {
  const events = useQuery({ queryKey: EVENTS_KEY, queryFn: authApi.events });
  if (events.isPending) return <p className="muted">Carregando…</p>;
  if (events.isError) return <Alert tone="error">{errorMessage(events.error)}</Alert>;
  if (events.data.length === 0) return <p className="muted">Nenhuma atividade registrada.</p>;
  return (
    <ul className="items items--scroll" tabIndex={0} aria-label="Atividade recente da conta">
      {events.data.map((e, i) => (
        <li key={i} className="item">
          <span className="item__main">
            <span className={`item__title ${e.event.endsWith("_failed") ? "tone--error" : ""}`}>
              {EVENT_LABELS[e.event] ?? e.event}
            </span>
            <span className="item__meta">
              {when(e.created_at)} · {describeDevice(e.user_agent)} · {e.ip ?? "IP desconhecido"}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DeleteAccountSection({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.deleteAccount(password, user.totp_enabled ? code : null);
      // Primeiro navega e marca como deslogado; só depois limpa o cache (a ordem importa:
      // limpar antes desconecta a tela da consulta do usuário e ela não sai daqui).
      navigate("/entrar", { replace: true, state: { notice: "Sua conta e todos os seus dados foram excluídos." } });
      queryClient.setQueryData(ME_KEY, null);
      queryClient.clear();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <div className="stack">
        <p className="muted">
          Apaga sua conta e <strong>todos</strong> os seus dados: lançamentos, metas, investimentos e histórico. Não dá
          para desfazer. Antes, se quiser, baixe o <Link to="/dados">backup completo</Link>.
        </p>
        <div>
          <Button type="button" variant="danger" onClick={() => setOpen(true)}>
            Excluir minha conta
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      <Alert tone="error">{error}</Alert>
      <Field
        label="Sua senha"
        name="delete-password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {user.totp_enabled && (
        <Field
          label="Código do aplicativo autenticador"
          name="delete-code"
          autoComplete="one-time-code"
          required
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
      )}
      <Field
        label='Digite EXCLUIR para confirmar'
        name="delete-confirm"
        required
        value={confirmText}
        onChange={(e) => setConfirmText(e.target.value)}
      />
      <div className="row">
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" loading={loading} disabled={confirmText.trim().toUpperCase() !== "EXCLUIR"}>
          Excluir definitivamente
        </Button>
      </div>
    </form>
  );
}
