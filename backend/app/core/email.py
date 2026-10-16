import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str


# Usado pelo backend "memory" (testes).
outbox: list[OutgoingEmail] = []


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = OutgoingEmail(to=to, subject=subject, body=body)

    if settings.email_backend == "memory":
        outbox.append(message)
    elif settings.email_backend == "console":
        print(f"\n--- E-MAIL para {to}: {subject}\n{body}\n---\n", flush=True)
    else:
        _send_smtp(message)


def _send_smtp(message: OutgoingEmail) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg.set_content(message.body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
