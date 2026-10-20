"""v0.7.5: solicitações (conversas com a administração), perfil e imagens."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile, status
from pydantic import BaseModel, StringConstraints, ValidationError

from app.api.deps import CurrentUser, DbSession, MailerDep
from app.core.errors import AppError
from app.core.months import parse_month
from app.models import SupportThread, User
from app.services import files, profile, support

router = APIRouter(tags=["solicitações e perfil"])

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Kind = Literal["idea", "bug", "other"]
Status = Literal["open", "in_progress", "planned", "answered", "resolved", "declined"]
Uploads = Annotated[list[UploadFile] | None, File(description="Até 3 imagens")]


class ThreadIn(BaseModel):
    title: Title
    kind: Kind
    message: Body
    page: Annotated[str, StringConstraints(max_length=200)] | None = None
    app_version: Annotated[str, StringConstraints(max_length=20)] | None = None


class ReplyIn(BaseModel):
    message: Body


class Attachment(BaseModel):
    id: uuid.UUID
    width: int
    height: int
    content_type: str


class MessageOut(BaseModel):
    id: uuid.UUID
    from_admin: bool
    body: str
    created_at: datetime
    attachments: list[Attachment]


class ThreadOut(BaseModel):
    id: uuid.UUID
    number: int
    title: str
    kind: str
    status: str
    unread: bool
    created_at: datetime
    last_message_at: datetime
    status_note: str | None = None
    planned_version: str | None = None
    announcement_id: uuid.UUID | None = None


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]


class Person(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_id: uuid.UUID | None


class AdminThreadOut(ThreadOut):
    user: Person
    messages_count: int
    page: str | None
    app_version: str | None


class AdminThreadDetail(AdminThreadOut):
    user_agent: str | None
    messages: list[MessageOut]


class PersonRow(BaseModel):
    user: Person
    total: int
    open: int
    unread: int
    last_message_at: datetime


class StatusIn(BaseModel):
    status: Status
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None


def _parse(model: type[BaseModel], **values: Any) -> Any:
    """Valida os campos do formulário (multipart) com as mesmas regras do JSON."""
    try:
        return model(**values)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        raise AppError(422, "validation_error", f"Campo inválido: {field}.") from exc


def _read(uploads: list[UploadFile] | None) -> list[bytes]:
    items = [u for u in (uploads or []) if u.filename]
    if len(items) > support.MAX_FILES:
        raise AppError(400, "too_many_files", f"Envie no máximo {support.MAX_FILES} imagens.")
    limit = files.RULES["attachment"].max_bytes
    data = []
    for upload in items:
        raw = upload.file.read(limit + 1)  # lê no máximo o limite (+1 para detectar excesso)
        if len(raw) > limit:
            raise AppError(
                413, "file_too_large", f"Cada imagem pode ter até {limit // files.MB} MB."
            )
        data.append(raw)
    return data


def _thread(thread: SupportThread, unread: bool) -> dict[str, Any]:
    return {
        "id": thread.id,
        "number": thread.number,
        "title": thread.title,
        "kind": thread.kind,
        "status": thread.status,
        "unread": unread,
        "created_at": thread.created_at,
        "last_message_at": thread.last_message_at,
        "status_note": thread.status_note,
        "planned_version": thread.planned_version,
        "announcement_id": thread.announcement_id,
    }


def _person(user: User, avatars: dict[uuid.UUID, uuid.UUID]) -> Person:
    return Person(
        id=user.id, email=user.email, display_name=user.display_name, avatar_id=avatars.get(user.id)
    )


# ---------------------------------------------------------------- usuário


@router.get("/support/threads")
def my_threads(user: CurrentUser, db: DbSession) -> list[ThreadOut]:
    return [ThreadOut(**_thread(t, t.user_unread)) for t in support.list_mine(db, user)]


@router.get("/support/unread")
def my_unread(user: CurrentUser, db: DbSession) -> dict[str, int]:
    return {"unread": support.unread_count(db, user)}


@router.post("/support/threads", status_code=status.HTTP_201_CREATED)
def create_thread(
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    message: Annotated[str, Form()],
    page: Annotated[str | None, Form()] = None,
    app_version: Annotated[str | None, Form()] = None,
    images: Uploads = None,
    user_agent: Annotated[str | None, Header()] = None,
) -> ThreadOut:
    data = _parse(
        ThreadIn, title=title, kind=kind, message=message, page=page, app_version=app_version
    )
    thread = support.create_thread(db, user, data.model_dump(), _read(images), user_agent)
    return ThreadOut(**_thread(thread, False))


@router.get("/support/threads/{thread_id}")
def my_thread(thread_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ThreadDetail:
    thread = support.open_mine(db, user, thread_id)
    return ThreadDetail(**_thread(thread, False), messages=support.messages(db, thread))


@router.post("/support/threads/{thread_id}/messages")
def reply(
    thread_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    message: Annotated[str, Form()],
    images: Uploads = None,
) -> ThreadDetail:
    data = _parse(ReplyIn, message=message)
    thread = support.reply_mine(db, user, thread_id, data.message, _read(images))
    return ThreadDetail(**_thread(thread, False), messages=support.messages(db, thread))


@router.post("/support/threads/{thread_id}/resolve")
def resolve(thread_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ThreadOut:
    thread = support.resolve_mine(db, user, thread_id)
    return ThreadOut(**_thread(thread, thread.user_unread))


# Compatibilidade: o botão antigo "Enviar feedback" (abas abertas antes do update).
class LegacyFeedbackIn(BaseModel):
    kind: Kind
    message: Body
    page: Annotated[str, StringConstraints(max_length=200)] | None = None
    app_version: Annotated[str, StringConstraints(max_length=20)] | None = None


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def legacy_feedback(
    body: LegacyFeedbackIn,
    user: CurrentUser,
    db: DbSession,
    user_agent: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    title = body.message.split("\n", 1)[0][:80].strip() or "Feedback"
    if len(title) < 3:
        title = "Feedback"
    support.create_thread(db, user, {**body.model_dump(), "title": title}, [], user_agent)
    return {"status": "ok"}


# ---------------------------------------------------------------- administração


@router.get("/admin/support/threads")
def admin_threads(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    user_id: uuid.UUID | None = None,
    kind: Kind | None = None,
    version: Annotated[str | None, Query(max_length=20)] = None,
) -> list[AdminThreadOut]:
    rows = support.admin_list(
        db, user, query=q, status=status_filter, user_id=user_id, kind=kind, version=version
    )
    avatars = profile.avatar_map(db, list({u.id for _, u, _ in rows}))
    return [
        AdminThreadOut(
            **_thread(t, t.admin_unread),
            user=_person(u, avatars),
            messages_count=n,
            page=t.page,
            app_version=t.app_version,
        )
        for t, u, n in rows
    ]


@router.get("/admin/support/people")
def admin_people(
    user: CurrentUser, db: DbSession, q: Annotated[str | None, Query(max_length=100)] = None
) -> list[PersonRow]:
    rows = support.admin_by_user(db, user, query=q)
    avatars = profile.avatar_map(db, [r["user"].id for r in rows])
    return [PersonRow(**{**r, "user": _person(r["user"], avatars)}) for r in rows]


@router.get("/admin/support/counts")
def admin_counts(user: CurrentUser, db: DbSession) -> dict[str, int]:
    return support.admin_counts(db, user)


def _admin_detail(db: DbSession, thread: SupportThread) -> AdminThreadDetail:
    author = db.get(User, thread.user_id)
    assert author is not None
    avatars = profile.avatar_map(db, [author.id])
    items = support.messages(db, thread)
    return AdminThreadDetail(
        **_thread(thread, thread.admin_unread),
        user=_person(author, avatars),
        messages_count=len(items),
        page=thread.page,
        app_version=thread.app_version,
        user_agent=thread.user_agent,
        messages=items,
    )


@router.get("/admin/support/threads/{thread_id}")
def admin_thread(thread_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AdminThreadDetail:
    return _admin_detail(db, support.admin_open(db, user, thread_id))


@router.post("/admin/support/threads/{thread_id}/messages")
def admin_reply(
    thread_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    mail: MailerDep,
    message: Annotated[str, Form()],
    images: Uploads = None,
) -> AdminThreadDetail:
    data = _parse(ReplyIn, message=message)
    thread = support.admin_reply(db, user, thread_id, data.message, _read(images), mail)
    return _admin_detail(db, thread)


@router.patch("/admin/support/threads/{thread_id}")
def admin_status(
    thread_id: uuid.UUID, body: StatusIn, user: CurrentUser, db: DbSession, mail: MailerDep
) -> AdminThreadDetail:
    thread = support.admin_set_status(
        db, user, thread_id, body.status, body.note, body.version, mail
    )
    return _admin_detail(db, thread)


@router.get("/admin/support/versions")
def admin_versions(user: CurrentUser, db: DbSession) -> list[str]:
    """Versões já usadas nas tarefas (para o filtro e para sugerir ao planejar)."""
    return support.admin_versions(db, user)


# ---------------------------------------------------------------- resposta a um recado


@router.post("/inbox/{item_id}/reply")
def reply_announcement(
    item_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    message: Annotated[str, Form()],
    images: Uploads = None,
) -> ThreadDetail:
    data = _parse(ReplyIn, message=message)
    thread = support.reply_announcement(db, user, item_id, data.message, _read(images))
    return ThreadDetail(**_thread(thread, False), messages=support.messages(db, thread))


# ---------------------------------------------------------------- perfil

ProfileText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]


class ProfilePrefs(BaseModel):
    stats: dict[str, bool] | None = None
    show_values_in_recap: bool | None = None


class ProfilePatch(BaseModel):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = (
        None
    )
    bio: ProfileText | None = None
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    profession: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = (
        None
    )
    prefs: ProfilePrefs | None = None


class ProfileOut(BaseModel):
    display_name: str | None
    bio: str | None
    city: str | None
    profession: str | None
    email: str
    member_since: datetime
    avatar_id: uuid.UUID | None
    banner_id: uuid.UUID | None
    prefs: dict[str, Any]


@router.get("/profile")
def get_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    return ProfileOut(**profile.get_profile(db, user))


@router.patch("/profile")
def update_profile(body: ProfilePatch, user: CurrentUser, db: DbSession) -> ProfileOut:
    changes = body.model_dump(exclude_unset=True)
    return ProfileOut(**profile.update_profile(db, user, changes))


def _read_one(upload: UploadFile, purpose: str) -> bytes:
    limit = files.RULES[purpose].max_bytes
    raw = upload.file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(413, "file_too_large", f"A imagem pode ter até {limit // files.MB} MB.")
    return raw


@router.put("/profile/{purpose}")
def set_image(
    purpose: Literal["avatar", "banner"],
    user: CurrentUser,
    db: DbSession,
    image: Annotated[UploadFile, File()],
) -> ProfileOut:
    return ProfileOut(**profile.set_image(db, user, purpose, _read_one(image, purpose)))


@router.delete("/profile/{purpose}")
def remove_image(
    purpose: Literal["avatar", "banner"], user: CurrentUser, db: DbSession
) -> ProfileOut:
    return ProfileOut(**profile.remove_image(db, user, purpose))


@router.get("/profile/summary")
def profile_summary(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return profile.summary(db, user)


@router.get("/profile/retrospective")
def profile_retrospective(
    user: CurrentUser,
    db: DbSession,
    period: Literal["month", "year"] = "month",
    month: str | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> dict[str, Any]:
    return profile.retrospective(
        db, user, period, month=parse_month(month) if month else None, year=year
    )


# ---------------------------------------------------------------- imagens


@router.get("/files/{file_id}")
def get_file(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    item = files.get_for(db, user, file_id)
    return Response(
        content=item.data,
        media_type=item.content_type,
        headers={
            # Imagem nunca muda (trocar a foto gera outro id): pode ficar no cache do navegador.
            "Cache-Control": "private, max-age=604800, immutable",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'",
        },
    )
