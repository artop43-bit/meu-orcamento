import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession, MailerDep, SessionToken, session_cookie_name
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db.types import utcnow
from app.schemas.auth import (
    ChangePasswordIn,
    CodeIn,
    DeleteAccountIn,
    Disable2faIn,
    EmailIn,
    Login2faIn,
    LoginIn,
    LoginOut,
    MessageOut,
    RecoveryCodesOut,
    RegisterIn,
    ResetPasswordIn,
    SecurityEventOut,
    SessionOut,
    TokenIn,
    TwoFactorPromptIn,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
    UserOut,
)
from app.services import admin as admin_service
from app.services import auth as auth_service
from app.services.auth import LoginResult

router = APIRouter(prefix="/auth", tags=["auth"])

UserAgent = Annotated[str | None, Header()]

# Limites por IP (requisições, janela em segundos).
LIMIT_LOGIN = [Depends(rate_limit("login", 20, 15 * 60))]
LIMIT_2FA = [Depends(rate_limit("login_2fa", 20, 15 * 60))]
LIMIT_SIGNUP = [Depends(rate_limit("signup", 10, 3600))]
LIMIT_EMAIL = [Depends(rate_limit("email", 10, 3600))]
LIMIT_TOKEN = [Depends(rate_limit("token", 30, 3600))]
LIMIT_SENSITIVE = [Depends(rate_limit("sensitive", 10, 15 * 60))]

CHECK_INBOX = "Se o e-mail puder ser usado, você receberá uma mensagem com os próximos passos."


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _user_out(db: DbSession, user: CurrentUser) -> UserOut:
    blocked = admin_service.effective_blocked_resources(db, user)
    quota = getattr(user, "storage_quota_mb", 50) or 50
    out = UserOut.model_validate(
        {
            **{
                k: getattr(user, k)
                for k in UserOut.model_fields
                if k not in ("blocked_resources", "storage_quota_mb") and hasattr(user, k)
            },
            "blocked_resources": blocked,
            "storage_quota_mb": quota,
        }
    )
    return out


def _login_response(db: DbSession, response: Response, result: LoginResult) -> LoginOut:
    if result.challenge is not None:
        return LoginOut(status="2fa_required", challenge=result.challenge)
    assert result.session_token is not None
    assert result.user is not None
    _set_session_cookie(response, result.session_token)
    return LoginOut(status="ok", user=_user_out(db, result.user))


