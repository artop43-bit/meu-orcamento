import { describe, expect, it } from "vitest";

import { gestureAxis, neighbor, rubberBand, swipeResult } from "./gestures";

describe("gestureAxis", () => {
  it("espera o dedo andar um pouco antes de decidir", () => {
    expect(gestureAxis(4, 3)).toBeNull();
  });
  it("horizontal só quando claramente para o lado", () => {
    expect(gestureAxis(-40, 5)).toBe("x");
    expect(gestureAxis(30, 28)).toBe("y");
    // Diagonal (rolando a página) não troca de aba.
    expect(gestureAxis(-40, 25)).toBe("y");
    expect(gestureAxis(2, 50)).toBe("y");
  });
});

describe("swipeResult", () => {
  const width = 390;
  it("arrastar mais de 1/3 da tela troca de aba", () => {
    expect(swipeResult(-150, 600, width)).toBe(1);
    expect(swipeResult(150, 600, width)).toBe(-1);
  });
  it("um movimento rápido também troca", () => {
    expect(swipeResult(-80, 100, width)).toBe(1);
  });
  it("arrasto curto e lento volta para o lugar", () => {
    expect(swipeResult(-80, 600, width)).toBe(0);
    expect(swipeResult(-30, 20, width)).toBe(0);
  });
});

describe("rubberBand", () => {
  it("anda menos que o dedo e nunca passa do limite", () => {
    expect(rubberBand(100, 60)).toBeLessThan(100);
    expect(rubberBand(10_000, 60)).toBeLessThan(60);
    expect(rubberBand(-100, 60)).toBeCloseTo(-rubberBand(100, 60));
    expect(rubberBand(0, 60)).toBe(0);
  });
});

describe("neighbor", () => {
  const tabs = ["a", "b", "c"];
  it("acha a aba vizinha", () => {
    expect(neighbor(tabs, 1, 1)).toBe("c");
    expect(neighbor(tabs, 1, -1)).toBe("a");
  });
  it("não passa das pontas nem funciona fora das abas", () => {
    expect(neighbor(tabs, 0, -1)).toBeNull();
    expect(neighbor(tabs, 2, 1)).toBeNull();
    expect(neighbor(tabs, -1, 1)).toBeNull();
  });
});
