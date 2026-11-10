import { describe, expect, it } from "vitest";

import { boxWithin } from "./navIndicator";

const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height }) as DOMRect;

describe("boxWithin", () => {
  it("posição do item ativo dentro do grupo, descontando a borda", () => {
    expect(boxWithin(rect(120, 40, 80, 36), rect(100, 30, 400, 60), 0, 0, 1, 1)).toEqual({ x: 19, y: 9, w: 80, h: 36 });
  });

  it("em grupo rolado para o lado, acompanha o conteúdo", () => {
    expect(boxWithin(rect(50, 10, 90, 40), rect(20, 10, 300, 48), 140, 0)).toEqual({ x: 170, y: 0, w: 90, h: 40 });
  });
});
