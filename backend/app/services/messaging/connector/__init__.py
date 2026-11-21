"""Lado da API usado pelo conector do WhatsApp: autenticação, sessões, fila e eventos."""

from app.services.messaging.connector.handlers import (
    _HANDLERS,
    process_events,
    save_connector_avatar,
)
from app.services.messaging.connector.outbox import (
    OUTBOX_CLAIM_SECONDS,
    authenticate_connector,
    claim_outbox,
    list_connector_sessions,
    parse_session_ids,
)

__all__ = [
    "_HANDLERS",
    "OUTBOX_CLAIM_SECONDS",
    "authenticate_connector",
    "claim_outbox",
    "list_connector_sessions",
    "parse_session_ids",
    "process_events",
    "save_connector_avatar",
]
