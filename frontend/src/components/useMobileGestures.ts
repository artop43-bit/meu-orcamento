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
  go: (dir: -1 | 1) => void;
  refresh: () => Promise<unknown>;
};

/** Desfaz o deslocamento do arrasto (chamado quando a nova página já está na tela). */
export function resetSwipe(el: HTMLElement | null) {
  if (!el) return;
  el.style.transition = "";
  el.style.transform = "";
  el.style.opacity = "";
}

/**
 * Gestos do celular sobre o conteúdo:
 * - deslizar para o lado troca de aba (a página acompanha o dedo);
 * - puxar para baixo no topo da página atualiza os dados.
 * No desktop não faz nada. Os gestos são atalhos: tudo continua acessível pelas abas e botões.
 */
export function useMobileGestures(
  contentRef: RefObject<HTMLElement | null>,
  pullRef: RefObject<HTMLElement | null>,
  options: Options,
) {
  const opts = useRef(options);
  useEffect(() => {
    opts.current = options;
  });

  useEffect(() => {
    const content = contentRef.current;
    const pull = pullRef.current;
    if (!content || !pull) return;
    const mobile = matchMedia(MOBILE);

    let mode: "idle" | "pending" | "swipe" | "pull" | "none" = "idle";
    let startX = 0;
    let startY = 0;
    let startT = 0;
    let lastDx = 0;
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

    function onStart(e: TouchEvent) {
      mode = "idle";
      if (!mobile.matches || e.touches.length !== 1 || refreshing) return;
      if (document.querySelector("dialog[open]")) return;
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      startT = e.timeStamp;
      lastDx = 0;
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
        const offset = opts.current.canGo(dx < 0 ? 1 : -1) ? dx : rubberBand(dx, 60);
        content!.style.transform = `translate3d(${offset}px, 0, 0)`;
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
        const width = content!.clientWidth;
        const dir = cancelled ? 0 : swipeResult(lastDx, e.timeStamp - startT, width);
        if (dir !== 0 && opts.current.canGo(dir)) {
          haptic("tap");
          if (prefersReducedMotion()) {
            opts.current.go(dir);
          } else {
            // Termina de empurrar a página para fora; a nova entra pelo outro lado (CSS .page).
            content!.style.transition = "transform 0.16s ease-in, opacity 0.16s ease-in";
            content!.style.transform = `translate3d(${dir === 1 ? -width : width}px, 0, 0)`;
            content!.style.opacity = "0.4";
            timers.push(window.setTimeout(() => opts.current.go(dir), 150));
          }
        } else {
          content!.style.transition = "transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)";
          content!.style.transform = "";
          timers.push(window.setTimeout(() => resetSwipe(content), 260));
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
  }, [contentRef, pullRef]);
}
