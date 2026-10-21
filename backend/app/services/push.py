"""v1.0: notificações no aparelho (Web Push), para o app Android e para o site instalado.

Cada aparelho inscrito recebe as notificações dos tipos ligados pela pessoa: vencimentos,
mensagens (respostas e recados) e alertas. Sem as chaves VAPID no servidor, fica desligado.
Inscrições que o serviço de push dá como expiradas (404/410) são removidas.
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import PushSubscription, User

logger = logging.getLogger(__name__)

KINDS = {
    "due": "push_due",
    "messages": "push_messages",
    "alerts": "push_alerts",
    "weekly": "push_weekly",
}
TIMEOUT = 5


def enabled() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def subscribe(
    db: Session, user: User, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> PushSubscription:
    if not enabled():
        raise AppError(503, "push_disabled", "As notificações no aparelho não estão disponíveis.")
    if not endpoint.startswith("https://"):
        raise AppError(400, "invalid_endpoint", "Inscrição inválida.")
    item = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if item is None:
        item = PushSubscription(endpoint=endpoint)
        db.add(item)
    # O mesmo aparelho pode trocar de conta: a inscrição passa para quem está logado agora.
    item.user_id = user.id
    item.p256dh = p256dh
    item.auth = auth
    item.user_agent = (user_agent or "")[:255] or None
    db.commit()
    return item


def unsubscribe(db: Session, user: User, endpoint: str) -> None:
    item = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id
        )
    )
    if item is not None:
        db.delete(item)
        db.commit()


def devices(db: Session, user: User) -> list[PushSubscription]:
    return list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)))


def _webpush(item: PushSubscription, payload: dict[str, Any]) -> bool:
    """Envia; devolve False se a inscrição expirou (deve ser removida)."""
    from pywebpush import WebPushException, webpush

    settings = get_settings()
    try:
        webpush(
            subscription_info={
                "endpoint": item.endpoint,
                "keys": {"p256dh": item.p256dh, "auth": item.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=TIMEOUT,
            ttl=24 * 3600,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return False
        logger.warning("Push não enviado para %s: %s", item.user_id, exc)
    except Exception as exc:  # rede fora do ar: tenta de novo no próximo aviso
        logger.warning("Push não enviado para %s: %s", item.user_id, exc)
    return True


def send(
    db: Session, user: User, kind: str, title: str, body: str, url: str = "/", force: bool = False
) -> int:
    """Notifica os aparelhos da pessoa se o tipo estiver ligado. Devolve quantos receberam."""
    if not enabled() or not (force or getattr(user, KINDS.get(kind, ""), False)):
        return 0
    payload = {"title": title[:120], "body": body[:240], "url": url, "tag": kind}
    sent = 0
    for item in devices(db, user):
        if _webpush(item, payload):
            sent += 1
        else:
            db.delete(item)
    db.commit()
    return sent
