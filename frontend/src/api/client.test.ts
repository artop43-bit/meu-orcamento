import { afterEach, describe, expect, it, vi } from "vitest";

import { api, withKeepalive } from "./client";

function stubFetch() {
  const fetch = vi.fn(async () => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const init = (fetch: ReturnType<typeof stubFetch>) => (fetch.mock.calls[0] as unknown as [string, RequestInit])[1];

describe("withKeepalive", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("marca a requisição para sobreviver à saída da página", async () => {
    const fetch = stubFetch();
    await withKeepalive(() => api.delete("/expenses/1?scope=one"));
    expect(init(fetch).keepalive).toBe(true);
  });

  it("não afeta as requisições comuns", async () => {
    const fetch = stubFetch();
    await api.delete("/expenses/1?scope=one");
    expect(init(fetch).keepalive).toBe(false);
  });

  it("vale só para o que começa dentro da função", async () => {
    const fetch = stubFetch();
    await withKeepalive(() => api.delete("/a"));
    await api.delete("/b");
    expect((fetch.mock.calls[1] as unknown as [string, RequestInit])[1].keepalive).toBe(false);
  });
});
