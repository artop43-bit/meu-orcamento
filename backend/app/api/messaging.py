"""Rotas da solução de Mensageria usadas pela tela (sessão do navegador)."""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require_feature, require_solution
from app.core.errors import AppError
from app.models import MessagingChat
from app.schemas.budget import PaymentMethod
from app.services import admin as admin_service
from app.services import messaging as service

router = APIRouter(tags=["mensageria"], dependencies=[Depends(require_solution("mensageria"))])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
ServiceStatusLiteral = Literal["open", "waiting", "resolved"]
ChatFilterLiteral = Literal["all", "unread", "followup", "open", "waiting", "resolved", "archived"]


# ---------------------------------------------------------------- schemas


class MessagingSessionOut(BaseModel):
    status: Literal["disconnected", "connecting", "qr", "ready", "error"]
    connected: bool
    # Conector configurado neste servidor (sem ele, não dá para conectar).
    available: bool
    phone: str | None
    phone_display: str
    display_name: str | None
    # String crua do QR Code (a tela desenha); só com status "qr".
    qr_code: str | None
    pending_outbox: int
    chats_count: int
    unread_chats: int
    last_seen_at: datetime | None
    last_error: str | None
    updated_at: datetime


class ChatIn(BaseModel):
    phone: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=300)
    budget_person: str | None = Field(default=None, max_length=80)


class ChatPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=300)
    budget_person: str | None = Field(default=None, max_length=80)
    pinned: bool | None = None
    archived: bool | None = None
    tags: list[str] | None = None
    service_status: ServiceStatusLiteral | None = None
    followup_at: datetime | None = None
    followup_note: str | None = Field(default=None, max_length=200)


class ChatOut(BaseModel):
    id: uuid.UUID
    remote_jid: str
    # Vazio quando o WhatsApp esconde o número (contato só com LID).
    phone: str | None
    phone_display: str
    lid_jid: str | None
    name: str
    avatar_url: str | None = None
    notes: str | None
    budget_person: str | None
    tags: list[str] = Field(default_factory=list)
    service_status: ServiceStatusLiteral = "open"
    followup_at: datetime | None = None
    followup_note: str | None = None
    unread_count: int
    pinned: bool
    archived: bool
    last_message_preview: str | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _chat_out(chat: MessagingChat) -> ChatOut:
    raw_status = (chat.service_status or "open").strip().lower()
    service_status: ServiceStatusLiteral = (
        cast(ServiceStatusLiteral, raw_status)
        if raw_status in ("open", "waiting", "resolved")
        else "open"
    )
    return ChatOut(
        id=chat.id,
        remote_jid=chat.remote_jid,
        phone=chat.phone,
        phone_display=service.format_phone_display(chat.phone),
        lid_jid=chat.lid_jid,
        name=chat.name,
        avatar_url=service.chat_avatar_url(chat),
        notes=chat.notes,
        budget_person=chat.budget_person,
        tags=service.parse_chat_tags(chat.tags),
        service_status=service_status,
        followup_at=chat.followup_at,
        followup_note=chat.followup_note,
        unread_count=chat.unread_count,
        pinned=chat.pinned,
        archived=chat.archived,
        last_message_preview=chat.last_message_preview,
        last_message_at=chat.last_message_at,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    reply_to_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    direction: Literal["in", "out"]
    body: str
    message_type: str
    status: str
    external_id: str | None
    reply_to_id: uuid.UUID | None
    reply_preview: str | None
    media_id: uuid.UUID | None = None
    media_mime: str | None = None
    media_name: str | None = None
    media_size: int | None = None
    media_url: str | None = None
    error_detail: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessagesPageOut(BaseModel):
    items: list[MessageOut]
    # Mandar de volta como `since` na próxima consulta (traz só o que mudou).
    cursor: datetime


class BudgetContactOut(BaseModel):
    person: str
    phone: str | None
    owes_me: Decimal
    i_owe: Decimal
    net: Decimal
    open_items: int


class BudgetCategoryOut(BaseModel):
    id: uuid.UUID
    name: str


class BudgetContextOut(BaseModel):
    month: str
    income_total: Decimal
    expense_total: Decimal
    pending_total: Decimal
    balance: Decimal
    pix_key: str | None = None
    pix_name: str | None = None
    contacts: list[BudgetContactOut]
    linked_contact: BudgetContactOut | None
    categories: list[BudgetCategoryOut] = Field(default_factory=list)
    cards: list[BudgetCategoryOut] = Field(default_factory=list)


class QuickReplyIn(BaseModel):
    shortcut: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=2000)


