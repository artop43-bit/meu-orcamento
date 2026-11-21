"""Consultas utilitárias compartilhadas pelos serviços do Hub."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import ORMExecuteState, Session

from app.core.errors import AppError

_SQLITE_TX_LOCK = threading.RLock()
_SQLITE_GUARD_DEPTH_KEY = "_sqlite_row_lock_depth"
_SQLITE_TX_WRITES_KEY = "_sqlite_tx_has_writes"


@event.listens_for(Session, "after_flush")
def _mark_session_flush(session: Session, _flush_context: object) -> None:
    session.info[_SQLITE_TX_WRITES_KEY] = True


@event.listens_for(Session, "do_orm_execute")
def _mark_session_write_execute(execute_state: ORMExecuteState) -> None:
    if not execute_state.is_select:
        execute_state.session.info[_SQLITE_TX_WRITES_KEY] = True


@event.listens_for(Session, "after_transaction_end")
def _clear_session_writes(session: Session, _transaction: object) -> None:
    if not session.in_transaction():
        session.info.pop(_SQLITE_TX_WRITES_KEY, None)


@contextmanager
def row_lock_guard(db: Session, *, user_id: uuid.UUID | None = None) -> Iterator[None]:
    """Serializa transações com lock no SQLite e trava opcionalmente o usuário no Postgres."""
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        if user_id is not None:
            from app.models import User

            db.scalar(select(User.id).where(User.id == user_id).with_for_update())
        yield
        return
    with _SQLITE_TX_LOCK:
        depth = int(db.info.get(_SQLITE_GUARD_DEPTH_KEY, 0))
        # Encerra apenas snapshot de leitura puro antes do primeiro lock (ex.: get_current_user),
        # sem descartar transações que já tenham feito flush/escrita antes da trava.
        if (
            depth == 0
            and db.in_transaction()
            and not db.in_nested_transaction()
            and not db.info.get(_SQLITE_TX_WRITES_KEY)
            and not db.new
            and not db.dirty
            and not db.deleted
        ):
            db.rollback()
        db.info[_SQLITE_GUARD_DEPTH_KEY] = depth + 1
        try:
            yield
        finally:
            if depth == 0:
                db.info.pop(_SQLITE_GUARD_DEPTH_KEY, None)
            else:
                db.info[_SQLITE_GUARD_DEPTH_KEY] = depth


def get_owned[ModelT](
    db: Session,
    model: type[ModelT],
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    error_code: str = "not_found",
    error_msg: str = "Registro não encontrado.",
    lock: bool = False,
) -> ModelT:
    """Busca um registro pelo id garantindo isolamento estrito por `user_id`."""
    stmt = select(model).where(model.id == item_id, model.user_id == user_id)  # type: ignore[attr-defined]
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise AppError(404, error_code, error_msg)
    return row
