import { describe, expect, it } from "vitest";

import { fadeFor } from "./scrollEdges";

describe("fadeFor", () => {
  it("esmaece só a borda onde há conteúdo escondido", () => {
    expect(fadeFor(0, 300, 300)).toBe("none");
    expect(fadeFor(0, 300, 600)).toBe("end");
    expect(fadeFor(150, 300, 600)).toBe("both");
    expect(fadeFor(300, 300, 600)).toBe("start");
  });
});
