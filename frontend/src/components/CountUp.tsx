import { useEffect, useRef, useState, type ReactNode } from "react";

import { easeOut, formatLike, parseFormatted, shouldAnimate } from "../lib/countUp";

/**
 * Mostra `text` com o número subindo até o valor (v1.6.5): na primeira vez, a partir de zero;
 * nas trocas seguintes, do valor anterior ao novo. Leitores de tela leem só o valor final.
 */
export function CountUp({ text, duration = 650 }: { text: string; duration?: number }) {
  const [shown, setShown] = useState(text);
  const previous = useRef<number | null>(null);
  useEffect(() => {
    const target = parseFormatted(text);
    const first = previous.current === null;
    const from = previous.current ?? 0;
    previous.current = target?.value ?? null;
    if (!target || !shouldAnimate() || from === target.value) {
      setShown(text);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const ms = first ? duration : duration * 0.7;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      setShown(t >= 1 ? text : formatLike(target, from + (target.value - from) * easeOut(t)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, duration]);
  if (shown === text) return <>{text}</>;
  return (
    <>
      <span aria-hidden>{shown}</span>
      <span className="sr-only">{text}</span>
    </>
  );
}

/** Para valores que podem não ser texto (ex.: elementos com ícones): só anima texto puro. */
export function maybeCountUp(value: ReactNode): ReactNode {
  return typeof value === "string" ? <CountUp text={value} /> : value;
}
