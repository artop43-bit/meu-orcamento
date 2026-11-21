import { afterEach, describe, expect, it, vi } from "vitest";

import { scheduleDebouncedCallback } from "./useDebouncedValue";

describe("useDebouncedValue / scheduleDebouncedCallback", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("dispara a busca uma única vez após digitação rápida com janela de 300 ms", () => {
    vi.useFakeTimers();
    const fetchNotes = vi.fn();
    let cleanup = () => {};

    for (const typed of ["r", "ro", "rot", "rote", "rotei", "roteir", "roteiro"]) {
      cleanup();
      cleanup = scheduleDebouncedCallback(typed, 300, fetchNotes);
      vi.advanceTimersByTime(50);
    }

    expect(fetchNotes).not.toHaveBeenCalled();
    vi.advanceTimersByTime(250);
    expect(fetchNotes).toHaveBeenCalledTimes(1);
    expect(fetchNotes).toHaveBeenCalledWith("roteiro");
  });

  it("cancela o timer pendente quando desmontado antes do atraso", () => {
    vi.useFakeTimers();
    const fetchNotes = vi.fn();
    const cancel = scheduleDebouncedCallback("proposta", 300, fetchNotes);

    vi.advanceTimersByTime(200);
    cancel();
    vi.advanceTimersByTime(300);

    expect(fetchNotes).not.toHaveBeenCalled();
  });
});
