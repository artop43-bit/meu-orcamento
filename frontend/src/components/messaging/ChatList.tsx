import { CalendarClock, MessageCircle, MessageSquarePlus, Pin, Search, Tag } from "lucide-react";

import { errorMessage } from "../../api/client";
import type { ChatFilter, MessagingChat } from "../../api/messaging";
import {
  followupStatus,
  formatChatTimestamp,
  PRESET_CHAT_TAGS,
  SERVICE_STATUS_LABELS,
  serviceStatusTone,
  shortenPreview,
} from "../../lib/messaging";
import { ChatAvatar } from "./ChatAvatar";

const FILTERS = [
  ["all", "Todas"],
  ["unread", "Não lidas"],
  ["followup", "Follow-up"],
  ["archived", "Arquivadas"],
] as const;

function emptyText(filter: ChatFilter, search: string, activeTag: string): string {
  if (search.trim() || activeTag) return "Nenhuma conversa encontrada.";
  if (filter === "unread") return "Nenhuma conversa não lida.";
  if (filter === "followup") return "Nenhum follow-up agendado.";
  if (filter === "archived") return "Nenhuma conversa arquivada.";
  return "Nenhuma conversa iniciada.";
}

/** Painel esquerdo: busca, filtros (incluindo Follow-up e etiquetas) e lista de conversas. */
export function ChatList({
  chats,
  loading,
  error,
  filter,
  search,
  activeTag = "",
  activeId,
  onFilterChange,
  onSearchChange,
  onTagChange,
  onOpenChat,
  onNewChat,
}: {
  chats: MessagingChat[];
  loading: boolean;
  error: unknown;
  filter: ChatFilter;
  search: string;
  activeTag?: string;
  activeId: string | null;
  onFilterChange: (filter: ChatFilter) => void;
  onSearchChange: (search: string) => void;
  onTagChange?: (tag: string) => void;
  onOpenChat: (chat: MessagingChat) => void;
  onNewChat: () => void;
}) {
  return (
    <aside className="wa-sidebar" aria-label="Conversas">
      <div className="wa-sidebar__head">
        <h1 className="wa-sidebar__title">Conversas</h1>
        <button type="button" className="btn btn--primary btn--sm" onClick={onNewChat}>
          <MessageSquarePlus size={16} aria-hidden />
          Nova conversa
        </button>
      </div>

      <div className="wa-search">
        <div className="wa-search__field">
          <label htmlFor="wa-search-input" className="sr-only">
            Buscar conversa
          </label>
          <Search size={16} className="wa-search__icon" aria-hidden />
          <input
            id="wa-search-input"
            type="search"
            className="wa-search__input"
            placeholder="Buscar conversa"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      </div>

      <div className="wa-filters" role="group" aria-label="Filtrar conversas">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="filter-chip"
            aria-pressed={filter === value}
            onClick={() => onFilterChange(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {onTagChange && (
        <div className="wa-tag-filters" role="group" aria-label="Filtrar por etiqueta">
          {PRESET_CHAT_TAGS.map((tag) => {
            const pressed = activeTag.toLowerCase() === tag.toLowerCase();
            return (
              <button
                key={tag}
                type="button"
                className={`wa-tag-chip ${pressed ? "is-active" : ""}`}
                aria-pressed={pressed}
                onClick={() => onTagChange(pressed ? "" : tag)}
              >
                <Tag size={10} aria-hidden />
                {tag}
              </button>
            );
          })}
        </div>
      )}

      {error ? (
        <div className="wa-sidebar__empty">
          <p className="alert alert--error" role="alert">
            {errorMessage(error)}
          </p>
        </div>
      ) : loading ? (
        <div className="wa-sidebar__empty">
          <p className="muted small">Carregando conversas…</p>
        </div>
      ) : chats.length === 0 ? (
        <div className="wa-sidebar__empty">
          <span className="wa-empty-icon" aria-hidden>
            <MessageCircle size={24} />
          </span>
          <p className="muted small m-0">
            {emptyText(filter, search, activeTag)}
          </p>
          {filter === "all" && !search.trim() && !activeTag && (
            <button type="button" className="btn btn--secondary btn--sm" onClick={onNewChat}>
              Iniciar conversa
            </button>
          )}
        </div>
      ) : (
        <ul className="wa-chat-list" aria-label="Lista de conversas">
          {chats.map((chat) => {
            const isSelected = activeId === chat.id;
            const fStatus = followupStatus(chat.followup_at);
            const tags = chat.tags ?? [];
            const hasBadges =
              tags.length > 0 ||
              Boolean(fStatus) ||
              (chat.service_status && chat.service_status !== "open");
            return (
              <li key={chat.id}>
                <button
                  type="button"
                  className={`wa-chat-item ${isSelected ? "is-active" : ""}`}
                  aria-current={isSelected ? "true" : undefined}
                  onClick={() => onOpenChat(chat)}
                >
                  <ChatAvatar name={chat.name} avatarUrl={chat.avatar_url} />
                  <span className="wa-chat-item__body">
                    <span className="wa-chat-item__top">
                      <strong className="wa-chat-item__name">{chat.name}</strong>
                      <span className="wa-chat-item__meta">
                        {chat.pinned && <Pin size={12} aria-label="Fixada" />}
                        {chat.last_message_at && (
                          <span className="muted small">{formatChatTimestamp(chat.last_message_at)}</span>
                        )}
                      </span>
                    </span>
                    <span className="wa-chat-item__bottom">
                      <span className="wa-chat-item__preview muted small">
                        {shortenPreview(chat.last_message_preview, 54)}
                      </span>
                      {chat.unread_count > 0 && (
                        <span className="wa-unread" aria-label={`${chat.unread_count} não lida(s)`}>
                          {chat.unread_count > 99 ? "99+" : chat.unread_count}
                        </span>
                      )}
                    </span>
                    {hasBadges && (
                      <span className="wa-chat-item__badges">
                        {chat.service_status && chat.service_status !== "open" && (
                          <span className={`badge ${serviceStatusTone(chat.service_status)}`}>
                            {SERVICE_STATUS_LABELS[chat.service_status] ?? chat.service_status}
                          </span>
                        )}
                        {fStatus && (
                          <span
                            className={`badge ${
                              fStatus.tone === "overdue"
                                ? "badge--error"
                                : fStatus.tone === "today"
                                  ? "badge--warn"
                                  : "badge--muted"
                            }`}
                          >
                            <CalendarClock size={10} aria-hidden />
                            {fStatus.label}
                          </span>
                        )}
                        {tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="wa-tag-pill">
                            {tag}
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
