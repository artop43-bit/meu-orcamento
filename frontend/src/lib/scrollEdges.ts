/**
 * Faixas que deslizam para o lado (abas, seções, seletor de calculadoras) ganham um esmaecido
 * na borda onde ainda há conteúdo escondido (v1.6.5). Marca o elemento com data-fade =
 * "start" | "end" | "both" | "none"; o CSS (visual.css) aplica a máscara. Um único ouvinte de
 * rolagem e um único observador para o documento inteiro.
 */
export const STRIP_SELECTOR = ".page-tabs, .tabs, .analysis__nav, .calc-picker, .calc-bars, .chips";

export function fadeFor(scrollLeft: number, clientWidth: number, scrollWidth: number): "start" | "end" | "both" | "none" {
  const hiddenStart = scrollLeft > 2;
  const hiddenEnd = scrollLeft + clientWidth < scrollWidth - 2;
  return hiddenStart && hiddenEnd ? "both" : hiddenStart ? "start" : hiddenEnd ? "end" : "none";
}

function update(el: HTMLElement) {
  const fade = fadeFor(el.scrollLeft, el.clientWidth, el.scrollWidth);
  if (el.dataset.fade !== fade) el.dataset.fade = fade;
}

export function installScrollEdges(root: Document = document): () => void {
  const resize = new ResizeObserver((entries) => entries.forEach((e) => update(e.target as HTMLElement)));
  const watched = new WeakSet<Element>();
  const scan = () => {
    root.querySelectorAll<HTMLElement>(STRIP_SELECTOR).forEach((el) => {
      if (!watched.has(el)) {
        watched.add(el);
        resize.observe(el);
      }
      update(el);
    });
  };
  let queued = false;
  const mutation = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      scan();
    });
  });
  const onScroll = (e: Event) => {
    const el = e.target as HTMLElement;
    if (el instanceof HTMLElement && el.matches(STRIP_SELECTOR)) update(el);
  };
  scan();
  mutation.observe(root.body, { childList: true, subtree: true });
  root.addEventListener("scroll", onScroll, { capture: true, passive: true });
  return () => {
    mutation.disconnect();
    resize.disconnect();
    root.removeEventListener("scroll", onScroll, { capture: true });
  };
}
