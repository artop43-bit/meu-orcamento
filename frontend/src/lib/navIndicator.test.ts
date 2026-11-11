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

describe("marcador elástico (v1.7.5)", () => {
  it("no meio do caminho cobre do item antigo ao novo e termina no novo", async () => {
    const { stretchFrames } = await import("./navIndicator");
    const frames = stretchFrames({ x: 0, y: 0, w: 100, h: 40 }, { x: 0, y: 120, w: 100, h: 40 });
    expect(frames[0]).toMatchObject({ transform: "translate3d(0px, 0px, 0)", height: "40px" });
    expect(frames[1]).toMatchObject({ transform: "translate3d(0px, 0px, 0)", height: "160px", offset: 0.42 });
    expect(frames[2]).toMatchObject({ transform: "translate3d(0px, 120px, 0)", height: "40px" });
  });
});
