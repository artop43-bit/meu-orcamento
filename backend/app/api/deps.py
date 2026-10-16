from typing import Annotated

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import AppError
from app.db.session import get_db
from app.models import User
from app.services import auth as auth_service
from app.services.auth import Mailer

DbSession = Annotated[Session, Depends(get_db)]


def session_cookie_name() -> str:
    # O prefixo __Host- exige HTTPS e impede que subdomínios sobrescrevam o cookie.
    return "__Host-session" if get_settings().secure_cookies else "session"


def get_session_token(request: Request) -> str | None:
    return request.cookies.get(session_cookie_name())


SessionToken = Annotated[str | None, Depends(get_session_token)]


def get_current_user(db: DbSession, token: SessionToken) -> User:
    user = auth_service.user_from_session(db, token)
    if user is None:
        raise AppError(401, "not_authenticated", "Faça login para continuar.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_mailer(background: BackgroundTasks) -> Mailer:
    def mail(to: str, subject: str, body: str) -> None:
        background.add_task(send_email, to, subject, body)

    return mail


MailerDep = Annotated[Mailer, Depends(get_mailer)]
