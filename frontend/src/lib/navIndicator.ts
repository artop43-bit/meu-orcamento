/**
 * Marcador que desliza até o item ativo (v1.6.5): menu lateral, barra de abas do celular,
 * submenus em pílula e abas das telas. Um <span class="nav-pill"> por grupo, posicionado por
 * transform (animado pelo navegador fora do processamento principal) e com efeito de mola no
 * CSS. Funciona para o documento inteiro: novos grupos e trocas de item ativo são percebidos
 * sozinhos. Com "reduzir movimento", o marcador só muda de lugar, sem animar.
 */
export const PILL_GROUPS = ".tabbar, .sidebar nav, .page-tabs, .group-tabs";
const ACTIVE = ".active, [aria-current='page']";

export type Box = { x: number; y: number; w: number; h: number };

/** Posição do item ativo dentro do grupo (considera a rolagem do grupo). */
export function boxWithin(item: DOMRect, group: DOMRect, scrollLeft: number, scrollTop: number, borderLeft = 0, borderTop = 0): Box {
  return {
    x: Math.round(item.left - group.left - borderLeft + scrollLeft),
    y: Math.round(item.top - group.top - borderTop + scrollTop),
    w: Math.round(item.width),
    h: Math.round(item.height),
  };
}

/** O item ativo mais específico (no menu lateral, o subitem vale mais que o grupo). */
function activeItem(group: HTMLElement): HTMLElement | null {
  const all = [...group.querySelectorAll<HTMLElement>(ACTIVE)].filter((el) => el.offsetParent !== null && !el.classList.contains("nav-pill"));
  return all.length ? all[all.length - 1]! : null;
}

function place(group: HTMLElement) {
  let pill = group.querySelector<HTMLElement>(":scope > .nav-pill");
  const item = activeItem(group);
  if (!item) {
    if (pill) pill.style.opacity = "0";
    return;
  }
  if (!pill) {
    pill = document.createElement("span");
    pill.className = "nav-pill";
    pill.setAttribute("aria-hidden", "true");
    group.prepend(pill);
    group.dataset.pill = "";
  }
  const cs = getComputedStyle(group);
  const box = boxWithin(item.getBoundingClientRect(), group.getBoundingClientRect(), group.scrollLeft, group.scrollTop, parseFloat(cs.borderLeftWidth) || 0, parseFloat(cs.borderTopWidth) || 0);
  // Margem interna opcional (ex.: na barra de abas, o marcador não encosta nas bordas).
  const inset = parseFloat(cs.getPropertyValue("--pill-inset")) || 0;
  if (inset) Object.assign(box, { x: box.x + inset, y: box.y + inset, w: box.w - inset * 2, h: box.h - inset * 2 });
  const first = pill.dataset.ready !== "1";
  if (first) pill.style.transition = "none";
  pill.style.opacity = "1";
  pill.style.width = `${box.w}px`;
  pill.style.height = `${box.h}px`;
  pill.style.transform = `translate3d(${box.x}px, ${box.y}px, 0)`;
  if (first) {
    void pill.offsetWidth;
    pill.style.transition = "";
    pill.dataset.ready = "1";
  }
}

export function installNavIndicator(root: Document = document): () => void {
  let queued = false;
  const update = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      root.querySelectorAll<HTMLElement>(PILL_GROUPS).forEach(place);
    });
  };
  const mutation = new MutationObserver((records) => {
    // Ignora as mudanças do próprio marcador.
    if (records.every((r) => r.target instanceof HTMLElement && r.target.classList.contains("nav-pill"))) return;
    update();
  });
  mutation.observe(root.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-current", "aria-expanded"] });
  const resize = new ResizeObserver(update);
  resize.observe(root.body);
  window.addEventListener("resize", update);
  update();
  return () => {
    mutation.disconnect();
    resize.disconnect();
    window.removeEventListener("resize", update);
  };
}
