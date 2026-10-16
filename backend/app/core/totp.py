import hmac
import secrets
import time

import pyotp

ISSUER = "Meu Orçamento"
STEP_SECONDS = 30
RECOVERY_CODE_COUNT = 10


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def matching_step(secret: str, code: str, now: float | None = None) -> int | None:
    """Retorna o passo de tempo do código (tolerância de ±30 s) ou None se inválido."""
    code = code.replace(" ", "").strip()
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None


def new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(5)
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().lower()
