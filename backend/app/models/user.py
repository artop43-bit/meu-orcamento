import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, SmallInteger, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # Segredo TOTP criptografado (Fernet). Existe antes de o 2FA ser ativado,
    # entre o "configurar" e a confirmação com o primeiro código.
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    # Último passo de tempo aceito: impede reutilizar o mesmo código.
    totp_last_used_step: Mapped[int | None] = mapped_column(BigInteger)

    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # Aceite dos Termos de uso e da Política de privacidade (LGPD): quando e qual versão.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    terms_version: Mapped[str | None] = mapped_column(String(20))

    # Beta fechado: "pending" (aguardando liberação), "approved" ou "blocked".
    access_status: Mapped[str] = mapped_column(
        String(10), default="approved", server_default="approved"
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Administração (painel). ADMIN_EMAILS no servidor também dá acesso.
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="0")

    # Perfil (tudo opcional). As preferências do resumo ficam em JSON: quais dados aparecem
    # no perfil e se a retrospectiva mostra valores em reais.
    display_name: Mapped[str | None] = mapped_column(String(60))
    bio: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(80))
    profession: Mapped[str | None] = mapped_column(String(80))
    profile_prefs: Mapped[str | None] = mapped_column(Text)

    # Avisos por e-mail (Ajustes › Preferências). O aviso de novo acesso é sempre enviado.
    notify_due: Mapped[bool] = mapped_column(default=True, server_default="1")
    notify_due_days: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    notify_hide_values: Mapped[bool] = mapped_column(default=False, server_default="0")
    notify_monthly: Mapped[bool] = mapped_column(default=True, server_default="1")
    # Configuração inicial guiada concluída (ou pulada).
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # O usuário pediu para não ver mais o convite para ativar a verificação em duas etapas.
    twofa_prompt_dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def twofa_prompt_dismissed(self) -> bool:
        return self.twofa_prompt_dismissed_at is not None


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AuthToken(Base):
    """Tokens de uso único: verificar e-mail, redefinir senha, segunda etapa do login."""

    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class SecurityEvent(Base):
    """Registro de atividade da conta (logins, troca de senha, 2FA…), visível ao usuário."""

    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(40))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class EmailLog(Base):
    """Cópia dos e-mails enviados (painel admin): confirmação, senha etc. Guardada 30 dias."""

    __tablename__ = "email_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    to: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class KnownDevice(Base):
    """Aparelho/navegador que já entrou na conta (para avisar acesso de um aparelho novo)."""

    __tablename__ = "known_devices"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Resumo do aparelho (navegador + sistema), sem dados que identifiquem a pessoa.
    fingerprint: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(80))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotificationLog(Base):
    """Avisos por e-mail já enviados: o mesmo aviso nunca sai duas vezes."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # "due" | "monthly"
    ref: Mapped[str] = mapped_column(String(40))  # ex.: "2026-10-20", "2026-09"
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
