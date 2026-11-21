import { afterEach, describe, expect, it, vi } from "vitest";

import { createUndoController } from "../lib/undoQueue";

describe("createUndoController (Desfazer / flush ao desmontar)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("cancela a exclusão antes do prazo quando o usuário desfaz", () => {
    vi.useFakeTimers();
    const ctrl = createUndoController(6000);
    const commit = vi.fn().mockResolvedValue(undefined);
    const onFire = vi.fn();

    ctrl.schedule({ key: 1, ids: ["a"], message: "Item excluído", commit }, onFire);
    expect(ctrl.current?.ids).toEqual(["a"]);

    const cancelled = ctrl.takeCurrent();
    expect(cancelled?.key).toBe(1);
    expect(ctrl.current).toBeNull();

    vi.advanceTimersByTime(7000);
    expect(onFire).not.toHaveBeenCalled();
    expect(commit).not.toHaveBeenCalled();
  });

  it("retorna a exclusão anterior para confirmação imediata quando surge uma nova e evita envio duplo no unmount", () => {
    vi.useFakeTimers();
    const ctrl = createUndoController(6000);
    const commitFirst = vi.fn().mockResolvedValue(undefined);
    const commitSecond = vi.fn().mockResolvedValue(undefined);
    const onFire = vi.fn();

    expect(
      ctrl.schedule({ key: 1, ids: ["a"], message: "Primeiro", commit: commitFirst }, onFire),
    ).toBeNull();

    const prev = ctrl.schedule(
      { key: 2, ids: ["b"], message: "Segundo", commit: commitSecond },
      onFire,
    );
    expect(prev?.key).toBe(1);

    // Simula unmount + pagehide acontecendo em seguida: só a primeira chamada leva o item.
    const onUnmount = ctrl.takeCurrent();
    const onPageHide = ctrl.takeCurrent();
    expect(onUnmount?.key).toBe(2);
    expect(onPageHide).toBeNull();
  });
});
