import { useEffect, useRef, type RefObject } from "react";

import { prefersReducedMotion } from "../lib/announce";
import { blocksSwipe, gestureAxis, PULL_TRIGGER, rubberBand, swipeResult } from "../lib/gestures";
import { haptic } from "../lib/haptics";

const MOBILE = "(max-width: 1023px)";
/** Faixa das bordas reservada ao gesto "voltar" do iPhone/Android. */
const EDGE = 24;

type Options = {
  /** Existe aba nessa direção? (1 = próxima, -1 = anterior) */
  canGo: (dir: -1 | 1) => boolean;
  /** Nome da tela que entra: aparece ao lado da página enquanto o dedo arrasta. */
  peekLabel: (dir: -1 | 1) => string;
  /** Adianta a tela vizinha (código e dados) assim que o arrasto começa. */
  prepare: (dir: -1 | 1) => void;
  /** Troca de tela. `from`: onde a nova tela começa (px), continuando o movimento do dedo. */
  go: (dir: -1 | 1, from: number) => void;
  refresh: () => Promise<unknown>;
};

/** Desfaz o deslocamento do arrasto (chamado quando a nova página já está na tela). */
export function resetSwipe(el: HTMLElement | null, peek?: HTMLElement | null) {
  for (const node of [el, peek]) {
    if (!node) continue;
    node.style.transition = "";
    node.style.transform = "";
    node.style.opacity = "";
  }
  if (peek) peek.hidden = true;
}

/**
 * Gestos do celular sobre o conteúdo:
 * - deslizar para o lado troca a aba de baixo: a página acompanha o dedo e a próxima entra
 *   colada a ela (nunca fica um vazio entre as duas);
 * - puxar para baixo no topo da página atualiza os dados.
 * No desktop não faz nada. Os gestos são atalhos: tudo continua acessível pelas abas e botões.
 */
