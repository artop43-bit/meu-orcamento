import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox } from "lucide-react";

import { errorMessage } from "../api/client";
import { extrasApi, type FeedbackItem } from "../api/extras";
import { EmptyGuide } from "../components/help";
import { Alert, LoadingRegion, PageHeader, Skeleton } from "../components/ui";

const KIND: Record<FeedbackItem["kind"], string> = { idea: "Sugestão", bug: "Problema", other: "Outro" };
const STATUS: Record<FeedbackItem["status"], string> = { new: "Nova", read: "Lida", done: "Resolvida" };

export default function AdminFeedback({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["admin", "feedback"], queryFn: extrasApi.feedback });

  async function setStatus(id: string, status: FeedbackItem["status"]) {
    await extrasApi.feedbackStatus(id, status);
    await queryClient.invalidateQueries({ queryKey: ["admin", "feedback"] });
  }

  const items = list.data ?? [];
  const fresh = items.filter((i) => i.status === "new").length;
  return (
    <>
      {embedded ? (
        <p className="muted" style={{ margin: "0 0 12px" }}>
          {list.data ? `${items.length} mensagem(ns) · ${fresh} nova(s)` : ""}
        </p>
      ) : (
        <PageHeader title="Feedback" subtitle={list.data ? `${items.length} no total · ${fresh} nova(s)` : undefined} />
      )}
      {list.isPending && (
        <LoadingRegion label="Carregando o feedback">
          <Skeleton height={200} />
        </LoadingRegion>
      )}
      {list.isError && <Alert tone="error">{errorMessage(list.error)}</Alert>}
      {list.data && items.length === 0 && (
        <section className="card">
          <EmptyGuide icon={<Inbox size={22} />} title="Nenhum feedback recebido" text="Mensagens enviadas pelo botão “Enviar feedback” aparecem aqui." />
        </section>
      )}
      <ul className="feedback-list">
        {items.map((item) => (
          <li key={item.id} className={`card stack stack--tight ${item.status === "new" ? "is-new" : ""}`}>
            <div className="split small">
              <span>
                <span className={`badge ${item.kind === "bug" ? "badge--error" : "badge--accent"}`}>{KIND[item.kind]}</span>{" "}
                {item.email ?? "conta excluída"} · {new Date(item.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
              </span>
              <select value={item.status} onChange={(e) => void setStatus(item.id, e.target.value as FeedbackItem["status"])} aria-label="Situação">
                {Object.entries(STATUS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{item.message}</p>
            <p className="muted small" style={{ margin: 0 }}>
              Tela {item.page ?? "?"} · versão {item.app_version ?? "?"} · {item.user_agent ?? ""}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
