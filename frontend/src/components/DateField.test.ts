import { describe, expect, it } from "vitest";

import { textToIso } from "./DateField";

describe("textToIso", () => {
  it("aceita dd/mm/aaaa válida", () => {
    expect(textToIso("19/10/2026", false)).toBe("2026-10-19");
    expect(textToIso("29022028", false)).toBe("2028-02-29");
  });

  it("recusa datas irreais", () => {
    expect(textToIso("08/08/8888", false)).toBeNull();
    expect(textToIso("31/02/2026", false)).toBeNull();
    expect(textToIso("10/13/2026", false)).toBeNull();
    expect(textToIso("01/01/1999", false)).toBeNull();
    expect(textToIso("08/08/888888", false)).toBeNull();
  });

  it("mês e ano", () => {
    expect(textToIso("12/2026", true)).toBe("2026-12");
    expect(textToIso("13/2026", true)).toBeNull();
    expect(textToIso("01/2101", true)).toBeNull();
  });
});
