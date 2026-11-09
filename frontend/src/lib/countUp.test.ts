import { describe, expect, it } from "vitest";

import { easeOut, formatLike, parseFormatted } from "./countUp";

describe("parseFormatted / formatLike", () => {
  it("separa prefixo, número e sufixo e reescreve com as mesmas casas", () => {
    const money = parseFormatted("R$ 4.880,00")!;
    expect(money).toEqual({ prefix: "R$ ", value: 4880, decimals: 2, suffix: "" });
    expect(formatLike(money, 1234.5)).toBe("R$ 1.234,50");
    const pct = parseFormatted("73,7%")!;
    expect(formatLike(pct, 12)).toBe("12,0%");
    expect(parseFormatted("-R$ 285,41")).toMatchObject({ prefix: "-R$ ", value: 285.41 });
    expect(parseFormatted("11")).toMatchObject({ value: 11, decimals: 0 });
  });

  it("texto sem número não anima", () => {
    expect(parseFormatted("R$ ••••")).toBeNull();
    expect(parseFormatted("—")).toBeNull();
  });

  it("a curva começa rápida e termina no valor", () => {
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(0.5)).toBeGreaterThan(0.8);
  });
});