export function useMobileGestures(
  contentRef: RefObject<HTMLElement | null>,
  pullRef: RefObject<HTMLElement | null>,
  peekRef: RefObject<HTMLElement | null>,
  options: Options,
) {
  const opts = useRef(options);
  useEffect(() => {
    opts.current = options;
  });

  useEffect(() => {
    const content = contentRef.current;
    const pull = pullRef.current;
    const peek = peekRef.current;
    if (!content || !pull || !peek) return;
    const mobile = matchMedia(MOBILE);

    let mode: "idle" | "pending" | "swipe" | "pull" | "none" = "idle";
    let startX = 0;
    let startY = 0;
    let startT = 0;
    let lastDx = 0;
    let peekDir: -1 | 0 | 1 = 0;
    let swipeAllowed = false;
    let pullAllowed = false;
    let armed = false;
    let refreshing = false;
    const timers: number[] = [];

    function showPull(distance: number) {
      pull!.style.transform = `translate(-50%, ${distance - 48}px)`;
      pull!.style.opacity = String(Math.min(1, distance / PULL_TRIGGER));
      pull!.style.setProperty("--pull-rotate", `${distance * 3}deg`);
    }

    function hidePull() {
      pull!.style.transition = "transform 0.2s ease, opacity 0.2s ease";
      showPull(0);
      timers.push(window.setTimeout(() => (pull!.style.transition = ""), 220));
    }

    /** Tela vizinha encostada na página, do lado que o dedo está revelando. */
    function showPeek(dir: -1 | 1, dx: number) {
      if (peekDir !== dir) {
        peekDir = dir;
        const title = peek!.querySelector(".swipe-peek__title");
        if (title) title.textContent = opts.current.peekLabel(dir);
        opts.current.prepare(dir);
        peek!.hidden = false;
      }
      const width = window.innerWidth;
      peek!.style.transform = `translate3d(${dir === 1 ? width + dx : -width + dx}px, 0, 0)`;
    }

    function hidePeek() {
      peekDir = 0;
      peek!.hidden = true;
    }

    function onStart(e: TouchEvent) {
      mode = "idle";
      if (!mobile.matches || e.touches.length !== 1 || refreshing) return;
      if (document.querySelector("dialog[open]")) return;
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      startT = e.timeStamp;
      lastDx = 0;
      peekDir = 0;
      armed = false;
      swipeAllowed = startX > EDGE && startX < window.innerWidth - EDGE && !blocksSwipe(e.target, content!);
      pullAllowed = window.scrollY <= 0;
      mode = "pending";
    }

    function onMove(e: TouchEvent) {
      if (mode === "idle" || mode === "none") return;
      const t = e.touches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;

      if (mode === "pending") {
        const axis = gestureAxis(dx, dy);
        if (!axis) return;
        if (axis === "x" && swipeAllowed) {
          mode = "swipe";
          content!.style.transition = "none";
          peek!.style.transition = "none";
        } else if (axis === "y" && dy > 0 && pullAllowed && window.scrollY <= 0) {
          mode = "pull";
          pull!.style.transition = "none";
        } else {
          mode = "none";
          return;
        }
      }

      if (mode === "swipe") {
        lastDx = dx;
        // Sem aba nessa direção: a página resiste (efeito elástico) em vez de andar.
        const dir = dx < 0 ? 1 : -1;
        const can = opts.current.canGo(dir);
        const offset = can ? dx : rubberBand(dx, 60);
        content!.style.transform = `translate3d(${offset}px, 0, 0)`;
        if (can) showPeek(dir, dx);
        else if (peekDir !== 0) hidePeek();
      } else {
        const distance = rubberBand(Math.max(dy, 0), 140);
        showPull(distance);
        const nowArmed = distance >= PULL_TRIGGER;
        if (nowArmed && !armed) haptic("tap");
        armed = nowArmed;
      }
    }

    function onEnd(e: TouchEvent, cancelled = false) {
      if (mode === "swipe") {
        const width = window.innerWidth;
        const dir = cancelled ? 0 : swipeResult(lastDx, e.timeStamp - startT, width);
        if (dir !== 0 && opts.current.canGo(dir)) {
          haptic("tap");
          // Troca na hora: a nova tela começa onde a vizinha estava e termina o movimento.
          const from = prefersReducedMotion() ? 0 : dir === 1 ? width + Math.min(lastDx, 0) : -width + Math.max(lastDx, 0);
          peekDir = 0;
          opts.current.go(dir, from);
        } else {
          const ease = "transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)";
          content!.style.transition = ease;
          content!.style.transform = "";
          if (peekDir !== 0) {
            peek!.style.transition = ease;
            peek!.style.transform = `translate3d(${peekDir === 1 ? width : -width}px, 0, 0)`;
          }
          peekDir = 0;
          timers.push(window.setTimeout(() => resetSwipe(content, peek), 260));
        }
      } else if (mode === "pull") {
        if (armed && !cancelled) {
          refreshing = true;
          pull!.classList.add("is-refreshing");
          pull!.style.transition = "transform 0.2s ease";
          showPull(PULL_TRIGGER);
          // Tempo mínimo para o indicador não piscar quando a resposta é instantânea.
          const minimum = new Promise((resolve) => setTimeout(resolve, 600));
          Promise.allSettled([opts.current.refresh(), minimum]).then(() => {
            refreshing = false;
            pull!.classList.remove("is-refreshing");
            hidePull();
          });
        } else {
          hidePull();
        }
      }
      mode = "idle";
    }

    const onCancel = (e: TouchEvent) => onEnd(e, true);
    content.addEventListener("touchstart", onStart, { passive: true });
    content.addEventListener("touchmove", onMove, { passive: true });
    content.addEventListener("touchend", onEnd);
    content.addEventListener("touchcancel", onCancel);
    return () => {
      content.removeEventListener("touchstart", onStart);
      content.removeEventListener("touchmove", onMove);
      content.removeEventListener("touchend", onEnd);
      content.removeEventListener("touchcancel", onCancel);
      timers.forEach(clearTimeout);
    };
  }, [contentRef, pullRef, peekRef]);
}
