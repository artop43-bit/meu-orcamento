import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { authApi } from "../api/auth";
import { errorMessage } from "../api/client";
import { Alert, AuthLayout, Button, Field } from "../components/ui";
import { MIN_PASSWORD } from "./Register";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    setLoading(true);
    try {
      setDone((await authApi.resetPassword(token, password)).message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Criar nova senha">
      {done ? (
        <Alert tone="success">{done}</Alert>
      ) : (
        <form onSubmit={submit} className="form">
          <Alert tone="error">{error}</Alert>
          <Field
            label="Nova senha"
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={MIN_PASSWORD}
            maxLength={128}
            required
            hint={`Pelo menos ${MIN_PASSWORD} caracteres.`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Field
            label="Confirme a nova senha"
            name="confirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <Button type="submit" loading={loading} disabled={!token}>
            Salvar nova senha
          </Button>
        </form>
      )}
      <p className="links">
        <Link to="/entrar">Ir para o login</Link>
      </p>
    </AuthLayout>
  );
}
