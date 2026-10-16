import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { authApi } from "../api/auth";
import { errorMessage } from "../api/client";
import { Alert, AuthLayout, Button, Field } from "../components/ui";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      setDone((await authApi.forgotPassword(email)).message);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Esqueci minha senha">
      {done ? (
        <>
          <Alert tone="success">{done}</Alert>
          <p className="muted">O link para criar uma nova senha vale por 1 hora.</p>
        </>
      ) : (
        <form onSubmit={submit} className="form">
          <p className="muted">Informe seu e-mail e enviaremos um link para criar uma nova senha.</p>
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
          <Button type="submit" loading={loading}>
            Enviar link
          </Button>
        </form>
      )}
      <p className="links">
        <Link to="/entrar">Voltar para o login</Link>
      </p>
    </AuthLayout>
  );
}
