import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.config import get_settings

Password = Annotated[str, Field(min_length=10, max_length=128)]
Code = Annotated[str, Field(min_length=6, max_length=32)]
Token = Annotated[str, Field(min_length=10, max_length=200)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    email_verified: bool
    totp_enabled: bool
    twofa_prompt_dismissed: bool
    created_at: datetime
    # Vê as sugestões enviadas pelo app (ADMIN_EMAILS no servidor).
    is_admin: bool = False
    # Configuração inicial guiada já concluída (ou pulada).
    onboarded_at: datetime | None = None
    # v0.9: aparência salva na conta (None = ainda não escolheu; vale a do aparelho).
    theme: str | None = None
    accent: str | None = None

    @model_validator(mode="after")
    def _admin(self) -> "UserOut":
        self.is_admin = self.is_admin or self.email.lower() in get_settings().admin_email_list()
        return self


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    # Precisa ser true: o aceite fica registrado com data e versão dos termos.
    accept_terms: Literal[True]


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: Token


class LoginIn(BaseModel):
    email: EmailStr
    # Sem mínimo no login: senhas antigas não devem ser barradas pela regra atual.
    password: Annotated[str, Field(min_length=1, max_length=128)]


class LoginOut(BaseModel):
    status: Literal["ok", "2fa_required"]
    user: UserOut | None = None
    challenge: str | None = None


class Login2faIn(BaseModel):
    challenge: Token
    code: Code


class ResetPasswordIn(BaseModel):
    token: Token
    password: Password


class ChangePasswordIn(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Password


class TwoFactorSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class CodeIn(BaseModel):
    code: Code


class Disable2faIn(BaseModel):
    password: Annotated[str, Field(min_length=1, max_length=128)]
    code: Code


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class TwoFactorStatusOut(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class MessageOut(BaseModel):
    message: str


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event: str
    ip: str | None
    user_agent: str | None
    created_at: datetime


class DeleteAccountIn(BaseModel):
    password: Annotated[str, Field(min_length=1, max_length=128)]
    code: Annotated[str, Field(max_length=32)] | None = None


class TwoFactorPromptIn(BaseModel):
    dismissed: bool
