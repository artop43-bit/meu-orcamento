"""Regras de negócio de autenticação: cadastro, login, sessões, 2FA e recuperação de senha."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core import security, totp
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.request_context import request_info
from app.db.types import utcnow
from app.models import AuthToken, RecoveryCode, SecurityEvent, User, UserSession
from app.services import budget

# (destinatário, assunto, corpo). As rotas enviam em segundo plano, para o tempo
# de resposta não revelar se um e-mail está cadastrado.
Mailer = Callable[[str, str, str], None]

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)
VERIFY_EMAIL_TTL = timedelta(hours=24)
RESET_PASSWORD_TTL = timedelta(hours=1)
LOGIN_CHALLENGE_TTL = timedelta(minutes=5)
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

PURPOSE_VERIFY_EMAIL = "verify_email"
PURPOSE_RESET_PASSWORD = "reset_password"
PURPOSE_LOGIN_2FA = "login_2fa"


def _invalid_credentials() -> AppError:
    return AppError(401, "invalid_credentials", "E-mail ou senha incorretos.")


def _invalid_token() -> AppError:
    return AppError(400, "invalid_token", "Este link é inválido ou expirou.")


def _invalid_code() -> AppError:
    return AppError(400, "invalid_code", "Código inválido.")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _record(db: Session, user: User, event: str) -> None:
    """Registra um evento de segurança com o IP e o navegador da requisição atual."""
    info = request_info()
    db.add(SecurityEvent(user_id=user.id, event=event, ip=info.ip, user_agent=info.user_agent))


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


# ---------------------------------------------------------------- tokens de uso único


def _issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    now = utcnow()
    # Só o link mais recente vale.
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = security.new_token()
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=security.hash_token(raw),
            expires_at=now + ttl,
        )
    )
    return raw


def _find_token(db: Session, raw: str, purpose: str) -> AuthToken:
    token = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == security.hash_token(raw),
            AuthToken.purpose == purpose,
        )
    )
    if token is None or token.used_at is not None or token.expires_at <= utcnow():
        raise _invalid_token()
    return token


def _link(path: str, token: str) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}{path}?token={token}"


# ---------------------------------------------------------------- cadastro e verificação


def register(db: Session, email: str, password: str, mail: Mailer) -> None:
    email = normalize_email(email)
    existing = _get_user_by_email(db, email)

    if existing is not None:
        if existing.email_verified:
            mail(
                email,
                "Você já tem uma conta no Meu Orçamento",
                "Alguém (talvez você) tentou criar uma conta com este e-mail, "
                "mas ele já está cadastrado.\n\n"
                f"Para entrar: {get_settings().frontend_url}/entrar\n"
                f"Esqueceu a senha? {get_settings().frontend_url}/esqueci-senha\n\n"
                "Se não foi você, pode ignorar esta mensagem.",
            )
        else:
            _send_verification(db, existing, mail)
        db.commit()
        return

    settings = get_settings()
    approved = not settings.signup_approval or email in settings.admin_email_list()
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        terms_accepted_at=utcnow(),
        terms_version=settings.terms_version,
        access_status="approved" if approved else "pending",
        approved_at=utcnow() if approved else None,
    )
    db.add(user)
    db.flush()
    budget.create_default_categories(db, user)
    _send_verification(db, user, mail)
    db.commit()


def _send_verification(db: Session, user: User, mail: Mailer) -> None:
    token = _issue_token(db, user, PURPOSE_VERIFY_EMAIL, VERIFY_EMAIL_TTL)
    mail(
        user.email,
        "Confirme seu e-mail",
        "Bem-vindo ao Meu Orçamento!\n\n"
        f"Confirme seu e-mail neste link (válido por 24 horas):\n{_link('/verificar-email', token)}"
        "\n\nSe você não criou esta conta, ignore esta mensagem.",
    )


def resend_verification(db: Session, email: str, mail: Mailer) -> None:
    user = _get_user_by_email(db, email)
    if user is not None and not user.email_verified:
        _send_verification(db, user, mail)
        db.commit()


def verify_email(db: Session, raw_token: str) -> None:
    token = _find_token(db, raw_token, PURPOSE_VERIFY_EMAIL)
    user = db.get_one(User, token.user_id)
    now = utcnow()
    token.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
        _record(db, user, "email_verified")
    db.commit()


# ---------------------------------------------------------------- login e sessões


@dataclass
class LoginResult:
    user: User
    session_token: str | None = None
    challenge: str | None = None


def _ensure_not_locked(user: User) -> None:
    if user.locked_until is not None and user.locked_until > utcnow():
        raise AppError(
            429,
            "account_locked",
            "Muitas tentativas incorretas. Tente novamente em alguns minutos.",
        )


def _register_failure(db: Session, user: User, event: str) -> None:
    now = utcnow()
    _record(db, user, event)
    if user.locked_until is not None and user.locked_until <= now:
        user.failed_login_attempts = 0
        user.locked_until = None
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = now + LOCK_DURATION
    db.commit()


def _reset_failures(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None


def login(db: Session, email: str, password: str, user_agent: str | None) -> LoginResult:
    user = _get_user_by_email(db, email)
    if user is None:
        security.burn_password_check(password)
        raise _invalid_credentials()

    _ensure_not_locked(user)
    if not security.verify_password(user.password_hash, password):
        _register_failure(db, user, "login_failed")
        raise _invalid_credentials()

    if not user.email_verified:
        raise AppError(
            403,
            "email_not_verified",
            "Confirme seu e-mail antes de entrar. Verifique sua caixa de entrada.",
        )

    if user.access_status == "pending":
        raise AppError(
            403,
            "access_pending",
            "Seu cadastro está em análise. Você receberá um e-mail quando o acesso for liberado.",
        )
    if user.access_status == "blocked":
        raise AppError(403, "access_blocked", "Acesso suspenso. Fale com a administração.")

    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    if user.totp_enabled:
        challenge = _issue_token(db, user, PURPOSE_LOGIN_2FA, LOGIN_CHALLENGE_TTL)
        db.commit()
        return LoginResult(user=user, challenge=challenge)

    _reset_failures(user)
    session_token = _start_session(db, user, user_agent)
    _record(db, user, "login")
    db.commit()
    return LoginResult(user=user, session_token=session_token)


def complete_login_2fa(
    db: Session, challenge: str, code: str, user_agent: str | None
) -> LoginResult:
    token = _find_token(db, challenge, PURPOSE_LOGIN_2FA)
    user = db.get_one(User, token.user_id)
    _ensure_not_locked(user)

    if not _verify_second_factor(db, user, code):
        _register_failure(db, user, "login_2fa_failed")
        raise _invalid_code()

    token.used_at = utcnow()
    _reset_failures(user)
    session_token = _start_session(db, user, user_agent)
    _record(db, user, "login")
    db.commit()
    return LoginResult(user=user, session_token=session_token)


def _start_session(db: Session, user: User, user_agent: str | None) -> str:
    raw = security.new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            user_agent=(user_agent or "")[:255] or None,
            ip=request_info().ip,
            expires_at=utcnow() + timedelta(days=get_settings().session_ttl_days),
        )
    )
    return raw


def user_from_session(db: Session, raw_token: str | None) -> User | None:
    if not raw_token:
        return None
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == security.hash_token(raw_token))
    )
    now = utcnow()
    if session is None or session.expires_at <= now:
        return None
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return db.get(User, session.user_id)


def logout(db: Session, raw_token: str | None) -> None:
    if raw_token:
        db.execute(
            delete(UserSession).where(UserSession.token_hash == security.hash_token(raw_token))
        )
        db.commit()


def _revoke_sessions(db: Session, user: User, keep_token: str | None = None) -> None:
    stmt = delete(UserSession).where(UserSession.user_id == user.id)
    if keep_token:
        stmt = stmt.where(UserSession.token_hash != security.hash_token(keep_token))
    db.execute(stmt)


def list_sessions(db: Session, user: User, current_token: str | None) -> list[dict[str, Any]]:
    current_hash = security.hash_token(current_token) if current_token else None
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.expires_at > utcnow())
        .order_by(UserSession.last_seen_at.desc())
    )
    return [
        {
            "id": s.id,
            "user_agent": s.user_agent,
            "ip": s.ip,
            "created_at": s.created_at,
            "last_seen_at": s.last_seen_at,
            "current": s.token_hash == current_hash,
        }
        for s in sessions
    ]


def revoke_session(
    db: Session, user: User, session_id: uuid.UUID, current_token: str | None
) -> None:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user.id:
        raise AppError(404, "not_found", "Sessão não encontrada.")
    if current_token and session.token_hash == security.hash_token(current_token):
        raise AppError(400, "current_session", "Para encerrar esta sessão, use o botão Sair.")
    db.delete(session)
    _record(db, user, "session_revoked")
    db.commit()


def revoke_other_sessions(db: Session, user: User, current_token: str | None) -> None:
    _revoke_sessions(db, user, keep_token=current_token)
    _record(db, user, "sessions_revoked")
    db.commit()


def list_events(db: Session, user: User, limit: int = 30) -> list[SecurityEvent]:
    return list(
        db.scalars(
            select(SecurityEvent)
            .where(SecurityEvent.user_id == user.id)
            .order_by(SecurityEvent.created_at.desc())
            .limit(limit)
        )
    )


# ---------------------------------------------------------------- exclusão de conta


def delete_account(db: Session, user: User, password: str, code: str | None, mail: Mailer) -> None:
    """Exclui a conta e todos os dados dela (LGPD, art. 18, VI). Não há como desfazer."""
    if not security.verify_password(user.password_hash, password):
        raise AppError(400, "wrong_password", "Senha incorreta.")
    if user.totp_enabled and (not code or not _verify_second_factor(db, user, code)):
        raise AppError(400, "invalid_code", "Informe um código válido do aplicativo autenticador.")

    email = user.email
    # As demais tabelas apagam junto (ON DELETE CASCADE).
    db.delete(user)
    db.commit()
    mail(
        email,
        "Sua conta foi excluída",
        "Sua conta no Meu Orçamento e todos os dados dela foram excluídos, como você pediu.\n\n"
        "Se não foi você, entre em contato pelo e-mail indicado na Política de privacidade: "
        f"{get_settings().frontend_url}/privacidade",
    )


# ---------------------------------------------------------------- senha


def forgot_password(db: Session, email: str, mail: Mailer) -> None:
    user = _get_user_by_email(db, email)
    if user is None:
        return
    token = _issue_token(db, user, PURPOSE_RESET_PASSWORD, RESET_PASSWORD_TTL)
    db.commit()
    mail(
        user.email,
        "Redefinição de senha",
        "Recebemos um pedido para redefinir sua senha.\n\n"
        f"Crie uma nova senha neste link (válido por 1 hora):\n"
        f"{_link('/redefinir-senha', token)}\n\n"
        "Se você não pediu isso, ignore esta mensagem: sua senha continua a mesma.",
    )


def reset_password(db: Session, raw_token: str, new_password: str, mail: Mailer) -> None:
    token = _find_token(db, raw_token, PURPOSE_RESET_PASSWORD)
    user = db.get_one(User, token.user_id)
    now = utcnow()

    token.used_at = now
    user.password_hash = security.hash_password(new_password)
    # Quem recebeu o link provou ter acesso ao e-mail.
    if user.email_verified_at is None:
        user.email_verified_at = now
    _reset_failures(user)
    _revoke_sessions(db, user)
    _record(db, user, "password_reset")
    db.commit()
    _notify_password_changed(user, mail)


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    current_session: str | None,
    mail: Mailer,
) -> None:
    if not security.verify_password(user.password_hash, current_password):
        raise AppError(400, "wrong_password", "Senha atual incorreta.")
    user.password_hash = security.hash_password(new_password)
    _revoke_sessions(db, user, keep_token=current_session)
    _record(db, user, "password_changed")
    db.commit()
    _notify_password_changed(user, mail)


def _notify_password_changed(user: User, mail: Mailer) -> None:
    mail(
        user.email,
        "Sua senha foi alterada",
        "A senha da sua conta no Meu Orçamento acabou de ser alterada, "
        "e as outras sessões abertas foram encerradas.\n\n"
        "Se não foi você, redefina sua senha imediatamente: "
        f"{get_settings().frontend_url}/esqueci-senha",
    )


# ---------------------------------------------------------------- 2FA


def setup_2fa(db: Session, user: User) -> tuple[str, str]:
    if user.totp_enabled:
        raise AppError(409, "2fa_already_enabled", "A verificação em duas etapas já está ativa.")
    secret = totp.new_secret()
    user.totp_secret_encrypted = security.encrypt(secret)
    db.commit()
    return secret, totp.provisioning_uri(secret, user.email)


def enable_2fa(db: Session, user: User, code: str, mail: Mailer) -> list[str]:
    if user.totp_enabled:
        raise AppError(409, "2fa_already_enabled", "A verificação em duas etapas já está ativa.")
    if user.totp_secret_encrypted is None:
        raise AppError(
            400, "2fa_not_set_up", "Comece a configuração da verificação em duas etapas."
        )

    step = totp.matching_step(security.decrypt(user.totp_secret_encrypted), code)
    if step is None:
        raise _invalid_code()

    user.totp_enabled = True
    user.totp_last_used_step = step
    codes = _replace_recovery_codes(db, user)
    _record(db, user, "2fa_enabled")
    db.commit()
    mail(
        user.email,
        "Verificação em duas etapas ativada",
        "A verificação em duas etapas foi ativada na sua conta. "
        "Guarde seus códigos de recuperação em local seguro.\n\n"
        "Se não foi você, redefina sua senha imediatamente.",
    )
    return codes


def disable_2fa(db: Session, user: User, password: str, code: str, mail: Mailer) -> None:
    if not user.totp_enabled:
        raise AppError(400, "2fa_not_enabled", "A verificação em duas etapas não está ativa.")
    if not security.verify_password(user.password_hash, password):
        raise AppError(400, "wrong_password", "Senha incorreta.")
    if not _verify_second_factor(db, user, code):
        raise _invalid_code()

    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.totp_last_used_step = None
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    _record(db, user, "2fa_disabled")
    db.commit()
    mail(
        user.email,
        "Verificação em duas etapas desativada",
        "A verificação em duas etapas foi desativada na sua conta.\n\n"
        "Se não foi você, redefina sua senha imediatamente.",
    )


def regenerate_recovery_codes(db: Session, user: User, code: str) -> list[str]:
    if not user.totp_enabled:
        raise AppError(400, "2fa_not_enabled", "A verificação em duas etapas não está ativa.")
    if not _verify_totp(user, code):
        raise _invalid_code()
    codes = _replace_recovery_codes(db, user)
    _record(db, user, "recovery_codes_regenerated")
    db.commit()
    return codes


def remaining_recovery_codes(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(RecoveryCode.id).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        ).all()
    )


def _replace_recovery_codes(db: Session, user: User) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = totp.new_recovery_codes()
    for code in codes:
        db.add(
            RecoveryCode(
                user_id=user.id,
                code_hash=security.hash_token(totp.normalize_recovery_code(code)),
            )
        )
    return codes


def _verify_totp(user: User, code: str) -> bool:
    if user.totp_secret_encrypted is None:
        return False
    step = totp.matching_step(security.decrypt(user.totp_secret_encrypted), code)
    if step is None or (user.totp_last_used_step is not None and step <= user.totp_last_used_step):
        return False
    user.totp_last_used_step = step
    return True


def _verify_second_factor(db: Session, user: User, code: str) -> bool:
    """Aceita um código do aplicativo autenticador ou um código de recuperação (uso único)."""
    if _verify_totp(user, code):
        return True
    recovery = db.scalar(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == security.hash_token(totp.normalize_recovery_code(code)),
            RecoveryCode.used_at.is_(None),
        )
    )
    if recovery is None:
        return False
    recovery.used_at = utcnow()
    return True


def is_admin(user: User) -> bool:
    return bool(user.is_admin) or user.email.lower() in get_settings().admin_email_list()
