import { describe, expect, it } from "vitest";

import { describeDevice } from "./account";

describe("describeDevice", () => {
  it.each([
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
      "Chrome no Windows",
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 Edg/141.0",
      "Edge no Windows",
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
      "Safari no iOS",
    ],
    [
      "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36",
      "Chrome no Android",
    ],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0", "Firefox no Linux"],
  ])("%s", (userAgent, expected) => {
    expect(describeDevice(userAgent)).toBe(expected);
  });

  it("lida com navegador desconhecido", () => {
    expect(describeDevice(null)).toBe("Dispositivo desconhecido");
    expect(describeDevice("curl/8.5")).toBe("Navegador no sistema desconhecido");
  });
});
