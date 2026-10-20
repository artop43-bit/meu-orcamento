import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, errorMessage } from "../api/client";
import { Alert, AuthLayout, Button } from "../components/ui";

/** Link "Não quero mais receber" dos e-mails de aviso (sem login). */
export function Unsubscribe() {
  const [params] = useSearchParams();
  const token = params.get("t") ?? "";
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api
      .post<{ message: string }>("/notifications/unsubscribe", { token })
      .then((r) => setState({ ok: true, text: r.message }))
      .catch((err) => setState({ ok: false, text: errorMessage(err) }));
  }, [token]);

  return (
    <AuthLayout title="Avisos por e-mail">
      {!state && <p className="muted">Processando…</p>}
      {state && <Alert tone={state.ok ? "success" : "error"}>{state.text}</Alert>}
      <p className="muted small">
        Para escolher quais avisos receber, entre no app e abra <Link to="/ajustes/preferencias">Ajustes › Preferências</Link>.
      </p>
    </AuthLayout>
  );
}

/** Link "Não fui eu" do aviso de novo acesso: encerra as sessões e leva à nova senha. */
export function NotMe() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function protect() {
    setBusy(true);
    setError("");
    try {
      const result = await api.post<{ message: string; reset_token: string }>("/auth/not-me", { token });
      navigate(`/redefinir-senha?token=${encodeURIComponent(result.reset_token)}&protecao=1`, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Proteger a conta">
      <Alert tone="error">{error}</Alert>
      <p>Se você não reconhece o acesso informado no e-mail, proteja a conta agora. Isso vai:</p>
      <ul className="small">
        <li>encerrar todas as sessões abertas, em qualquer aparelho;</li>
        <li>levar você à criação de uma nova senha.</li>
      </ul>
      <p className="muted small">Depois, recomendamos ativar a verificação em duas etapas em Ajustes › Segurança.</p>
      <Button type="button" block loading={busy} onClick={() => void protect()} disabled={!token}>
        Encerrar sessões e criar nova senha
      </Button>
    </AuthLayout>
  );
}
