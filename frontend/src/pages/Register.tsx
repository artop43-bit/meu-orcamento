import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { authApi } from "../api/auth";
import { errorMessage } from "../api/client";
import { Alert, AuthLayout, Button, Field } from "../components/ui";

export const MIN_PASSWORD = 10;

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [accepted, setAccepted] = useState(false);
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
    if (!accepted) {
      setError("Para criar a conta, aceite os Termos de uso e a Política de privacidade.");
      return;
    }
    setLoading(true);
    try {
      const result = await authApi.register(email, password, accepted);
      setDone(result.message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <AuthLayout title="Verifique seu e-mail">
        <Alert tone="success">{done}</Alert>
        <p className="muted">
          Um link de confirmação foi enviado para <strong>{email}</strong> (válido por 24 horas). Durante o período de testes, o
          acesso também precisa ser liberado pela administração; você receberá um e-mail quando isso acontecer.
        </p>
        <p className="links">
          <Link to="/entrar">Ir para o login</Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Criar conta">
      <form onSubmit={submit} className="form">
        <Alert tone="error">{error}</Alert>
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
          autoComplete="new-password"
          minLength={MIN_PASSWORD}
          maxLength={128}
          required
          hint={`Pelo menos ${MIN_PASSWORD} caracteres. Uma frase longa é mais segura e fácil de lembrar.`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Field
          label="Confirme a senha"
          name="confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <label className="check small">
          <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} required />
          <span>
            Li e aceito os{" "}
            <Link to="/termos" target="_blank">
              Termos de uso
            </Link>{" "}
            e a{" "}
            <Link to="/privacidade" target="_blank">
              Política de privacidade
            </Link>
            .
          </span>
        </label>
        <Button type="submit" loading={loading}>
          Criar conta
        </Button>
      </form>
      <p className="links">
        Já tem conta? <Link to="/entrar">Entrar</Link>
      </p>
    </AuthLayout>
  );
}
