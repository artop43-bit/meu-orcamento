"""v0.8: preferências dos avisos por e-mail, descadastro com um clique e boas-vindas."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.db.types import utcnow
from app.services import notify

router = APIRouter(tags=["avisos e boas-vindas"])


class NotifyPrefs(BaseModel):
    notify_due: bool
    notify_due_days: Literal[1, 3, 7]
    notify_hide_values: bool
    notify_monthly: bool


class NotifyPrefsPatch(BaseModel):
    notify_due: bool | None = None
    notify_due_days: Literal[1, 3, 7] | None = None
    notify_hide_values: bool | None = None
    notify_monthly: bool | None = None


def _prefs(user) -> NotifyPrefs:  # type: ignore[no-untyped-def]
    return NotifyPrefs(
        notify_due=user.notify_due,
        notify_due_days=user.notify_due_days if user.notify_due_days in (1, 3, 7) else 3,
        notify_hide_values=user.notify_hide_values,
        notify_monthly=user.notify_monthly,
    )


@router.get("/notifications/prefs")
def get_prefs(user: CurrentUser) -> NotifyPrefs:
    return _prefs(user)


@router.patch("/notifications/prefs")
def update_prefs(body: NotifyPrefsPatch, user: CurrentUser, db: DbSession) -> NotifyPrefs:
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    return _prefs(user)


class UnsubscribeOut(BaseModel):
    message: str
    kind: str


@router.post("/notifications/unsubscribe")
async def unsubscribe(
    request: Request, db: DbSession, t: Annotated[str | None, Query(max_length=200)] = None
) -> UnsubscribeOut:
    """Descadastro sem login: pelo link do e-mail (página do app) ou pelo botão do provedor."""
    token = t
    if token is None and request.headers.get("content-type", "").startswith("application/json"):
        token = (await request.json()).get("token")
    result = notify.unsubscribe(db, token or "")
    if result is None:
        raise AppError(
            400, "invalid_token", "Link inválido. Ajuste os avisos em Ajustes › Preferências."
        )
    _, kind = result
    return UnsubscribeOut(
        message=f"Você não vai mais receber {notify.KINDS[kind]}. "
        "É possível reativar em Ajustes › Preferências.",
        kind=kind,
    )


class OnboardingOut(BaseModel):
    done: bool


@router.post("/onboarding/done")
def onboarding_done(user: CurrentUser, db: DbSession) -> OnboardingOut:
    """Configuração inicial concluída ou pulada: não aparece de novo."""
    if user.onboarded_at is None:
        user.onboarded_at = utcnow()
        db.commit()
    return OnboardingOut(done=True)
