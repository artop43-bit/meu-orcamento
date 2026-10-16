import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { authApi } from "../api/auth";
import { errorMessage } from "../api/client";
import { Alert, AuthLayout } from "../components/ui";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<{ tone: "info" | "success" | "error"; text: string }>({
    tone: "info",
    text: "Confirmando seu e-mail…",
  });
  // O StrictMode roda efeitos duas vezes em desenvolvimento; o link é de uso único.
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    if (!token) {
      setState({ tone: "error", text: "Link incompleto. Abra o link direto do e-mail." });
      return;
    }
    authApi
      .verifyEmail(token)
      .then((r) => setState({ tone: "success", text: r.message }))
      .catch((err) => setState({ tone: "error", text: errorMessage(err) }));
  }, [token]);

  return (
    <AuthLayout title="Confirmação de e-mail">
      <Alert tone={state.tone}>{state.text}</Alert>
      <p className="links">
        <Link to="/entrar">Ir para o login</Link>
      </p>
    </AuthLayout>
  );
}
