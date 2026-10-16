import { createContext, useContext, useEffect, useRef, type MutableRefObject, type ReactNode } from "react";

/**
 * Permite que uma página "assuma" o deslizar lateral do celular (ex.: Análise financeira
 * troca entre as próprias seções). Quando a página não tem para onde ir naquela direção,
 * o gesto volta a trocar as abas do app.
 */
export type SwipeHandler = { canGo: (dir: -1 | 1) => boolean; go: (dir: -1 | 1) => void };

const SwipeContext = createContext<MutableRefObject<SwipeHandler | null> | null>(null);

export function SwipeProvider({ handler, children }: { handler: MutableRefObject<SwipeHandler | null>; children: ReactNode }) {
  return <SwipeContext.Provider value={handler}>{children}</SwipeContext.Provider>;
}

export function useSwipeOverride(handler: SwipeHandler) {
  const ref = useContext(SwipeContext);
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => {
    if (!ref) return;
    const proxy: SwipeHandler = { canGo: (dir) => latest.current.canGo(dir), go: (dir) => latest.current.go(dir) };
    ref.current = proxy;
    return () => {
      if (ref.current === proxy) ref.current = null;
    };
  }, [ref]);
}