class QuickReplyOut(BaseModel):
    id: uuid.UUID
    shortcut: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


class ChatCrmDealIn(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    value: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9999999999.99"), allow_inf_nan=False
    )
    amount: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9999999999.99"), allow_inf_nan=False
    )
    stage_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=300)


class ChatBudgetEntryIn(BaseModel):
    kind: Literal["income", "expense"] = "expense"
    description: str = Field(min_length=1, max_length=140)
    amount: Decimal = Field(ge=Decimal("0.01"), le=Decimal("9999999999.99"), allow_inf_nan=False)
    category_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    paid: bool = True
    payment_method: PaymentMethod | None = "pix"
    notes: str | None = Field(default=None, max_length=300)
    client_ref: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")


# ---------------------------------------------------------------- sessão do WhatsApp


@router.get("/messaging/session")
def get_session(user: CurrentUser, db: DbSession) -> MessagingSessionOut:
    return MessagingSessionOut(**service.session_summary(db, user))


@router.post(
    "/messaging/session/connect",
    dependencies=[Depends(require_feature("feature:whatsapp_connect"))],
)
def connect_session(user: CurrentUser, db: DbSession) -> MessagingSessionOut:
    return MessagingSessionOut(**service.connect_session(db, user))


@router.post("/messaging/session/disconnect")
def disconnect_session(user: CurrentUser, db: DbSession) -> MessagingSessionOut:
    return MessagingSessionOut(**service.disconnect_session(db, user))


# ---------------------------------------------------------------- conversas


@router.get("/messaging/chats")
def list_chats(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    filter: Annotated[ChatFilterLiteral, Query()] = "all",
    tag: Annotated[str | None, Query(max_length=40)] = None,
) -> list[ChatOut]:
    return [
        _chat_out(chat) for chat in service.list_chats(db, user, q=q, filter_mode=filter, tag=tag)
    ]


@router.post("/messaging/chats", status_code=status.HTTP_201_CREATED)
def create_chat(body: ChatIn, user: CurrentUser, db: DbSession) -> ChatOut:
    chat, _ = service.create_or_open_chat(
        db,
        user,
        phone=body.phone,
        name=body.name,
        notes=body.notes,
        budget_person=body.budget_person,
    )
    return _chat_out(chat)


