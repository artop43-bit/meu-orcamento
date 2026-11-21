"""Rotas usadas pelo conector interno do WhatsApp (cabeçalho X-Connector-Token, sem cookie)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import DbSession
from app.core.errors import AppError
from app.services import messaging as service


def require_connector(
    x_connector_token: Annotated[str | None, Header()] = None,
) -> None:
    service.authenticate_connector(x_connector_token)


router = APIRouter(
    prefix="/messaging/connector",
    tags=["mensageria-conector"],
    dependencies=[Depends(require_connector)],
)


class ConnectorSessionOut(BaseModel):
    session_id: uuid.UUID


class ConnectorSessionsOut(BaseModel):
    sessions: list[ConnectorSessionOut]


class QuotedOut(BaseModel):
    external_id: str
    from_me: bool
    remote_jid: str
    body: str


class OutboxMediaOut(BaseModel):
    media_id: uuid.UUID
    kind: str
    mime_type: str
    file_name: str | None = None


class OutboxItemOut(BaseModel):
    message_id: uuid.UUID
    session_id: uuid.UUID
    remote_jid: str
    body: str
    message_type: str = "chat"
    media: OutboxMediaOut | None = None
    caption: str | None = None
    quoted: QuotedOut | None
    created_at: datetime


class OutboxOut(BaseModel):
    items: list[OutboxItemOut]


class EventsIn(BaseModel):
    # Cada evento é conferido sozinho: um evento estranho não recusa o lote inteiro.
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class EventsOut(BaseModel):
    processed: int
    ignored: int


@router.get("/sessions")
def list_sessions(db: DbSession) -> ConnectorSessionsOut:
    return ConnectorSessionsOut(
        sessions=[ConnectorSessionOut(**row) for row in service.list_connector_sessions(db)]
    )


@router.get("/outbox")
def outbox(
    db: DbSession,
    session_ids: Annotated[str, Query(max_length=8000)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OutboxOut:
    ids = service.parse_session_ids(session_ids)
    return OutboxOut(
        items=[OutboxItemOut(**row) for row in service.claim_outbox(db, ids, limit=limit)]
    )


@router.post("/events")
def events(body: EventsIn, db: DbSession) -> EventsOut:
    return EventsOut(**service.process_events(db, body.events))


class ConnectorMediaOut(BaseModel):
    media_id: uuid.UUID
    kind: str
    mime_type: str
    size_bytes: int


async def read_connector_body(request: Request) -> bytes:
    """Lê o corpo sem bloquear o loop e sem aceitar arquivos acima do limite."""
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > service.MAX_MEDIA_BYTES:
            raise AppError(413, "media_too_large", "Mídia acima do limite de 8 MB.")
        raw.extend(chunk)
    return bytes(raw)


@router.post("/sessions/{session_id}/media")
def upload_media(
    session_id: uuid.UUID,
    raw: Annotated[bytes, Depends(read_connector_body)],
    db: DbSession,
    kind: Annotated[str, Query(max_length=16)] = "document",
    mime_type: Annotated[str, Query(max_length=128)] = "application/octet-stream",
    file_name: Annotated[str | None, Query(max_length=255)] = None,
) -> ConnectorMediaOut:
    if len(raw) > service.MAX_MEDIA_BYTES:
        raise AppError(413, "media_too_large", "Mídia acima do limite de 8 MB.")
    media = service.store_connector_media(
        db,
        session_id,
        kind=kind,
        mime_type=mime_type,
        data=raw,
        file_name=file_name,
    )
    return ConnectorMediaOut(
        media_id=media.id,
        kind=media.kind,
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
    )


@router.get("/sessions/{session_id}/media/{media_id}")
def fetch_media(session_id: uuid.UUID, media_id: uuid.UUID, db: DbSession) -> Response:
    media = service.get_media_for_connector(db, session_id, media_id)
    fname = service.ascii_filename(media.file_name, fallback=media.kind)
    return Response(
        content=media.data,
        media_type=media.mime_type,
        headers={
            "X-Media-Kind": media.kind,
            "X-Media-Name": fname,
        },
    )


@router.post("/sessions/{session_id}/avatar")
def upload_avatar(
    session_id: uuid.UUID,
    raw: Annotated[bytes, Depends(read_connector_body)],
    db: DbSession,
    jid: Annotated[str, Query(min_length=3, max_length=128)],
    jid_alt: Annotated[str | None, Query(max_length=128)] = None,
    mime_type: Annotated[str, Query(max_length=64)] = "image/jpeg",
) -> dict[str, bool]:
    saved = service.save_connector_avatar(
        db,
        session_id,
        jid=jid,
        jid_alt=jid_alt,
        mime_type=mime_type,
        data=raw,
    )
    return {"saved": saved}
