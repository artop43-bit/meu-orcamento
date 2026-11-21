/** Fila pura de exclusão com atraso ("Desfazer"): garante envio único ao sair ou sobrepor. */
export interface PendingUndoItem {
  key: number;
  ids: string[];
  message: string;
  commit: () => Promise<unknown>;
}

/** Cria o estado mutável da fila de exclusões pendentes para o UndoProvider e testes unitários. */
export function createUndoController(delayMs = 6000) {
  let current: PendingUndoItem | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function clearTimer() {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
  }

  /** Extrai e limpa o item atual antes de chamar commit(), evitando duplo envio em unmount/pagehide. */
  function takeCurrent(): PendingUndoItem | null {
    clearTimer();
    const item = current;
    current = null;
    return item;
  }

  function takeIfKey(key: number): PendingUndoItem | null {
    if (!current || current.key !== key) return null;
    return takeCurrent();
  }

  function schedule(
    item: PendingUndoItem,
    onFire: (expired: PendingUndoItem) => void,
    ms = delayMs,
  ): PendingUndoItem | null {
    const previous = current ? takeCurrent() : null;
    current = item;
    timer = setTimeout(() => onFire(item), ms);
    return previous;
  }

  return {
    get current() {
      return current;
    },
    clearTimer,
    takeCurrent,
    takeIfKey,
    schedule,
  };
}
