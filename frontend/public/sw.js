// Service worker do Meu Orçamento (v1.0): abre sem internet com os últimos dados e mostra as
// notificações no aparelho. As respostas da API ficam só neste aparelho e são apagadas ao sair.
const SHELL = "shell-v1";
const ASSETS = "assets-v1";
const API = "api-v1";
const SHELL_FILES = ["/", "/index.html", "/aparencia.js", "/favicon.svg", "/manifest.webmanifest", "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  const keep = [SHELL, ASSETS, API];
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => !keep.includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

// Sinal fraco (v1.4.3): passando disto sem resposta, a tela recebe a última resposta guardada.
const SLOW_MS = 5000;

// Primeiro a rede; sem conexão, a última resposta guardada. Com a rede lenta demais, também
// a guardada, e a busca continua: quando a resposta chega, o app é avisado e atualiza a tela.
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const network = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  });
  let timer;
  const slow = new Promise((resolve) => {
    timer = setTimeout(() => resolve("lento"), SLOW_MS);
  });
  try {
    const first = await Promise.race([network, slow]);
    if (first !== "lento") return first;
    const cached = await cache.match(request);
    if (!cached) return await network;
    network
      .then(async (response) => {
        if (!response.ok) return;
        const clients = await self.clients.matchAll({ type: "window" });
        clients.forEach((client) => client.postMessage({ type: "api-atualizada" }));
      })
      .catch(() => undefined);
    return cached;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    // Arquivos (fotos, comprovantes) e o que muda a sessão não ficam guardados.
    if (url.pathname.startsWith("/api/files/") || (url.pathname.startsWith("/api/auth/") && url.pathname !== "/api/auth/me")) return;
    event.respondWith(networkFirst(request, API));
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    // Arquivos com hash no nome nunca mudam: guarda na primeira vez.
    event.respondWith(
      caches.open(ASSETS).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
      }),
    );
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => (await caches.match("/index.html")) || Response.error()),
    );
  }
});

// Ao sair da conta, o app pede para apagar os dados guardados neste aparelho.
self.addEventListener("message", (event) => {
  if (event.data === "limpar-dados") event.waitUntil(caches.delete(API));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Meu Orçamento", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Meu Orçamento", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag || undefined,
      data: { url: data.url || "/" },
      lang: "pt-BR",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
