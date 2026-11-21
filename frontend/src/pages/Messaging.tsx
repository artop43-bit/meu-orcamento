import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, MessageSquarePlus } from "lucide-react";
import { useNavigate, useParams } from "react-router";

import { useMe } from "../api/auth";
import { ApiError, errorMessage } from "../api/client";
import {
  messagingApi,
  messagingKeys,
  useMessagingChat,
  useMessagingChats,
  useMessagingMessages,
  type ChatFilter,
  type MessagingChat,
  type MessagingMessage,
} from "../api/messaging";
import { ChatList } from "../components/messaging/ChatList";
import { ChatThread } from "../components/messaging/ChatThread";
import { Composer } from "../components/messaging/Composer";
import { ContactSheet } from "../components/messaging/ContactSheet";
import { NewChatSheet } from "../components/messaging/NewChatSheet";
import { announce } from "../lib/announce";
import { canUseSolution } from "../lib/hub";
import { payloadForChat } from "../lib/messaging";

/** Tela da Mensageria: junta a lista de conversas, a conversa aberta e as janelas. */
export default function Messaging() {
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe().data;
  const canUseCaderno = canUseSolution(me, "caderno");
  const canUseCofre = canUseSolution(me, "cofre");

  const [filter, setFilter] = useState<ChatFilter>("all");
  const [search, setSearch] = useState("");
  const [activeTag, setActiveTag] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(routeChatId ?? null);
  const [replyTo, setReplyTo] = useState<MessagingMessage | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [droppedFile, setDroppedFile] = useState<{ chatId: string | null; file: File; seq: number } | null>(null);
  const [externalDraft, setExternalDraft] = useState<{ chatId: string | null; text: string; seq: number } | null>(null);

  useEffect(() => {
    setSelectedId(routeChatId ?? null);
  }, [routeChatId]);

  const chatsQuery = useMessagingChats(filter, search, activeTag);
  const chats = useMemo(() => chatsQuery.data ?? [], [chatsQuery.data]);

  // A conversa aberta vem do próprio id (e não da lista filtrada): arquivar, filtrar ou buscar
  // outra coisa não fecha a conversa.
  const chatQuery = useMessagingChat(selectedId);
  const chatNotFound = chatQuery.error instanceof ApiError && chatQuery.error.status === 404;
  // Falha passageira na atualização mantém a conversa na tela com os dados que já vieram.
  const activeChat: MessagingChat | null = selectedId && !chatNotFound ? (chatQuery.data ?? null) : null;

  const messagesQuery = useMessagingMessages(activeChat?.id ?? null);
  const messages = useMemo(() => messagesQuery.data?.items ?? [], [messagesQuery.data]);

  const markRead = useMutation({
    mutationFn: (id: string) => messagingApi.markRead(id),
    onSuccess: (chat) => {
      queryClient.setQueryData(messagingKeys.chat(chat.id), chat);
      void queryClient.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void queryClient.invalidateQueries({ queryKey: messagingKeys.session });
    },
  });

  useEffect(() => {
    if (activeChat && activeChat.unread_count > 0 && !markRead.isPending) {
      markRead.mutate(activeChat.id);
    }
  }, [activeChat?.id, activeChat?.unread_count]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setReplyTo(null);
    setDroppedFile(null);
    setExternalDraft(null);
  }, [selectedId]);

  // Conversa que não existe mais (excluída em outro aparelho, link antigo): volta para a lista.
  useEffect(() => {
    if (!chatNotFound) return;
    setSelectedId(null);
    setInfoOpen(false);
    navigate("/mensageria", { replace: true });
    announce("Conversa não encontrada.");
  }, [chatNotFound]); // eslint-disable-line react-hooks/exhaustive-deps

  function openChat(chat: MessagingChat) {
    setSelectedId(chat.id);
    navigate(`/mensageria/${chat.id}`);
  }

  function closeChatMobile() {
    setSelectedId(null);
    navigate("/mensageria");
  }

  function openNewChat() {
    setNewOpen(true);
  }

  function onChatCreated(created: MessagingChat) {
    setNewOpen(false);
    setFilter("all");
    setSearch("");
    setSelectedId(created.id);
    navigate(`/mensageria/${created.id}`);
    announce(`Conversa com ${created.name} aberta.`);
  }

  function onChatDeleted() {
    setInfoOpen(false);
    setSelectedId(null);
    navigate("/mensageria", { replace: true });
  }

  const showThread = Boolean(selectedId) && !chatNotFound;

  return (
    <div className={`wa-workspace ${showThread ? "has-chat" : ""}`}>
      <ChatList
        chats={chats}
        loading={chatsQuery.isPending}
        error={chatsQuery.isError ? chatsQuery.error : null}
        filter={filter}
        search={search}
        activeTag={activeTag}
        activeId={selectedId}
        onFilterChange={setFilter}
        onSearchChange={setSearch}
        onTagChange={setActiveTag}
        onOpenChat={openChat}
        onNewChat={openNewChat}
      />

      <section className="wa-thread" aria-label={activeChat ? `Conversa com ${activeChat.name}` : "Área de mensagens"}>
        {activeChat ? (
          <>
            <ChatThread
              chat={activeChat}
              messages={messages}
              loading={messagesQuery.isPending}
              onBack={closeChatMobile}
              onOpenInfo={() => setInfoOpen(true)}
              onReply={setReplyTo}
              onFileDrop={(file) =>
                setDroppedFile((prev) => ({ chatId: activeChat.id, file, seq: (prev?.seq ?? 0) + 1 }))
              }
              onInsertDraft={(text) =>
                setExternalDraft((prev) => ({ chatId: activeChat.id, text, seq: (prev?.seq ?? 0) + 1 }))
              }
              canUseCaderno={canUseCaderno}
              canUseCofre={canUseCofre}
            />
            <Composer
              key={activeChat.id}
              chatId={activeChat.id}
              chatName={activeChat.name}
              chatPhone={activeChat.phone_display}
              replyTo={replyTo}
              onCancelReply={() => setReplyTo(null)}
              droppedFile={payloadForChat(droppedFile, activeChat.id)}
              externalDraft={payloadForChat(externalDraft, activeChat.id)}
            />
          </>
        ) : showThread ? (
          <div className="wa-thread__empty">
            {chatQuery.isError ? (
              <p className="alert alert--error" role="alert" style={{ margin: 0 }}>
                {errorMessage(chatQuery.error)}
              </p>
            ) : (
              <p className="muted small" style={{ margin: 0 }}>
                Carregando conversa…
              </p>
            )}
            <button type="button" className="btn btn--secondary btn--sm" onClick={closeChatMobile}>
              Voltar para conversas
            </button>
          </div>
        ) : (
          <div className="wa-thread__empty">
            <span className="wa-empty-icon wa-empty-icon--lg" aria-hidden>
              <MessageCircle size={32} />
            </span>
            <h2 className="wa-thread__empty-title">Selecione uma conversa</h2>
            <button type="button" className="btn btn--primary" onClick={openNewChat}>
              <MessageSquarePlus size={16} aria-hidden />
              Nova conversa
            </button>
          </div>
        )}
      </section>

      <NewChatSheet open={newOpen} onClose={() => setNewOpen(false)} onCreated={onChatCreated} />

      <ContactSheet
        open={infoOpen}
        chat={activeChat}
        onClose={() => setInfoOpen(false)}
        onDeleted={onChatDeleted}
        onFillDraft={(text) =>
          setExternalDraft((prev) => ({ chatId: activeChat?.id ?? null, text, seq: (prev?.seq ?? 0) + 1 }))
        }
      />
    </div>
  );
}
