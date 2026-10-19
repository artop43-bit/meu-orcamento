import { describe, expect, it } from "vitest";

import { dateProblem, textToIso } from "./DateField";

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

describe("dateProblem", () => {
  it("explica o erro exato", () => {
    expect(dateProblem("30/02/2027", false)).toBe("Fevereiro de 2027 tem 28 dias.");
    expect(dateProblem("31/04/2026", false)).toBe("Abril de 2026 tem 30 dias.");
    expect(dateProblem("10/13/2026", false)).toBe("Mês inválido: use de 01 a 12.");
    expect(dateProblem("10/10/1999", false)).toBe("Ano inválido: use um ano entre 2000 e 2100.");
    expect(dateProblem("00/10/2026", false)).toBe("Dia inválido: use a partir de 01.");
    expect(dateProblem("10/10", false)).toBe("Data incompleta: use dd/mm/aaaa.");
    expect(dateProblem("13/2026", true)).toBe("Mês inválido: use de 01 a 12.");
  });

  it("enquanto digita, data incompleta não é erro", () => {
    expect(dateProblem("10/1", false, { partial: true })).toBeNull();
    expect(dateProblem("", false)).toBeNull();
  });

  it("respeita mínimo e máximo", () => {
    expect(dateProblem("01/2026", true, { min: "2026-03" })).toBe("Use uma data a partir de 03/2026.");
    expect(dateProblem("10/10/2026", false, { max: "2026-10-01" })).toBe("Use uma data até 01/10/2026.");
    expect(dateProblem("29/02/2028", false)).toBeNull();
  });
});
