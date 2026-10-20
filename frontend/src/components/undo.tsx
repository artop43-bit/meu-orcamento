import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { errorMessage, withKeepalive } from "../api/client";
import { announce } from "../lib/announce";
import { haptic } from "../lib/haptics";

/**
 * Exclusão com "Desfazer": o item some da tela na hora, aparece um aviso com o botão
 * "Desfazer" e a exclusão só vai para o servidor depois de alguns segundos.
 * Se a pessoa recarregar, fechar a aba ou sair do app antes disso, a exclusão é enviada na hora.
 */

const DELAY = 6000;

type Pending = { key: number; ids: string[]; message: string; commit: () => Promise<unknown> };
/** Ação já feita (ex.: edição) que pode ser revertida pelo aviso. */
type Done = { key: number; message: string; revert: () => Promise<unknown> };

type UndoApi = {
  remove: (options: { ids: string[]; message: string; commit: () => Promise<unknown> }) => void;
  isHidden: (id: string) => boolean;
  /** Mostra "Salvo · Desfazer" depois de uma alteração. */
  done: (options: { message: string; revert: () => Promise<unknown> }) => void;
  /** Desfaz o que estiver no aviso (Ctrl+Z). Retorna se havia algo. */
  undoLast: () => boolean;
};

const UndoContext = createContext<UndoApi>({
  remove: () => undefined,
  isHidden: () => false,
  done: () => undefined,
  undoLast: () => false,
});

export function useUndo(): UndoApi {
  return useContext(UndoContext);
}

export function UndoProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending | null>(null);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const current = useRef<Pending | null>(null);

  const unhide = useCallback((ids: string[]) => {
    setHidden((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
  }, []);

  const commit = useCallback(
    async (item: Pending) => {
      window.clearTimeout(timer.current);
      if (current.current?.key === item.key) {
        current.current = null;
        setPending(null);
      }
      try {
        await item.commit();
        await queryClient.invalidateQueries({ queryKey: ["budget"] });
      } catch (err) {
        setError(`Não foi possível excluir: ${errorMessage(err)}`);
        announce(`Não foi possível excluir: ${errorMessage(err)}`);
        haptic("error");
      } finally {
        unhide(item.ids);
      }
    },
    [queryClient, unhide],
  );

  const start = useCallback((item: Pending, ms = DELAY) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void commit(item), ms);
  }, [commit]);

  const remove = useCallback<UndoApi["remove"]>(
    ({ ids, message, commit: send }) => {
      // Uma exclusão nova confirma a anterior na hora.
      if (current.current) void commit(current.current);
      const item = { key: Date.now(), ids, message, commit: send };
      current.current = item;
      setError("");
      setPending(item);
      setHidden((prev) => new Set([...prev, ...ids]));
      haptic("tap");
      announce(`${message}. Para desfazer, use o botão Desfazer.`);
      start(item);
    },
    [commit, start],
  );

  const [doneItem, setDoneItem] = useState<Done | null>(null);
  const doneTimer = useRef<number | undefined>(undefined);
  const doneRef = useRef<Done | null>(null);

  const done = useCallback<UndoApi["done"]>(({ message, revert }) => {
    const item = { key: Date.now(), message, revert };
    doneRef.current = item;
    setDoneItem(item);
    announce(`${message}. Para desfazer, use o botão Desfazer.`);
    window.clearTimeout(doneTimer.current);
    doneTimer.current = window.setTimeout(() => {
      doneRef.current = null;
      setDoneItem(null);
    }, DELAY);
  }, []);

  async function revertDone() {
    const item = doneRef.current;
    if (!item) return;
    doneRef.current = null;
    setDoneItem(null);
    window.clearTimeout(doneTimer.current);
    try {
      await item.revert();
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
      announce("Alteração desfeita");
      haptic("tap");
    } catch (err) {
      setError(`Não foi possível desfazer: ${errorMessage(err)}`);
    }
  }

  function undoLast(): boolean {
    if (current.current) {
      undo();
      return true;
    }
    if (doneRef.current) {
      void revertDone();
      return true;
    }
    return false;
  }

  function undo() {
    const item = current.current;
    if (!item) return;
    window.clearTimeout(timer.current);
    current.current = null;
    setPending(null);
    unhide(item.ids);
    announce("Exclusão desfeita");
  }

  // Ao recarregar, fechar a aba ou trocar de app com uma exclusão pendente, envia na hora.
  // keepalive: sem ele o navegador cancela a requisição quando a página é recarregada.
  // visibilitychange: no celular, sair do app nem sempre dispara o pagehide.
  useEffect(() => {
    const flush = () => {
      const item = current.current;
      if (item) withKeepalive(() => void commit(item));
    };
    const hidden = () => {
      if (document.visibilityState === "hidden") flush();
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [commit]);

  const isHidden = useCallback((id: string) => hidden.has(id), [hidden]);

  return (
    <UndoContext.Provider value={{ remove, isHidden, done, undoLast }}>
      {children}
      {pending && (
        <div
          className="toast no-print"
          // Pausa enquanto o mouse ou o foco estão no aviso (dá tempo de ler e decidir).
          onMouseEnter={() => window.clearTimeout(timer.current)}
          onMouseLeave={() => start(pending, 3000)}
          onFocus={() => window.clearTimeout(timer.current)}
          onBlur={() => start(pending, 3000)}
        >
          <span>{pending.message}</span>
          <button type="button" onClick={undo}>
            Desfazer
          </button>
        </div>
      )}
      {!pending && doneItem && (
        <div className="toast toast--done no-print" role="status">
          <span>
            <span className="toast__check" aria-hidden>
              ✓
            </span>{" "}
            {doneItem.message}
          </span>
          <button type="button" onClick={() => void revertDone()}>
            Desfazer
          </button>
        </div>
      )}
      {!pending && !doneItem && error && (
        <div className="toast no-print" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")}>
            Ok
          </button>
        </div>
      )}
    </UndoContext.Provider>
  );
}
