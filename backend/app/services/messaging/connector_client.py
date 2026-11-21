"""Cliente HTTP da API para o conector interno do WhatsApp (rede do Docker).

Chamadas curtas (3 s) e de melhor esforço: uma falha de rede nunca derruba a ação da pessoa,
exceto onde o contrato pede para registrar o erro (início da conexão).
"""

import http.client
import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Any

from app.core.config import get_settings

TIMEOUT_SECONDS = 3
logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Não deu para falar com o conector (não configurado, fora do ar ou resposta de erro)."""


def is_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.messaging_connector_url.strip() and settings.messaging_connector_token.strip()
    )


def _post(path: str, payload: dict[str, Any] | None = None) -> None:
    settings = get_settings()
    base = settings.messaging_connector_url.strip().rstrip("/")
    token = settings.messaging_connector_token.strip()
    if not base or not token:
        raise ConnectorError("conector não configurado")
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload or {}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Connector-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    # HTTPError (4xx/5xx), tempo esgotado e conexão recusada entram aqui.
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise ConnectorError(str(exc) or type(exc).__name__) from exc
    if status >= 300:
        raise ConnectorError(f"resposta {status}")


def _best_effort(path: str, payload: dict[str, Any] | None = None) -> bool:
    if not is_configured():
        return False
    try:
        _post(path, payload)
    except ConnectorError as exc:
        logger.warning("Conector do WhatsApp não respondeu em %s: %s", path, exc)
        return False
    return True


def start_session(session_id: uuid.UUID) -> None:
    """Inicia (ou reinicia, com QR novo) a sessão. Levanta ConnectorError se não der."""
    _post(f"/sessions/{session_id}/start")


def stop_session(session_id: uuid.UUID, *, logout: bool) -> bool:
    """Fecha a sessão; com logout=True também desconecta o número e apaga as credenciais."""
    return _best_effort(f"/sessions/{session_id}/stop", {"logout": logout})


def flush_session(session_id: uuid.UUID) -> bool:
    """Pede para o conector buscar a fila de envio dessa sessão agora."""
    return _best_effort(f"/sessions/{session_id}/flush")


def mark_read(session_id: uuid.UUID, remote_jid: str, external_ids: list[str]) -> bool:
    """Envia ao WhatsApp a confirmação de leitura das mensagens recebidas."""
    return _best_effort(
        f"/sessions/{session_id}/read",
        {"remote_jid": remote_jid, "external_ids": external_ids},
    )
