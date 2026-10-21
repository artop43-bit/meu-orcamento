import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { installFormErrors } from "./lib/formErrors";
import { captureInstallPrompt } from "./lib/install";
import { startOfflineSync } from "./lib/offline";
import { applyPrefs } from "./lib/prefs";
import "./theme.css";
import "./styles.css";

// Tema, cor, tamanho do texto e privacidade escolhidos neste aparelho.
applyPrefs();

// Erros de formulário em mensagens do app, junto do campo (sem balões do navegador).
installFormErrors();

// Convite de instalação ("Instalar no computador"): chega só uma vez, logo no início.
captureInstallPrompt();

// Dados ficam "frescos" por 30 s: navegar entre páginas não recarrega tudo a cada toque.
// Depois de salvar algo, as telas afetadas são recarregadas na hora (invalidateQueries).
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } });

// Lançamentos feitos sem internet sobem sozinhos quando a conexão volta; depois, as telas se atualizam.
startOfflineSync(() => void queryClient.invalidateQueries({ queryKey: ["budget"] }));

// App instalável e sem internet: o service worker só roda no site publicado (no desenvolvimento
// ele atrapalharia a atualização automática das telas).
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
