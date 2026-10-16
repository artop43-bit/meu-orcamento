import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../api/client";
import { announce } from "../lib/announce";
import { haptic } from "../lib/haptics";

/**
 * Exclusão com "Desfazer": o item some da tela na hora, aparece um aviso com o botão
 * "Desfazer" e a exclusão só vai para o servidor depois de alguns segundos.
 * Se a pessoa fechar a aba antes disso, nada é excluído (o lado seguro).
 */

const DELAY = 6000;

type Pending = { key: number; ids: string[]; message: string; commit: () => Promise<unknown> };

type UndoApi = {
  remove: (options: { ids: string[]; message: string; commit: () => Promise<unknown> }) => void;
  isHidden: (id: string) => boolean;
};

const UndoContext = createContext<UndoApi>({ remove: () => undefined, isHidden: () => false });

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

  function undo() {
    const item = current.current;
    if (!item) return;
    window.clearTimeout(timer.current);
    current.current = null;
    setPending(null);
    unhide(item.ids);
    announce("Exclusão desfeita");
  }

  // Ao sair da página com uma exclusão pendente, tenta enviar na hora.
  useEffect(() => {
    const flush = () => {
      if (current.current) void current.current.commit();
    };
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, []);

  const isHidden = useCallback((id: string) => hidden.has(id), [hidden]);

  return (
    <UndoContext.Provider value={{ remove, isHidden }}>
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
      {!pending && error && (
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
