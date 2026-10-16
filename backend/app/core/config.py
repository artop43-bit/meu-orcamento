from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-only-insecure-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://orcamento:orcamento@localhost:5432/orcamento"
    # Também deriva a chave que criptografa os segredos de 2FA no banco:
    # trocar a SECRET_KEY invalida o 2FA de todos os usuários.
    secret_key: str = DEFAULT_SECRET_KEY
    # Lista separada por vírgulas, ex.: "http://localhost:5173,https://meuorcamento.com.br"
    cors_origins: str = "http://localhost:5173"
    # Endereço público do frontend, usado nos links enviados por e-mail.
    frontend_url: str = "http://localhost:5173"

    # Fuso usado para saber qual é o "mês atual".
    timezone: str = "America/Sao_Paulo"

    session_ttl_days: int = 30
    # None = seguro automaticamente em produção (HTTPS).
    cookie_secure: bool | None = None

    # "console" imprime os e-mails no log; "memory" guarda para testes; "smtp" envia de verdade.
    email_backend: Literal["console", "memory", "smtp"] = "console"
    email_from: str = "Meu Orçamento <nao-responda@localhost>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
