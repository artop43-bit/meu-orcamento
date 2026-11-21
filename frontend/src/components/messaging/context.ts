import { useOutletContext } from "react-router";

/** O que a moldura da Mensageria (MessagingShell) passa para as telas de dentro. */
export interface MessagingOutletContext {
  /** Abre a janela de conexão com o WhatsApp. */
  openConnection: () => void;
}

const FALLBACK: MessagingOutletContext = { openConnection: () => {} };

/** Contexto da moldura da Mensageria; fora dela (ex.: em testes) os atalhos não fazem nada. */
export function useMessagingOutlet(): MessagingOutletContext {
  return useOutletContext<MessagingOutletContext | undefined>() ?? FALLBACK;
}
