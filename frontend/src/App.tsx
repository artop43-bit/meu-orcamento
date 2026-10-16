import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./api/client";

type Health = { status: string; database?: string };

function StatusLine({ label, query }: { label: string; query: ReturnType<typeof useHealth> }) {
  const text = query.isPending ? "verificando…" : query.isError ? "indisponível" : "ok";
  const tone = query.isPending ? "pending" : query.isError ? "error" : "ok";
  return (
    <li className={`status status--${tone}`}>
      <span>{label}</span>
      <strong>{text}</strong>
    </li>
  );
}

function useHealth(path: string) {
  return useQuery({ queryKey: ["health", path], queryFn: () => apiGet<Health>(path), retry: false });
}

export default function App() {
  const api = useHealth("/health");
  const db = useHealth("/health/db");

  return (
    <main className="container">
      <h1>Meu Orçamento</h1>
      <p className="muted">Base do projeto rodando. Próximo passo: contas de usuário.</p>
      <ul className="status-list">
        <StatusLine label="API" query={api} />
        <StatusLine label="Banco de dados" query={db} />
      </ul>
    </main>
  );
}
