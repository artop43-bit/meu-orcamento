import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { installFormErrors } from "./lib/formErrors";
import { captureInstallPrompt } from "./lib/install";
import { startOfflineSync } from "./lib/offline";
import { installErrorReporting } from "./lib/errorReport";
import { applyPrefs } from "./lib/prefs";
import "./theme.css";
import "./styles.css";

// Tema, cor, tamanho do texto e privacidade escolhidos neste aparelho.
applyPrefs();

// Erros de formulário em mensagens do app, junto do campo (sem balões do navegador).
installFormErrors();

// Erros inesperados das telas vão para Administração › Erros (só no site publicado).
installErrorReporting();

// Convite de instalação ("Instalar no computador"): chega só uma vez, logo no início.
captureInstallPrompt();

// Dados ficam "frescos" por 30 s: navegar entre páginas não recarrega tudo a cada toque.
// Depois de salvar algo, as telas afetadas são recarregadas na hora (invalidateQueries).
// Gravações rodam mesmo sem rede: sem internet, a fila do aparelho (lib/offline) guarda o
// lançamento; com a pausa padrão da biblioteca, ele ficaria preso sem aviso.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000 }, mutations: { networkMode: "always" } },
});

// Lançamentos feitos sem internet sobem sozinhos quando a conexão volta; depois, as telas se atualizam.
startOfflineSync(() => void queryClient.invalidateQueries({ queryKey: ["budget"] }));

// App instalável e sem internet: o service worker só roda no site publicado (no desenvolvimento
// ele atrapalharia a atualização automática das telas).
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
  // Com sinal fraco a tela recebe os últimos dados guardados; quando a resposta de verdade
  // chega, o service worker avisa e as telas abertas se atualizam.
  // No máximo uma atualização a cada 10 s, para o sinal fraco não virar uma enxurrada de pedidos.
  let lastRefresh = 0;
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type !== "api-atualizada" || Date.now() - lastRefresh < 10_000) return;
    lastRefresh = Date.now();
    void queryClient.invalidateQueries();
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
