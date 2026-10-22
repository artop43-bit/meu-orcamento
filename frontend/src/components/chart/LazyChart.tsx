import { lazy, Suspense } from "react";

import type { ChartProps } from "./Chart";

const Chart = lazy(() => import("./Chart").then((m) => ({ default: m.Chart })));

/**
 * Gráfico baixado só quando aparece (v1.4.4): tira o código dos gráficos do arquivo principal,
 * que também carrega a tela de entrada. Enquanto baixa, guarda o espaço do gráfico (a tela
 * não pula).
 */
export function LazyChart(props: ChartProps) {
  return (
    <Suspense fallback={<div style={{ height: props.height ?? 260 }} aria-hidden />}>
      <Chart {...props} />
    </Suspense>
  );
}
