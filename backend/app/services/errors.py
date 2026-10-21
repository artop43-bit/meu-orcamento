"""Painel de erros (v1.3): erros das telas e do servidor, agrupados para a administração.

Sem serviço externo. Guardamos só o necessário para corrigir: tipo, mensagem, tela, aparelho e
versão. Números longos e e-mails da mensagem são mascarados (nada de valores, documentos ou
contatos), e senhas nunca chegam aqui. Cada grupo guarda a contagem e a última ocorrência;
grupos sem novidade há 90 dias são apagados pela limpeza diária.
"""

import hashlib
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import ErrorEvent

RETENTION = timedelta(days=90)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_NUMBER = re.compile(r"\d[\d.,/-]{3,}")
_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def scrub(text: str | None, limit: int) -> str | None:
    """Tira da mensagem o que pode identificar alguém ou revelar valores."""
    if not text:
        return None
    clean = _EMAIL.sub("[e-mail]", text)
    clean = _UUID.sub("[id]", clean)
    clean = _TOKEN.sub("[código]", clean)
    clean = _NUMBER.sub("#", clean)
    return clean.strip()[:limit] or None


def _path(path: str | None) -> str | None:
    # Telas com ids e meses na URL viram um caminho só (/dividas/[id], /orcamento/[mês]).
    if not path:
        return None
    clean = path.split("?")[0]
    clean = _UUID.sub("[id]", clean)
    clean = re.sub(r"/\d{4}-\d{2}(-\d{2})?", "/[data]", clean)
    return clean[:200]


def record(
    db: Session,
    *,
    source: str,
    name: str | None,
    message: str | None,
    path: str | None,
    user_agent: str | None,
    release: str | None,
    detail: str | None = None,
) -> ErrorEvent:
    name_clean = scrub(name, 80) or "Error"
    message_clean = scrub(message, 300) or "(sem mensagem)"
    where = _path(path)
    fingerprint = hashlib.sha256(
        f"{source}|{name_clean}|{message_clean}|{where}".encode()
    ).hexdigest()[:32]
    now = utcnow()
    event = db.scalar(select(ErrorEvent).where(ErrorEvent.fingerprint == fingerprint))
    if event is None:
        event = ErrorEvent(
            fingerprint=fingerprint,
            source=source,
            name=name_clean,
            message=message_clean,
            path=where,
            count=0,
            first_seen=now,
        )
        db.add(event)
    event.count += 1
    event.last_seen = now
    event.user_agent = (user_agent or "")[:200] or None
    event.release = (release or "")[:20] or None
    event.detail = scrub(detail, 1500)
    event.resolved_at = None
    db.commit()
    return event


def overview(db: Session) -> list[ErrorEvent]:
    return list(
        db.scalars(
            select(ErrorEvent)
            .order_by(ErrorEvent.resolved_at.is_not(None), ErrorEvent.last_seen.desc())
            .limit(100)
        )
    )


def resolve(db: Session, event_id: Any) -> None:
    event = db.get(ErrorEvent, event_id)
    if event is not None:
        event.resolved_at = utcnow()
        db.commit()


def cleanup(db: Session) -> int:
    return db.execute(
        delete(ErrorEvent).where(ErrorEvent.last_seen <= utcnow() - RETENTION)
    ).rowcount
