"""Serviços da solução de Mensageria (WhatsApp pelo conector interno e vínculo com Orçamento).

Módulos:
- phones: números e JIDs (@s.whatsapp.net e @lid);
- sessions: conexão do número (QR Code), resumo e desconexão;
- chats e messages: conversas e mensagens da tela;
- connector e connector_client: os dois lados da conversa com o conector;
- budget: ponte com o Meu Orçamento.
"""

from app.services.messaging import connector_client
from app.services.messaging.budget import budget_context, create_chat_budget_entry
from app.services.messaging.chats import (
    SERVICE_STATUSES,
    chat_avatar_url,
    create_or_open_chat,
    create_quick_reply,
    delete_chat,
    delete_quick_reply,
    get_chat,
    get_chat_avatar,
    list_chats,
    list_quick_replies,
    mark_chat_read,
    parse_chat_tags,
    update_chat,
)
from app.services.messaging.cleanup import RETENTION, purge_old
from app.services.messaging.connector import (
    OUTBOX_CLAIM_SECONDS,
    authenticate_connector,
    claim_outbox,
    list_connector_sessions,
    parse_session_ids,
    process_events,
    save_connector_avatar,
)
from app.services.messaging.crm_link import chat_crm_context, create_chat_crm_deal
from app.services.messaging.media import (
    MAX_AVATAR_BYTES,
    MAX_MEDIA_BYTES,
    ascii_filename,
    get_media_for_connector,
    get_media_for_user,
    is_inline_safe,
    sniff_media_mime,
    store_connector_media,
)
from app.services.messaging.messages import (
    MESSAGE_STATUSES,
    MESSAGE_TYPES,
    list_messages,
    preview,
    send_media_message,
    send_message,
    serialize_message,
)
from app.services.messaging.phones import (
    DEFAULT_CONTACT_NAME,
    format_phone_display,
    is_placeholder_name,
    normalize_phone,
    parse_jid,
    phone_from_jid,
    split_jids,
)
from app.services.messaging.sessions import (
    SESSION_STATUSES,
    connect_session,
    disconnect_session,
    get_or_create_session,
    session_summary,
)

__all__ = [
    "DEFAULT_CONTACT_NAME",
    "MAX_AVATAR_BYTES",
    "MAX_MEDIA_BYTES",
    "MESSAGE_STATUSES",
    "MESSAGE_TYPES",
    "OUTBOX_CLAIM_SECONDS",
    "RETENTION",
    "SERVICE_STATUSES",
    "SESSION_STATUSES",
    "ascii_filename",
    "authenticate_connector",
    "budget_context",
    "chat_avatar_url",
    "chat_crm_context",
    "claim_outbox",
    "connect_session",
    "connector_client",
    "create_chat_budget_entry",
    "create_chat_crm_deal",
    "create_or_open_chat",
    "create_quick_reply",
    "delete_chat",
    "delete_quick_reply",
    "disconnect_session",
    "format_phone_display",
    "get_chat",
    "get_chat_avatar",
    "get_media_for_connector",
    "get_media_for_user",
    "get_or_create_session",
    "is_inline_safe",
    "is_placeholder_name",
    "list_chats",
    "list_connector_sessions",
    "list_messages",
    "list_quick_replies",
    "mark_chat_read",
    "normalize_phone",
    "parse_chat_tags",
    "parse_jid",
    "parse_session_ids",
    "phone_from_jid",
    "preview",
    "process_events",
    "purge_old",
    "save_connector_avatar",
    "send_media_message",
    "send_message",
    "serialize_message",
    "session_summary",
    "sniff_media_mime",
    "split_jids",
    "store_connector_media",
    "update_chat",
]
