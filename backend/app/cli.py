"""Tarefas de manutenção. Uso: `python -m app.cli cleanup`.

Em produção, rode `cleanup` uma vez por dia (agendado no servidor, na fase de deploy).
"""

import argparse
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.models import AuthToken, SecurityEvent, UserSession

USED_TOKEN_RETENTION = timedelta(days=7)


def cleanup(db: Session) -> dict[str, int]:
    """Apaga sessões vencidas, links de e-mail usados/vencidos e eventos antigos."""
    now = utcnow()
    sessions = db.execute(delete(UserSession).where(UserSession.expires_at <= now)).rowcount
    tokens = db.execute(
        delete(AuthToken).where(
            or_(
                AuthToken.expires_at <= now - USED_TOKEN_RETENTION,
                AuthToken.used_at <= now - USED_TOKEN_RETENTION,
            )
        )
    ).rowcount
    retention = timedelta(days=get_settings().security_event_retention_days)
    events = db.execute(
        delete(SecurityEvent).where(SecurityEvent.created_at <= now - retention)
    ).rowcount
    db.commit()
    return {"sessions": sessions, "tokens": tokens, "security_events": events}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    parser.add_argument("command", choices=["cleanup"])
    args = parser.parse_args()

    from app.db.session import SessionLocal

    if args.command == "cleanup":
        with SessionLocal() as db:
            removed = cleanup(db)
        print("Removidos:", ", ".join(f"{k}={v}" for k, v in removed.items()))


if __name__ == "__main__":
    main()
