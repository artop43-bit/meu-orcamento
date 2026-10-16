from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.api.deps import CurrentUser, DbSession, MailerDep, SessionToken, session_cookie_name
from app.core.config import get_settings
from app.schemas.auth import (
    ChangePasswordIn,
    CodeIn,
    Disable2faIn,
    EmailIn,
    Login2faIn,
    LoginIn,
    LoginOut,
    MessageOut,
    RecoveryCodesOut,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
    UserOut,
)
from app.services import auth as auth_service
from app.services.auth import LoginResult

router = APIRouter(prefix="/auth", tags=["auth"])

UserAgent = Annotated[str | None, Header()]

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


def _login_response(response: Response, result: LoginResult) -> LoginOut:
    if result.challenge is not None:
        return LoginOut(status="2fa_required", challenge=result.challenge)
    assert result.session_token is not None
    _set_session_cookie(response, result.session_token)
    return LoginOut(status="ok", user=UserOut.model_validate(result.user))


# ---------------------------------------------------------------- cadastro


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register(body: RegisterIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.register(db, body.email, body.password, mail)
    return MessageOut(message=CHECK_INBOX)


@router.post("/verify-email")
def verify_email(body: TokenIn, db: DbSession) -> MessageOut:
    auth_service.verify_email(db, body.token)
    return MessageOut(message="E-mail confirmado. Você já pode entrar.")


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(body: EmailIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.resend_verification(db, body.email, mail)
    return MessageOut(message=CHECK_INBOX)


# ---------------------------------------------------------------- login


@router.post("/login")
def login(
    body: LoginIn, response: Response, db: DbSession, user_agent: UserAgent = None
) -> LoginOut:
    result = auth_service.login(db, body.email, body.password, user_agent)
    return _login_response(response, result)


@router.post("/login/2fa")
def login_2fa(
    body: Login2faIn, response: Response, db: DbSession, user_agent: UserAgent = None
) -> LoginOut:
    result = auth_service.complete_login_2fa(db, body.challenge, body.code, user_agent)
    return _login_response(response, result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DbSession, token: SessionToken) -> None:
    auth_service.logout(db, token)
    response.delete_cookie(session_cookie_name(), path="/")


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


# ---------------------------------------------------------------- senha


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: EmailIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.forgot_password(db, body.email, mail)
    return MessageOut(message=CHECK_INBOX)


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, db: DbSession, mail: MailerDep) -> MessageOut:
    auth_service.reset_password(db, body.token, body.password, mail)
    return MessageOut(message="Senha redefinida. Entre com a nova senha.")


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordIn, user: CurrentUser, db: DbSession, token: SessionToken, mail: MailerDep
) -> None:
    auth_service.change_password(
        db, user, body.current_password, body.new_password, token, mail
    )


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


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_disable(
    body: Disable2faIn, user: CurrentUser, db: DbSession, mail: MailerDep
) -> None:
    auth_service.disable_2fa(db, user, body.password, body.code, mail)


@router.post("/2fa/recovery-codes")
def regenerate_recovery_codes(
    body: CodeIn, user: CurrentUser, db: DbSession
) -> RecoveryCodesOut:
    codes = auth_service.regenerate_recovery_codes(db, user, body.code)
    return RecoveryCodesOut(recovery_codes=codes)
