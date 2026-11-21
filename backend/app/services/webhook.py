"""v1.9.0: avisos por webhook (Discord, Slack ou qualquer endereço https).

O formato sai do endereço: Discord recebe um cartão, Slack uma mensagem própria e qualquer outro
endereço um JSON com todos os dados (e o texto pronto em "text" e "content").

Segurança: a pessoa digita o endereço, então o servidor só envia para https em IP público
(nunca para o próprio servidor, a rede interna ou o endereço de dados da Oracle). A conferência
vale ao salvar e de novo a cada envio; redirecionamentos não são seguidos.
"""

import ipaddress
import json
import logging
import socket
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import InboxItem, User

if TYPE_CHECKING:
    from app.services.notify import Section

logger = logging.getLogger(__name__)

KINDS: tuple[str, ...] = ("due", "monthly", "weekly", "daily", "messages", "alerts")
MAX_FAILURES = 5
TIMEOUT = 5
DEADLINE = 12  # prazo total de um envio (DNS + conexão + resposta)
MAX_URL = 500
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")
DISCORD_COLOR = 0x3FB994

Service = Literal["discord", "slack", "generic"]


# ---------------------------------------------------------------- endereço


def _invalid(message: str) -> AppError:
    return AppError(400, "webhook_invalido", message)


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def _public(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global and not address.is_multicast


def validate_url(url: str) -> str:
    """Devolve o endereço limpo ou levanta AppError com a explicação em português."""
    url = (url or "").strip()
    if len(url) > MAX_URL:
        raise _invalid(f"O endereço do webhook pode ter no máximo {MAX_URL} caracteres.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise _invalid("Esse endereço de webhook não é válido.") from None
    if parts.scheme != "https" or not host:
        raise _invalid("O endereço do webhook precisa começar com https://.")
    if parts.username or parts.password:
        raise _invalid("O endereço do webhook não pode ter usuário e senha.")
    try:
        ips = _resolve(host)
    except OSError:
        raise _invalid("Não foi possível encontrar esse endereço. Confira se está certo.") from None
    if not ips or not all(_public(ip) for ip in ips):
        raise _invalid("Esse endereço não pode receber avisos: ele aponta para uma rede interna.")
    return url


def service_of(url: str) -> Service:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in ("discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com") and (
        parts.path.startswith("/api/webhooks/")
    ):
        return "discord"
    if host == "hooks.slack.com":
        return "slack"
    return "generic"


def url_hint(url: str) -> str:
    """Só um pedaço do endereço: quem tem o endereço inteiro consegue postar no canal."""
    host = urlsplit(url).hostname or ""
    return f"{host}/…{url[-4:]}"


# ---------------------------------------------------------------- preferências


def kinds_of(user: User) -> list[str]:
    try:
        saved = json.loads(user.webhook_kinds or "[]")
    except ValueError:
        return []
    return [kind for kind in KINDS if kind in saved]


def dump_kinds(kinds: list[str]) -> str:
    return json.dumps([kind for kind in KINDS if kind in kinds])


def paused(user: User) -> bool:
    return (user.webhook_failures or 0) >= MAX_FAILURES


def wants(user: User, kind: str) -> bool:
    return bool(user.webhook_url) and not paused(user) and kind in kinds_of(user)


# ---------------------------------------------------------------- formato


def _link(path: str) -> str:
    if path.startswith("http"):
        return path
    return get_settings().frontend_url.rstrip("/") + path


def _row(row: tuple[str, str, str]) -> str:
    return " · ".join(part for part in row if part)


def _plain(title: str, body: str, link: str, sections: "list[Section]") -> str:
    lines = [title, body]
    for section in sections:
        lines += ["", f"{section.title}:"] + [f"- {_row(row)}" for row in section.rows]
        if section.note:
            lines.append(section.note)
    lines += ["", link]
    return "\n".join(line for line in lines if line is not None)


def build_payload(
    service: Service,
    kind: str,
    title: str,
    body: str,
    link: str,
    sections: "list[Section] | None" = None,
) -> dict[str, Any]:
    sections = sections or []
    url = _link(link)
    if service == "discord":
        fields = []
        for section in sections[:25]:
            value = "\n".join(_row(row) for row in section.rows)
            if section.note:
                value = f"{value}\n{section.note}" if value else section.note
            fields.append({"name": section.title[:256], "value": (value or "—")[:1024]})
        embed: dict[str, Any] = {
            "title": title[:256],
            "description": body[:4096],
            "url": url,
            "color": DISCORD_COLOR,
            "footer": {"text": "Meu Orçamento"},
        }
        if fields:
            embed["fields"] = fields
        return {"username": "Meu Orçamento", "embeds": [embed]}
    if service == "slack":
        lines = [f"*{title}*", body]
        for section in sections:
            lines += ["", f"*{section.title}*"] + [f"• {_row(row)}" for row in section.rows]
            if section.note:
                lines.append(section.note)
        lines += ["", f"<{url}|Abrir no Meu Orçamento>"]
        return {"text": "\n".join(lines)}
    text = _plain(title, body, url, sections)
    return {
        "event": kind,
        "title": title,
        "body": body,
        "link": url,
        "sent_at": datetime.now(UTC).isoformat(),
        "sections": [
            {
                "title": section.title,
                "rows": [
                    {"description": desc, "date": day, "value": value}
                    for desc, day, value in section.rows
                ],
                "note": section.note,
            }
            for section in sections
        ],
        "text": text,
        "content": text[:2000],
    }


# ---------------------------------------------------------------- envio


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None  # um 3xx vira erro: o endereço confirmado é o único que recebe


def _post(url: str, payload: dict[str, Any]) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "MeuOrcamento-Webhook"},
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=TIMEOUT) as response:  # noqa: S310 (endereço conferido)
            return 200 <= response.status < 300
    except Exception as exc:  # fora do ar, tempo esgotado, 4xx/5xx, redirecionamento
        logger.warning("Webhook não respondeu: %s", type(exc).__name__)
        return False


