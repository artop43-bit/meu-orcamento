import { Link } from "react-router";

import { useMe } from "../api/auth";

export default function Home() {
  const { data: user } = useMe();

  return (
    <div className="stack">
      <h1>Olá!</h1>
      <p className="muted">
        Você entrou como <strong>{user?.email}</strong>. O painel do orçamento chega na próxima
        fase.
      </p>
      {user && !user.totp_enabled && (
        <section className="card">
          <h2>Proteja sua conta</h2>
          <p className="muted">
            Seus dados financeiros merecem uma camada extra de proteção. Ative a verificação em
            duas etapas.
          </p>
          <Link className="btn btn--primary" to="/seguranca">
            Configurar agora
          </Link>
        </section>
      )}
    </div>
  );
}
