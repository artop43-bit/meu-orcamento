"""Tarefas de manutenção.

python -m app.cli cleanup    roda a limpeza uma vez
python -m app.cli schedule   roda a limpeza agora e depois uma vez por dia (produção)
"""

import argparse
import time
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


def run_cleanup() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        removed = cleanup(db)
    print("Removidos:", ", ".join(f"{k}={v}" for k, v in removed.items()), flush=True)


def schedule(interval: timedelta = timedelta(hours=24)) -> None:
    """Roda a limpeza ao iniciar e depois a cada `interval` (contêiner "scheduler")."""
    while True:
        try:
            run_cleanup()
        except Exception as exc:  # um erro pontual (ex.: banco reiniciando) não derruba o loop
            print(f"Falha na limpeza: {exc}", flush=True)
        time.sleep(interval.total_seconds())


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    parser.add_argument("command", choices=["cleanup", "schedule"])
    args = parser.parse_args()

    if args.command == "cleanup":
        run_cleanup()
    else:
        schedule()


if __name__ == "__main__":
    main()
