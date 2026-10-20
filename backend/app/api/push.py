"""v1.0: notificações no aparelho (inscrição, preferências e teste)."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.services import push

router = APIRouter(prefix="/push", tags=["notificações no aparelho"])


class PushConfig(BaseModel):
    enabled: bool
    public_key: str
    devices: int
    push_due: bool
    push_messages: bool
    push_alerts: bool


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=600)
    keys: SubscriptionKeys


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=600)


class PushPrefs(BaseModel):
    push_due: bool | None = None
    push_messages: bool | None = None
    push_alerts: bool | None = None


class TestOut(BaseModel):
    sent: int


def _config(db, user) -> PushConfig:  # type: ignore[no-untyped-def]
    return PushConfig(
        enabled=push.enabled(),
        public_key=get_settings().vapid_public_key if push.enabled() else "",
        devices=len(push.devices(db, user)),
        push_due=user.push_due,
        push_messages=user.push_messages,
        push_alerts=user.push_alerts,
    )


@router.get("")
def config(user: CurrentUser, db: DbSession) -> PushConfig:
    return _config(db, user)


@router.post("/subscribe")
def subscribe(body: SubscribeIn, request: Request, user: CurrentUser, db: DbSession) -> PushConfig:
    push.subscribe(
        db, user, body.endpoint, body.keys.p256dh, body.keys.auth, request.headers.get("user-agent")
    )
    return _config(db, user)


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn, user: CurrentUser, db: DbSession) -> PushConfig:
    push.unsubscribe(db, user, body.endpoint)
    return _config(db, user)


@router.patch("/prefs")
def prefs(body: PushPrefs, user: CurrentUser, db: DbSession) -> PushConfig:
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    return _config(db, user)


@router.post("/test")
def test(user: CurrentUser, db: DbSession) -> TestOut:
    sent = push.send(
        db,
        user,
        "messages",
        "Notificações ativadas",
        "Você vai receber aqui os avisos do Meu Orçamento.",
        "/ajustes/app",
        force=True,
    )
    return TestOut(sent=sent)
