import { useCallback, useMemo, useState } from "react";
import { QrCode, RefreshCw, Wifi, WifiOff } from "lucide-react";

import { useMessagingSession } from "../api/messaging";
import { sessionStatusLabel, type SessionStatusKey } from "../lib/messaging";
import { releaseLabel } from "../release";
import { ConnectionSheet } from "./messaging/ConnectionSheet";
import type { MessagingOutletContext } from "./messaging/context";
import { SolutionShell } from "./SolutionShell";

function StatusIcon({ status }: { status: SessionStatusKey }) {
  if (status === "ready") return <Wifi size={16} aria-hidden />;
  if (status === "qr") return <QrCode size={16} aria-hidden />;
  if (status === "connecting") return <RefreshCw size={16} aria-hidden />;
  return <WifiOff size={16} aria-hidden />;
}

/** Moldura da solução Mensageria baseada na SolutionShell única. */
export function MessagingShell() {
  const [connOpen, setConnOpen] = useState(false);
  const sessionQuery = useMessagingSession(connOpen);

  const openConnection = useCallback(() => setConnOpen(true), []);
  const outletContext = useMemo<MessagingOutletContext>(() => ({ openConnection }), [openConnection]);

  const status = sessionQuery.data?.status ?? "disconnected";
  const statusText = sessionStatusLabel(status);

  return (
    <SolutionShell
      solutionId="mensageria"
      releaseId="mensageria"
      icon="messages"
      name="Mensageria"
      homeTo="/mensageria"
      variant="wa"
      showVersionBadge={false}
      outletContext={outletContext}
      extraActions={
        <button
          type="button"
          className={`wa-conn-btn ${status === "ready" ? "is-online" : ""}`}
          onClick={openConnection}
          aria-label={`Conexão WhatsApp: ${statusText}`}
          title={`Conexão WhatsApp: ${statusText}`}
        >
          <StatusIcon status={status} />
          <span className="wa-conn-btn__label">{statusText}</span>
        </button>
      }
      footer={<footer className="wa-bar__inner muted small">{releaseLabel("mensageria")}</footer>}
    >
      <ConnectionSheet
        open={connOpen}
        onClose={() => setConnOpen(false)}
        session={sessionQuery.data}
        loadError={sessionQuery.error}
      />
    </SolutionShell>
  );
}