@router.get("/messaging/chats/{chat_id}")
def get_chat(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ChatOut:
    return _chat_out(service.get_chat(db, user, chat_id))


@router.patch("/messaging/chats/{chat_id}")
def patch_chat(chat_id: uuid.UUID, body: ChatPatch, user: CurrentUser, db: DbSession) -> ChatOut:
    changes = body.model_dump(exclude_unset=True)
    return _chat_out(service.update_chat(db, user, chat_id, changes))


@router.delete("/messaging/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chat(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_chat(db, user, chat_id)


@router.post("/messaging/chats/{chat_id}/read")
def mark_read(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ChatOut:
    return _chat_out(service.mark_chat_read(db, user, chat_id))


# ---------------------------------------------------------------- mensagens


@router.get("/messaging/chats/{chat_id}/messages")
def list_messages(
    chat_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=300)] = 100,
    since: Annotated[datetime | None, Query()] = None,
) -> MessagesPageOut:
    page = service.list_messages(db, user, chat_id, limit=limit, since=since)
    return MessagesPageOut(
        items=[MessageOut(**row) for row in page["items"]], cursor=page["cursor"]
    )


@router.post("/messaging/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    chat_id: uuid.UUID, body: MessageIn, user: CurrentUser, db: DbSession
) -> MessageOut:
    return MessageOut(
        **service.send_message(db, user, chat_id, body=body.body, reply_to_id=body.reply_to_id)
    )


@router.post("/messaging/chats/{chat_id}/media", status_code=status.HTTP_201_CREATED)
def send_media(
    chat_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),  # noqa: B008
    caption: Annotated[str | None, Form(max_length=4000)] = None,
    kind: Annotated[str | None, Form(max_length=16)] = None,
    reply_to_id: Annotated[str | None, Form(max_length=64)] = None,
) -> MessageOut:
    raw = file.file.read(service.MAX_MEDIA_BYTES + 1)
    if len(raw) > service.MAX_MEDIA_BYTES:
        raise AppError(
            413,
            "media_too_large",
            "O arquivo passa do limite de 8 MB permitido para envio.",
        )
    admin_service.assert_storage_quota(db, user, len(raw))
    parsed_reply: uuid.UUID | None = None
    if reply_to_id and reply_to_id.strip():
        try:
            parsed_reply = uuid.UUID(reply_to_id.strip())
        except ValueError as exc:
            raise AppError(400, "invalid_reply", "Mensagem citada inválida.") from exc
    return MessageOut(
        **service.send_media_message(
            db,
            user,
            chat_id,
            data=raw,
            mime_type=file.content_type or "application/octet-stream",
            file_name=file.filename,
            caption=caption,
            kind=kind,
            reply_to_id=parsed_reply,
        )
    )