# ---------------------------------------------------------------- cadastro


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, dependencies=LIMIT_SIGNUP)
def register(body: RegisterIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.register(db, body.email, body.password, mail)
    return MessageOut(message=CHECK_INBOX)


@router.post("/verify-email", dependencies=LIMIT_TOKEN)
def verify_email(body: TokenIn, db: DbSession) -> MessageOut:
    auth_service.verify_email(db, body.token)
    return MessageOut(message="E-mail confirmado. Você já pode entrar.")


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED, dependencies=LIMIT_EMAIL)
def resend_verification(body: EmailIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.resend_verification(db, body.email, mail)
    return MessageOut(message=CHECK_INBOX)


# ---------------------------------------------------------------- login


@router.post("/login", dependencies=LIMIT_LOGIN)
def login(
    body: LoginIn,
    response: Response,
    db: DbSession,
    mail: MailerDep,
    user_agent: UserAgent = None,
) -> LoginOut:
    result = auth_service.login(db, body.email, body.password, user_agent, mail)
    return _login_response(db, response, result)


@router.post("/login/2fa", dependencies=LIMIT_2FA)
def login_2fa(
    body: Login2faIn,
    response: Response,
    db: DbSession,
    mail: MailerDep,
    user_agent: UserAgent = None,
) -> LoginOut:
    result = auth_service.complete_login_2fa(db, body.challenge, body.code, user_agent, mail)
    return _login_response(db, response, result)


class NotMeOut(BaseModel):
    message: str
    reset_token: str


@router.post("/not-me", dependencies=LIMIT_TOKEN)
def not_me(body: TokenIn, db: DbSession) -> NotMeOut:
    """Link "Não fui eu" do aviso de novo acesso."""
    reset = auth_service.not_me(db, body.token)
    return NotMeOut(
        message="Todas as sessões foram encerradas. Crie uma nova senha para proteger a conta.",
        reset_token=reset,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DbSession, token: SessionToken) -> None:
    auth_service.logout(db, token)
    response.delete_cookie(session_cookie_name(), path="/")


@router.get("/me")
def me(user: CurrentUser, db: DbSession) -> UserOut:
    return _user_out(db, user)


# ---------------------------------------------------------------- senha


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, dependencies=LIMIT_EMAIL)
def forgot_password(body: EmailIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.forgot_password(db, body.email, mail)
    return MessageOut(message=CHECK_INBOX)


@router.post("/reset-password", dependencies=LIMIT_TOKEN)
def reset_password(body: ResetPasswordIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.reset_password(db, body.token, body.password, mail)
    return MessageOut(message="Senha redefinida. Entre com a nova senha.")


@router.post(
    "/change-password", status_code=status.HTTP_204_NO_CONTENT, dependencies=LIMIT_SENSITIVE
)
def change_password(
    body: ChangePasswordIn, user: CurrentUser, db: DbSession, token: SessionToken, mail: MailerDep
) -> None:
    auth_service.change_password(db, user, body.current_password, body.new_password, token, mail)


# ---------------------------------------------------------------- 2FA


@router.get("/2fa")
def two_factor_status(user: CurrentUser, db: DbSession) -> TwoFactorStatusOut:
    return TwoFactorStatusOut(
        enabled=user.totp_enabled,
        recovery_codes_remaining=auth_service.remaining_recovery_codes(db, user),
    )


@router.post("/2fa/setup")
def two_factor_setup(user: CurrentUser, db: DbSession) -> TwoFactorSetupOut:
    secret, uri = auth_service.setup_2fa(db, user)
    return TwoFactorSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/2fa/enable")
def two_factor_enable(
    body: CodeIn, user: CurrentUser, db: DbSession, mail: MailerDep
) -> RecoveryCodesOut:
    codes = auth_service.enable_2fa(db, user, body.code, mail)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT, dependencies=LIMIT_SENSITIVE)
def two_factor_disable(
    body: Disable2faIn, user: CurrentUser, db: DbSession, mail: MailerDep
) -> None:
    auth_service.disable_2fa(db, user, body.password, body.code, mail)


@router.post("/2fa/prompt", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_prompt(body: TwoFactorPromptIn, user: CurrentUser, db: DbSession) -> None:
    """Esconde (ou volta a mostrar) o convite para ativar a verificação em duas etapas."""
    user.twofa_prompt_dismissed_at = utcnow() if body.dismissed else None
    db.commit()


@router.post("/2fa/recovery-codes")
def regenerate_recovery_codes(body: CodeIn, user: CurrentUser, db: DbSession) -> RecoveryCodesOut:
    codes = auth_service.regenerate_recovery_codes(db, user, body.code)
    return RecoveryCodesOut(recovery_codes=codes)


# ---------------------------------------------------------------- sessões e atividade


@router.get("/sessions")
def list_sessions(user: CurrentUser, db: DbSession, token: SessionToken) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in auth_service.list_sessions(db, user, token)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID, user: CurrentUser, db: DbSession, token: SessionToken
) -> None:
    auth_service.revoke_session(db, user, session_id, token)


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(user: CurrentUser, db: DbSession, token: SessionToken) -> None:
    auth_service.revoke_other_sessions(db, user, token)


@router.get("/events")
def list_events(user: CurrentUser, db: DbSession) -> list[SecurityEventOut]:
    return [SecurityEventOut.model_validate(e) for e in auth_service.list_events(db, user)]


# ---------------------------------------------------------------- exclusão de conta


@router.post(
    "/delete-account", status_code=status.HTTP_204_NO_CONTENT, dependencies=LIMIT_SENSITIVE
)
def delete_account(
    body: DeleteAccountIn, response: Response, user: CurrentUser, db: DbSession, mail: MailerDep
) -> None:
    auth_service.delete_account(db, user, body.password, body.code, mail)
    response.delete_cookie(session_cookie_name(), path="/")
