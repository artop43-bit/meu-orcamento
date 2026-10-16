import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router";

import { authApi, ME_KEY } from "../api/auth";
import { ApiError, errorMessage } from "../api/client";
import { Alert, AuthLayout, Button, Field } from "../components/ui";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice ?? "";
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [unverified, setUnverified] = useState(false);
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  async function finish(result: Awaited<ReturnType<typeof authApi.login>>) {
    if (result.status === "2fa_required") {
      setChallenge(result.challenge);
      return;
    }
    queryClient.setQueryData(ME_KEY, result.user);
    navigate("/", { replace: true });
  }

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    setInfo("");
    setUnverified(false);
    setLoading(true);
    try {
      await finish(await authApi.login(email, password));
    } catch (err) {
      setError(errorMessage(err));
      setUnverified(err instanceof ApiError && err.code === "email_not_verified");
    } finally {
      setLoading(false);
    }
  }

  async function submitCode(event: FormEvent) {
    event.preventDefault();
    if (!challenge) return;
    setError("");
    setLoading(true);
    try {
      await finish(await authApi.login2fa(challenge, code));
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_token") {
        // O desafio expirou (5 min): volta para a senha.
        setChallenge(null);
        setCode("");
      }
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function resend() {
    const result = await authApi.resendVerification(email).catch((err) => ({
      message: errorMessage(err),
    }));
    setInfo(result.message);
    setUnverified(false);
    setError("");
  }

  if (challenge) {
    return (
      <AuthLayout title="Verificação em duas etapas">
        <p className="muted">
          Digite o código de 6 dígitos do seu aplicativo autenticador, ou um código de recuperação.
        </p>
        <form onSubmit={submitCode} className="form">
          <Alert tone="error">{error}</Alert>
          <Field
            label="Código"
            name="code"
            autoComplete="one-time-code"
            inputMode="text"
            autoFocus
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button type="submit" loading={loading}>
            Confirmar
          </Button>
        </form>
        <p className="links">
          <button type="button" className="link" onClick={() => setChallenge(null)}>
            Voltar
          </button>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Entrar">
      <form onSubmit={submitPassword} className="form">
        {error && (
          <Alert tone="error">
            {error}
            {unverified && (
              <>
                {" "}
                <button type="button" className="link" onClick={resend}>
                  Reenviar e-mail de confirmação
                </button>
              </>
            )}
          </Alert>
        )}
        <Alert tone="success">{info}</Alert>
        {!info && <Alert tone="success">{notice}</Alert>}
        <Field
          label="E-mail"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Senha"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" loading={loading}>
          Entrar
        </Button>
      </form>
      <p className="links">
        <Link to="/esqueci-senha">Esqueci minha senha</Link>
        <Link to="/cadastro">Criar conta</Link>
      </p>
    </AuthLayout>
  );
}