@router.get("/messaging/media/{media_id}")
def download_media(
    media_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    media = service.get_media_for_user(db, user, media_id)
    mime = service.sniff_media_mime(media.data, media.mime_type, media.kind)
    inline = service.is_inline_safe(media.kind, mime)
    disp = "inline" if inline else "attachment"
    fname = service.ascii_filename(media.file_name, fallback=media.kind)
    data = media.data or b""
    total = len(data)
    base_headers = {
        "Content-Disposition": f'{disp}; filename="{fname}"',
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
    }

    range_header = (request.headers.get("range") or "").strip()
    if range_header and total > 0:
        match = _RANGE_RE.match(range_header)
        if match:
            start_s, end_s = match.group(1), match.group(2)
            if not start_s and end_s:
                suffix = min(int(end_s), total)
                start = max(0, total - suffix)
                end = total - 1
            else:
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else total - 1
                end = min(end, total - 1)
            if 0 <= start <= end < total:
                chunk = data[start : end + 1]
                return Response(
                    content=chunk,
                    status_code=status.HTTP_206_PARTIAL_CONTENT,
                    media_type=mime,
                    headers={
                        **base_headers,
                        "Content-Range": f"bytes {start}-{end}/{total}",
                        "Content-Length": str(len(chunk)),
                    },
                )
            return Response(
                content=b"",
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                headers={**base_headers, "Content-Range": f"bytes */{total}"},
            )

    return Response(
        content=data,
        media_type=mime,
        headers={
            **base_headers,
            "Content-Length": str(total),
        },
    )


@router.get("/messaging/chats/{chat_id}/avatar")
def get_avatar(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    data, mime_type = service.get_chat_avatar(db, user, chat_id)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/messaging/budget-context")
def get_budget_context(
    user: CurrentUser,
    db: DbSession,
    chat_id: Annotated[uuid.UUID | None, Query()] = None,
) -> BudgetContextOut:
    admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    return BudgetContextOut(**service.budget_context(db, user, chat_id=chat_id))


# ---------------------------------------------------------------- CRM 360° e respostas rápidas


@router.get("/messaging/chats/{chat_id}/crm-context")
def get_chat_crm_context(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    admin_service.assert_resource_allowed(db, user, "dashboard-crm")
    return service.chat_crm_context(db, user, chat_id)


@router.post("/messaging/chats/{chat_id}/crm-deal", status_code=status.HTTP_201_CREATED)
def post_chat_crm_deal(
    chat_id: uuid.UUID,
    body: ChatCrmDealIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    admin_service.assert_resource_allowed(db, user, "dashboard-crm")
    deal_val = body.value if body.value is not None else (body.amount or Decimal("0"))
    return service.create_chat_crm_deal(
        db,
        user,
        chat_id,
        title=body.title,
        value=deal_val,
        stage_id=body.stage_id,
        notes=body.notes,
    )


@router.post("/messaging/chats/{chat_id}/budget-entry", status_code=status.HTTP_201_CREATED)
def post_chat_budget_entry(
    chat_id: uuid.UUID,
    body: ChatBudgetEntryIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    admin_service.assert_resource_allowed(db, user, "meu-orcamento")
    return service.create_chat_budget_entry(
        db,
        user,
        chat_id,
        kind=body.kind,
        description=body.description,
        amount=body.amount,
        category_id=body.category_id,
        card_id=body.card_id,
        paid=body.paid,
        payment_method=body.payment_method,
        notes=body.notes,
        client_ref=body.client_ref,
    )


@router.get("/messaging/quick-replies")
def get_quick_replies(user: CurrentUser, db: DbSession) -> list[QuickReplyOut]:
    return [
        QuickReplyOut(
            id=row.id,
            shortcut=f"/{row.shortcut.lstrip('/')}",
            title=row.title,
            body=row.body,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in service.list_quick_replies(db, user)
    ]


@router.post("/messaging/quick-replies", status_code=status.HTTP_201_CREATED)
def post_quick_reply(body: QuickReplyIn, user: CurrentUser, db: DbSession) -> QuickReplyOut:
    row = service.create_quick_reply(
        db,
        user,
        shortcut=body.shortcut,
        title=body.title,
        body=body.body,
    )
    return QuickReplyOut(
        id=row.id,
        shortcut=f"/{row.shortcut.lstrip('/')}",
        title=row.title,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/messaging/quick-replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_quick_reply(reply_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_quick_reply(db, user, reply_id)


# ---------------------------------------------------------------- Fase C: Tarefas e Agenda


class ChatWorkTaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    project_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: Literal["low", "medium", "high", "urgent"] = "medium"


class ChatAgendaEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["meeting", "delivery", "visit", "reminder", "personal"] = "meeting"
    start_at: datetime
    location: str | None = Field(default=None, max_length=180)
    notes: str | None = Field(default=None, max_length=1000)


@router.get("/messaging/chats/{chat_id}/work-context")
def get_chat_work_context(chat_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    from app.services.work.projects import list_projects

    service.get_chat(db, user, chat_id)
    blocked = admin_service.effective_blocked_resources(db, user)
    projects = (
        [
            {"id": p["id"], "name": p["name"], "status": p["status"]}
            for p in list_projects(db, user.id)
        ]
        if "projetos" not in blocked
        else []
    )
    return {
        "projects": projects,
        "projects_blocked": "projetos" in blocked,
        "agenda_blocked": "agenda" in blocked,
    }


@router.post("/messaging/chats/{chat_id}/work-task", status_code=status.HTTP_201_CREATED)
def post_chat_work_task(
    chat_id: uuid.UUID,
    body: ChatWorkTaskIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    from app.services.work.projects import create_task_from_messaging

    return create_task_from_messaging(
        db,
        user,
        chat_id,
        title=body.title,
        project_id=body.project_id,
        message_id=body.message_id,
        due_date=body.due_date,
        priority=body.priority,
    )


@router.post("/messaging/chats/{chat_id}/agenda-event", status_code=status.HTTP_201_CREATED)
def post_chat_agenda_event(
    chat_id: uuid.UUID,
    body: ChatAgendaEventIn,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    from app.services.work.agenda import create_event_from_messaging

    return create_event_from_messaging(
        db,
        user,
        chat_id,
        title=body.title,
        start_at=body.start_at,
        kind=body.kind,
        location=body.location,
        notes=body.notes,
    )
