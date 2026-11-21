import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, withKeepalive } from "./client";

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

describe("erros transitórios 502/503/504", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("tenta novamente uma vez em GET quando o servidor devolve 502", async () => {
    vi.useFakeTimers();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);

    const promise = api.get<{ ok: boolean }>("/health");
    await vi.advanceTimersByTimeAsync(750);
    const data = await promise;

    expect(data).toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("exibe mensagem amigável em português quando 502 persiste sem duplicar POST", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response("", { status: 502 }));
    vi.stubGlobal("fetch", fetch);

    await expect(api.post("/expenses", { amount: 10 })).rejects.toMatchObject({
      status: 502,
      code: "unavailable",
      message: "Servidor indisponível no momento. Tente novamente em instantes.",
    } satisfies Partial<ApiError>);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
