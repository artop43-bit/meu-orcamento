import { describe, expect, it } from "vitest";

import { crc16, pixCode } from "./pix";

describe("Pix copia e cola", () => {
  it("CRC16-CCITT do padrão", () => {
    // Valor de referência do CRC-16/CCITT-FALSE para "123456789".
    expect(crc16("123456789")).toBe("29B1");
  });

  it("monta o código com chave, valor, nome e cidade", () => {
    const code = pixCode({ key: "12345678909", name: "Ana Souza", city: "Goiânia", amount: 45.5 });
    expect(code.startsWith("000201")).toBe(true);
    expect(code).toContain("0014br.gov.bcb.pix0111" + "12345678909");
    expect(code).toContain("540545.50");
    expect(code).toContain("5909ANA SOUZA");
    expect(code).toContain("6007GOIANIA");
    expect(code).toContain("62070503***");
    // O código termina com o CRC do próprio conteúdo.
    expect(code.slice(-4)).toBe(crc16(code.slice(0, -4)));
  });

  it("nome e cidade sem acentos e no tamanho máximo", () => {
    const code = pixCode({ key: "ana@example.com", name: "José da Silva Conceição Júnior Neto", city: "São José dos Campos" });
    expect(code).toContain("5925JOSE DA SILVA CONCEICAO ");
    expect(code).toContain("6015SAO JOSE DOS CA");
    expect(code).not.toContain("5404");
  });
});
