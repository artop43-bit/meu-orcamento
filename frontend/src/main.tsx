import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { installFormErrors } from "./lib/formErrors";
import { applyPrefs } from "./lib/prefs";
import "./styles.css";

// Tema, cor, tamanho do texto e privacidade escolhidos neste aparelho.
applyPrefs();

// Erros de formulário em mensagens do app, junto do campo (sem balões do navegador).
installFormErrors();

// Dados ficam "frescos" por 30 s: navegar entre páginas não recarrega tudo a cada toque.
// Depois de salvar algo, as telas afetadas são recarregadas na hora (invalidateQueries).
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
