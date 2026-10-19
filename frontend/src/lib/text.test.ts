import { describe, expect, it } from "vitest";

import { normalizeText } from "./text";

describe("normalizeText", () => {
  it("ignora acentos, maiúsculas e espaços nas pontas", () => {
    expect(normalizeText("  Farmácia SÃO João ")).toBe("farmacia sao joao");
  });
});