def _attempt(url: str, payload: dict[str, Any]) -> bool:
    try:
        return _post(validate_url(url), payload)
    except AppError:
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook falhou: %s", type(exc).__name__)
        return False


def _with_deadline(url: str, payload: dict[str, Any]) -> bool:
    """Prazo total: o tempo limite do urllib vale por operação (um servidor que responde aos
    pouquinhos ou um DNS travado prenderiam o envio para sempre)."""
    result: list[bool] = []
    worker = threading.Thread(
        target=lambda: result.append(_attempt(url, payload)), daemon=True, name="webhook-post"
    )
    worker.start()
    worker.join(DEADLINE)
    return bool(result and result[0])


def _record(bind: Any, user_id: uuid.UUID, ok: bool) -> None:
    """Conta sucesso/falha numa sessão própria: nunca grava nem desfaz o trabalho de quem chamou."""
    try:
        with Session(bind) as session:
            user = session.get(User, user_id)
            if user is None:
                return
            if ok:
                user.webhook_failures = 0
            else:
                user.webhook_failures = (user.webhook_failures or 0) + 1
                if user.webhook_failures == MAX_FAILURES:
                    session.add(
                        InboxItem(
                            user_id=user.id,
                            kind="alert",
                            title="Webhook pausado",
                            body=(
                                "Os avisos pararam de chegar ao seu webhook depois de "
                                f"{MAX_FAILURES} tentativas sem resposta. Confira o endereço em "
                                "Configurações › Preferências."
                            ),
                        )
                    )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Contagem de falhas do webhook não salva para %s: %s", user_id, exc)


def _dispatch(job: Callable[[], object]) -> None:
    """Envio fora da requisição e do agendador: quem chama não espera a rede."""
    _POOL.submit(job)


def send(
    db: Session,
    user: User,
    kind: str,
    title: str,
    body: str,
    link: str = "/",
    sections: "list[Section] | None" = None,
    force: bool = False,
    wait: bool = False,
) -> bool:
    """Envia o aviso se o tipo estiver ligado. Nunca levanta erro (o aviso segue por e-mail).

    Por padrão o envio vai para uma fila em segundo plano e devolve True (aviso na fila).
    wait=True envia agora e devolve se o endereço respondeu (botão "Enviar teste").
    """
    if not user.webhook_url or not (force or wants(user, kind)):
        return False
    url = user.webhook_url
    payload = build_payload(service_of(url), kind, title, body, link, sections)
    bind = db.get_bind()
    user_id = user.id

    def job() -> bool:
        ok = _with_deadline(url, payload)
        _record(bind, user_id, ok)
        return ok

    if wait:
        return job()
    _dispatch(job)
    return True
