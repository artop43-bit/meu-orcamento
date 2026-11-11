/**
 * Velocidade das telas com usuários reais (v1.7.5).
 *
 * A cada troca de tela mede quanto ela levou para ficar pronta (dados carregados e desenhados)
 * e a pior travada no caminho. Vai para o servidor só o nome da tela, de uma lista fixa, e os
 * milissegundos; o servidor soma por dia. Nada identifica a pessoa (Administração › Erros
 * mostra as médias). Não mede em testes automáticos.
 */
const SCREENS = new Set([
  "orcamento", "calendario", "cartoes", "contas", "revisar", "busca", "mensagens", "dividas", "divisoes", "metas", "historico",
  "analises", "investimentos", "ajustes", "relatorio", "admin",
]); // prettier-ignore

export type PerfSample = { screen: string; load_ms: number; frame_ms: number };

const queue: PerfSample[] = [];
let timer: ReturnType<typeof setTimeout> | undefined;

/** "/orcamento/2026-11" → "orcamento"; telas fora da lista viram "outras". */
export function screenOf(pathname: string): string {
  const first = pathname.split("/").filter(Boolean)[0] ?? "orcamento";
  return SCREENS.has(first) ? first : "outras";
}

export function flushPerf() {
  if (timer) clearTimeout(timer);
  timer = undefined;
  if (queue.length === 0) return;
  const samples = queue.splice(0, 20);
  void fetch("/api/perf", {
    method: "POST",
    credentials: "include",
    keepalive: true,
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
    body: JSON.stringify({ samples }),
  }).catch(() => undefined);
}

export function recordPerf(sample: PerfSample) {
  if (typeof navigator !== "undefined" && navigator.webdriver) return;
  if (!(sample.load_ms > 0) || sample.load_ms > 60_000) return;
  queue.push({ screen: sample.screen, load_ms: Math.round(sample.load_ms), frame_ms: Math.round(Math.min(sample.frame_ms, 5000)) });
  if (queue.length >= 10) flushPerf();
  else if (!timer) timer = setTimeout(flushPerf, 30_000);
}

/** Acompanha uma navegação: chame `done()` quando a tela estiver pronta. */
export function startMeasure(pathname: string, first: boolean): { done: () => void; cancel: () => void } {
  const start = first ? 0 : performance.now();
  let worst = 0;
  let last = performance.now();
  let running = true;
  let frames = 0;
  const tick = (now: number) => {
    if (!running) return;
    if (frames++ > 0) worst = Math.max(worst, now - last);
    last = now;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return {
    done() {
      if (!running) return;
      running = false;
      // Aba em segundo plano não desenha: a medida não vale.
      if (document.visibilityState !== "visible") return;
      recordPerf({ screen: screenOf(pathname), load_ms: performance.now() - start, frame_ms: worst });
    },
    cancel() {
      running = false;
    },
  };
}

export function installPerfReport() {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushPerf();
  });
}

/** Só para os testes. */
export function pendingPerf(): PerfSample[] {
  return [...queue];
}
