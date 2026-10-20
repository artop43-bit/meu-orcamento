"""Tarefas de manutenção.

python -m app.cli cleanup    roda a limpeza uma vez
python -m app.cli schedule   limpeza diária e avisos por e-mail às 8h (produção)
python -m app.cli seed-demo  cria a conta de demonstração com dados (nunca em produção)
"""

import argparse
import time
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.models import AuthToken, EmailLog, SecurityEvent, UserSession

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
    emails = db.execute(
        delete(EmailLog).where(EmailLog.created_at <= now - timedelta(days=30))
    ).rowcount
    db.commit()
    return {"sessions": sessions, "tokens": tokens, "security_events": events, "emails": emails}


def run_cleanup() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        removed = cleanup(db)
    print("Removidos:", ", ".join(f"{k}={v}" for k, v in removed.items()), flush=True)


def run_notifications() -> dict[str, int]:
    from app.db.session import SessionLocal
    from app.services import notify

    with SessionLocal() as db:
        return notify.run_daily(db)


def run_snapshots() -> int:
    """Foto do patrimônio do mês de cada conta (alimenta o gráfico mês a mês)."""
    from app.db.session import SessionLocal
    from app.services import loans

    with SessionLocal() as db:
        return loans.snapshot_all(db)


def schedule(tick: timedelta = timedelta(minutes=10)) -> None:
    """Contêiner "scheduler": limpeza uma vez por dia e os avisos por e-mail a partir das 8h
    (horário de Brasília). Rodar várias vezes no dia é seguro: nenhum aviso sai duplicado."""
    last_cleanup = 0.0
    while True:
        if time.monotonic() - last_cleanup >= 24 * 3600 or last_cleanup == 0.0:
            try:
                run_cleanup()
                run_snapshots()
                last_cleanup = time.monotonic()
            except Exception as exc:  # um erro pontual (ex.: banco reiniciando) não derruba o loop
                print(f"Falha na limpeza: {exc}", flush=True)
        try:
            sent = run_notifications()
            if any(sent.values()):
                print(f"Avisos enviados: {sent}", flush=True)
        except Exception as exc:
            print(f"Falha nos avisos: {exc}", flush=True)
        time.sleep(tick.total_seconds())


def run_seed_demo(credentials_file: str | None, *, with_data: bool, reset: bool) -> None:
    from app.db.session import SessionLocal
    from app.demo import DEMO_EMAIL, seed_demo

    with SessionLocal() as db:
        password, created = seed_demo(db, with_data=with_data, reset=reset)
    text = f"E-mail: {DEMO_EMAIL}\nSenha:  {password}\n"
    if credentials_file:
        with open(credentials_file, "w", encoding="utf-8") as f:
            f.write(text)
    content = "com dados de exemplo" if with_data else "vazia"
    status = f"criada ({content})" if created else "já existia; senha redefinida"
    print(f"Conta de demonstração {status}.\n{text}", flush=True)


def run_feedback(limit: int = 30) -> None:
    """Mostra as últimas solicitações recebidas pelo app (para ler pelo SSH)."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import SupportMessage, SupportThread, User

    labels = {"bug": "PROBLEMA", "idea": "SUGESTÃO", "other": "OUTRO"}
    with SessionLocal() as db:
        rows = db.execute(
            select(SupportThread, User.email)
            .join(User, User.id == SupportThread.user_id)
            .order_by(SupportThread.last_message_at.desc())
            .limit(limit)
        ).all()
        if not rows:
            print("Nenhuma solicitação ainda.", flush=True)
        for thread, email in rows:
            last = db.scalar(
                select(SupportMessage)
                .where(SupportMessage.thread_id == thread.id)
                .order_by(SupportMessage.created_at.desc())
                .limit(1)
            )
            when = thread.last_message_at.strftime("%d/%m %H:%M")
            kind = labels.get(thread.kind, thread.kind)
            print(f"[{when}] {kind} · {thread.status} · {email} · {thread.title}")
            if last is not None:
                who = "admin" if last.from_admin else "usuário"
                print(f"  ({who}) {last.body}\n", flush=True)


def run_admin(command: str, email: str) -> None:
    """Liberar, bloquear ou tornar admin uma conta pelo terminal (ex.: o primeiro admin)."""
    from app.db.session import SessionLocal
    from app.services import admin

    with SessionLocal() as db:
        print(admin.cli_action(db, command, email), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    parser.add_argument(
        "command",
        choices=["cleanup", "schedule", "seed-demo", "feedback", "make-admin", "approve", "block"],
    )
    parser.add_argument("email", nargs="?", help="make-admin/approve/block: e-mail da conta")
    parser.add_argument(
        "--credentials-file", help="seed-demo: também grava e-mail e senha neste arquivo"
    )
    parser.add_argument(
        "--vazia", action="store_true", help="seed-demo: conta sem dados (como um usuário novo)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="seed-demo: apaga a conta e os dados antes de criar"
    )
    args = parser.parse_args()

    if args.command == "cleanup":
        run_cleanup()
    elif args.command == "schedule":
        schedule()
    elif args.command == "feedback":
        run_feedback()
    elif args.command in ("make-admin", "approve", "block"):
        if not args.email:
            parser.error("informe o e-mail da conta")
        run_admin(args.command, args.email)
    else:
        run_seed_demo(args.credentials_file, with_data=not args.vazia, reset=args.reset)


if __name__ == "__main__":
    main()
