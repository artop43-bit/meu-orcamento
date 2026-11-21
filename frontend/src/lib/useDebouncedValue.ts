import { useEffect, useState } from "react";

export function scheduleDebouncedCallback<T>(
  value: T,
  delayMs: number,
  onFlush: (value: T) => void,
): () => void {
  const timer = globalThis.setTimeout(() => onFlush(value), delayMs);
  return () => globalThis.clearTimeout(timer);
}

/** Adia a propagação de `value` por `delay` ms até a pessoa parar de digitar. */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [current, setCurrent] = useState(value);
  useEffect(() => scheduleDebouncedCallback(value, delay, setCurrent), [value, delay]);
  return current;
}
