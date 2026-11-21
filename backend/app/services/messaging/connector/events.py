"""Modelos Pydantic e utilitários de saneamento dos eventos recebidos do conector."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.services.messaging.messages import MESSAGE_TYPES

MAX_BODY = 65_536
UNSUPPORTED_BODY = "Mensagem não suportada"
# Ordem das confirmações: nunca volta atrás (enviada < entregue < lida).
STATUS_RANK = {"pending": 0, "failed": 0, "sent": 1, "delivered": 2, "read": 3}
# Prioridade da origem do nome: manual (editado no Hub) > agenda > apelido > genérico.
NAME_SOURCE_RANK = {"fallback": 0, "push": 1, "contact": 2, "manual": 3}


class StatusEvent(BaseModel):
    type: Literal["status"]
    session_id: uuid.UUID
    status: Literal["connecting", "qr", "ready", "disconnected", "error"]
    qr: str | None = None
    phone: str | None = None
    display_name: str | None = None
    wa_jid: str | None = None
    error: str | None = None
    wanted: bool | None = None


class MessageEvent(BaseModel):
    type: Literal["message"]
    session_id: uuid.UUID
    external_id: str = Field(min_length=1, max_length=160)
    remote_jid: str = Field(max_length=128)
    remote_jid_alt: str | None = Field(default=None, max_length=128)
    from_me: bool = False
    push_name: str | None = None
    body: str | None = None
    message_type: str | None = None
    status: Literal["pending", "sent", "delivered", "read", "played", "failed"] | None = None
    media_id: uuid.UUID | None = None
    timestamp: datetime | None = None
    quoted_external_id: str | None = Field(default=None, max_length=160)
    history: bool = False


class MediaAttachEvent(BaseModel):
    type: Literal["media_attach"]
    session_id: uuid.UUID
    external_id: str = Field(min_length=1, max_length=160)
    media_id: uuid.UUID


class ReceiptEvent(BaseModel):
    type: Literal["receipt"]
    session_id: uuid.UUID
    external_id: str = Field(min_length=1, max_length=160)
    status: Literal["sent", "delivered", "read", "played", "failed"]
    error: str | None = None


class AckEvent(BaseModel):
    type: Literal["ack"]
    session_id: uuid.UUID
    message_id: uuid.UUID
    status: Literal["sent", "failed"]
    external_id: str | None = Field(default=None, max_length=160)
    error: str | None = None


class ReadSelfEvent(BaseModel):
    type: Literal["read_self"]
    session_id: uuid.UUID
    remote_jid: str = Field(max_length=128)
    remote_jid_alt: str | None = Field(default=None, max_length=128)


class ContactEvent(BaseModel):
    type: Literal["contact"]
    session_id: uuid.UUID
    jid: str = Field(max_length=128)
    jid_alt: str | None = Field(default=None, max_length=128)
    name: str | None = None
    # "contact" / "chat" = nome salvo na agenda do celular; "push" = apelido do WhatsApp.
    source: Literal["contact", "push", "chat"] = "contact"


ConnectorEvent = Annotated[
    StatusEvent
    | MessageEvent
    | MediaAttachEvent
    | ReceiptEvent
    | AckEvent
    | ReadSelfEvent
    | ContactEvent,
    Field(discriminator="type"),
]
EVENT_ADAPTER = TypeAdapter(ConnectorEvent)


def clean_text(value: str | None, size: int) -> str:
    return " ".join((value or "").split())[:size]


def normalize_message_type(value: str | None) -> str:
    if not value:
        return "chat"
    return value if value in MESSAGE_TYPES else "other"


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
