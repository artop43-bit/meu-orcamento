import { describe, expect, it } from "vitest";

import { pendingPerf, recordPerf, screenOf } from "./perfReport";

describe("velocidade das telas (anônima)", () => {
  it("o nome da tela vem de uma lista fixa, sem identificadores do endereço", () => {
    expect(screenOf("/orcamento/2026-11")).toBe("orcamento");
    expect(screenOf("/dividas/3f2a9c1e-aaaa-bbbb-cccc-000000000000/tabela")).toBe("dividas");
    expect(screenOf("/ajustes/seguranca")).toBe("ajustes");
    expect(screenOf("/")).toBe("orcamento");
    expect(screenOf("/qualquer-coisa")).toBe("outras");
  });

  it("guarda só tela e milissegundos, e ignora medidas impossíveis", () => {
    recordPerf({ screen: "orcamento", load_ms: 412.7, frame_ms: 9000 });
    recordPerf({ screen: "orcamento", load_ms: -5, frame_ms: 0 });
    recordPerf({ screen: "orcamento", load_ms: 999_999, frame_ms: 0 });
    expect(pendingPerf()).toEqual([{ screen: "orcamento", load_ms: 413, frame_ms: 5000 }]);
  });
});
