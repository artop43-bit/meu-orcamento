"""Conector seguro para APIs externas REST/JSON com proteção anti-SSRF e credenciais cifradas."""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import socket
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from app.core import security
from app.core.errors import AppError
from app.services.crm.pdf_reader import MAX_ROWS, build_schema_and_rows, suggest_crm_mapping

MAX_URL_LENGTH = 500
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _resolve_ips(host: str, port: int) -> list[str]:
    result: list[str] = []
    errors: list[OSError] = []
    done = threading.Event()

    def resolve() -> None:
        try:
            result.extend(
                info[4][0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            )
        except OSError as exc:
            errors.append(exc)
        finally:
            done.set()

    threading.Thread(target=resolve, daemon=True).start()
    if not done.wait(REQUEST_TIMEOUT_SECONDS):
        raise TimeoutError("Tempo de resolução do domínio excedido")
    if errors:
        raise errors[0]
    return result


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if not addr.is_global or addr.is_multicast:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if any(
            addr in ipaddress.ip_network(net) for net in ("64:ff9b::/96", "64:ff9b:1::/48", "::/96")
        ):
            return False
        embedded = [addr.ipv4_mapped, addr.sixtofour]
        if addr.teredo:
            embedded.extend(addr.teredo)
        if any(ip is not None and not _is_public_ip(str(ip)) for ip in embedded):
            return False
    return True


def validate_api_url(url: str) -> str:
    """Aceita apenas URLs https:// cujo DNS resolva exclusivamente para IPs públicos globais."""
    return _validated_api_target(url)[0]


def _validated_api_target(url: str) -> tuple[str, list[str]]:
    clean = (url or "").strip()
    if not clean or len(clean) > MAX_URL_LENGTH:
        raise AppError(400, "invalid_api_url", "Informe uma URL HTTPS válida.")
    try:
        parts = urlsplit(clean)
        port = parts.port or 443
    except ValueError as exc:
        raise AppError(400, "invalid_api_url", "Informe uma URL HTTPS válida.") from exc
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise AppError(400, "invalid_api_url", "Apenas endereços https:// são permitidos.")
    if parts.username or parts.password:
        raise AppError(
            400,
            "invalid_api_url",
            "Não coloque usuário ou senha na URL; use a seção de autenticação.",
        )
    host = parts.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise AppError(400, "ssrf_blocked", "Endereços locais ou da rede interna são bloqueados.")
    try:
        ips = _resolve_ips(host, port)
    except OSError as exc:
        raise AppError(400, "dns_failed", "Não foi possível resolver o domínio informado.") from exc
    if not ips or not all(_is_public_ip(ip) for ip in ips):
        raise AppError(
            400, "ssrf_blocked", "Endereços locais ou privados são bloqueados por segurança."
        )
    return clean, ips


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TCP usa IP público conferido; TLS verifica o domínio original."""

    def __init__(self, host: str, *, pinned_ip: str, deadline: float, sockets: list, **kwargs):
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip
        self._deadline = deadline
        self._sockets = sockets

    def connect(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Prazo da API excedido")
        raw = socket.create_connection((self._pinned_ip, self.port), timeout=remaining)
        self._sockets.append(raw)
        self.sock = raw
        self.sock = self._context.wrap_socket(
            raw, server_hostname=self.host, do_handshake_on_connect=False
        )
        self._sockets.append(self.sock)
        self.sock.do_handshake()


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, ip: str, deadline: float, sockets: list):
        super().__init__()
        self._ip = ip
        self._deadline = deadline
        self._sockets = sockets

    def https_open(self, req):
        def connection(host, **kwargs):
            return _PinnedHTTPSConnection(
                host, pinned_ip=self._ip, deadline=self._deadline, sockets=self._sockets, **kwargs
            )

        return self.do_open(connection, req, context=self._context)


def encrypt_credentials(
    auth_type: str, auth_value: str | None, header_name: str | None = None
) -> str | None:
    if auth_type == "none" or not (auth_value or "").strip():
        return None
    payload = json.dumps(
        {
            "auth_type": auth_type,
            "auth_value": auth_value.strip(),
            "header_name": (header_name or "X-API-Key").strip(),
        },
        separators=(",", ":"),
    )
    return security.encrypt(payload)


def _auth_headers(credentials_encrypted: str | None) -> dict[str, str]:
    if not credentials_encrypted:
        return {}
    data = json.loads(security.decrypt(credentials_encrypted))
    kind = data.get("auth_type")
    val = str(data.get("auth_value") or "")
    if not val:
        return {}
    if kind == "bearer":
        return {"Authorization": f"Bearer {val}"}
    if kind == "api_key":
        header = str(data.get("header_name") or "X-API-Key")
        return {header: val}
    if kind == "basic":
        encoded = base64.b64encode(val.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    return {}


def _flatten_record(item: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, val in item.items():
        full_key = f"{prefix}_{key}" if prefix else str(key)
        if isinstance(val, dict):
            flat.update(_flatten_record(val, full_key))
        elif isinstance(val, list):
            flat[full_key] = ", ".join(str(x) for x in val[:20])
        else:
            flat[full_key] = val
    return flat


def extract_json_records(payload: Any, data_path: str | None = None) -> list[dict[str, Any]]:
    """Extrai registros de um JSON usando data_path (ex.: 'data.items') ou auto-descoberta."""
    current = payload
    if data_path and data_path.strip():
        for part in data_path.strip().split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise AppError(
                    400,
                    "invalid_data_path",
                    f"Caminho '{data_path}' não encontrado na resposta da API.",
                )

    if isinstance(current, list):
        records = [item if isinstance(item, dict) else {"valor": item} for item in current]
    elif isinstance(current, dict):
        list_found = next(
            (v for v in current.values() if isinstance(v, list) and v and isinstance(v[0], dict)),
            None,
        )
        if list_found is not None:
            records = list_found
        else:
            records = [current]
    else:
        raise AppError(
            400, "invalid_json_shape", "A resposta da API não contém objetos JSON tabuláveis."
        )

    return [_flatten_record(rec) for rec in records[:MAX_ROWS]]


def records_to_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"columns": [], "rows": [], "total_rows": 0, "suggestions": suggest_crm_mapping([])}
    headers: list[str] = []
    for rec in records:
        for key in rec:
            if key not in headers:
                headers.append(key)
    raw_rows = [[rec.get(h) for h in headers] for rec in records]
    schema, rows = build_schema_and_rows(headers, raw_rows)
    return {
        "columns": schema,
        "rows": rows,
        "total_rows": len(rows),
        "suggestions": suggest_crm_mapping(schema),
    }


def fetch_external_api(
    *,
    url: str,
    method: str = "GET",
    data_path: str | None = None,
    credentials_encrypted: str | None = None,
    extra_headers: dict[str, str] | None = None,
    body_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Busca dados de uma API HTTPS externa com revalidação anti-SSRF a cada chamada."""
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    validated_url, addresses = _validated_api_target(url)
    if time.monotonic() >= deadline:
        raise AppError(
            502, "api_unreachable", "A consulta da API excedeu o prazo total de 10 segundos."
        )
    verb = method.upper()
    if verb not in {"GET", "POST"}:
        raise AppError(400, "invalid_method", "Apenas métodos GET e POST são permitidos.")

    headers = {
        "Accept": "application/json",
        "User-Agent": "HubDashboardCRM/0.1",
        **(extra_headers or {}),
        **_auth_headers(credentials_encrypted),
    }
    data_bytes = None
    if verb == "POST" and body_json is not None:
        data_bytes = json.dumps(body_json).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(validated_url, data=data_bytes, headers=headers, method=verb)
    sockets: list = []

    def expire() -> None:
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except OSError:
                pass

    timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
    timer.daemon = True
    opener = build_opener(
        ProxyHandler({}), _NoRedirect(), _PinnedHTTPSHandler(addresses[0], deadline, sockets)
    )
    timer.start()
    try:
        with opener.open(req, timeout=max(0.001, deadline - time.monotonic())) as resp:
            if 300 <= resp.status < 400:
                raise AppError(400, "redirect_blocked", "Redirecionamentos de API são bloqueados.")
            chunks: list[bytes] = []
            length = 0
            while length <= MAX_RESPONSE_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Prazo total excedido")
                for sock in sockets:
                    try:
                        sock.settimeout(remaining)
                    except OSError:
                        pass
                reader = getattr(resp, "read1", resp.read)
                chunk = reader(min(65536, MAX_RESPONSE_BYTES + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
            if time.monotonic() >= deadline:
                raise TimeoutError("Prazo total excedido")
            raw = b"".join(chunks)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AppError(
                    400, "payload_too_large", "A resposta da API excede o limite de 2 MB."
                )
    except AppError:
        raise
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise AppError(
                400, "redirect_blocked", "Redirecionamentos de API são bloqueados."
            ) from exc
        raise AppError(
            502,
            "api_http_error",
            f"A API externa respondeu com erro HTTP {exc.code}.",
        ) from exc
    except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise AppError(
            502,
            "api_unreachable",
            "Não foi possível conectar à API externa dentro do tempo limite.",
        ) from exc

    finally:
        timer.cancel()

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AppError(400, "invalid_json", "A resposta da API não é um JSON válido.") from exc

    records = extract_json_records(parsed, data_path=data_path)
    return records_to_dataset(records)
