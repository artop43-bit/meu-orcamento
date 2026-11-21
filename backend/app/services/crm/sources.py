"""Gestão unificada de Fontes de Dados (Nativas do Hub, PDF, CSV e APIs externas)."""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import CrmWidget, DataSnapshot, DataSource, User
from app.services import admin as admin_service
from app.services.crm import api_connector, hub_bridge
from app.services.crm.parsing import coerce_cell, slugify_column
from app.services.crm.pdf_reader import MAX_ROWS

NATIVE_KINDS = (
    "native_crm",
    "native_crm_contacts",
    "native_messaging",
    "native_budget",
    "native_catalog",
)

NATIVE_SOURCE_RESOURCE = {
    "native_messaging": "mensageria",
    "native_budget": "meu-orcamento",
    "native_catalog": "catalogo",
}


def _rows_byte_size(rows: list[dict[str, Any]]) -> int:
    return len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"))


def _check_snapshot_quota(db: Session, user_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    user = db.get(User, user_id)
    if user is not None:
        admin_service.assert_storage_quota(db, user, _rows_byte_size(rows))


def _checksum(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


_BOOTSTRAP_LOCK = threading.Lock()


def ensure_native_sources(db: Session, user_id: uuid.UUID) -> list[DataSource]:
    """Garante as 4 fontes nativas vivas do Hub (CRM, Contatos, Mensageria e Meu Orçamento)."""
    with _BOOTSTRAP_LOCK:
        existing = list(
            db.scalars(
                select(DataSource).where(
                    DataSource.user_id == user_id,
                    DataSource.kind.in_(NATIVE_KINDS),
                )
            ).all()
        )
        existing_kinds = {s.kind for s in existing}
        created = False
        specs = (
            (
                "native_crm",
                "CRM · Negócios",
                "Negócios e etapas do funil do CRM em tempo real.",
                hub_bridge.native_crm_deals_dataset,
            ),
            (
                "native_crm_contacts",
                "CRM · Contatos",
                "Base de contatos do CRM e vínculos com Mensageria e Orçamento.",
                hub_bridge.native_crm_contacts_dataset,
            ),
            (
                "native_messaging",
                "Mensageria · Mensagens",
                "Volume de atendimentos e mensagens do WhatsApp em tempo real.",
                hub_bridge.native_messaging_dataset,
            ),
            (
                "native_budget",
                "Meu Orçamento · Lançamentos",
                "Receitas e despesas do Meu Orçamento em tempo real.",
                hub_bridge.native_budget_dataset,
            ),
            (
                "native_catalog",
                "Catálogo · Produtos & Estoque",
                "Preços, custos, margens e saldo de estoque em tempo real.",
                hub_bridge.native_catalog_dataset,
            ),
        )
        for kind, name, desc, loader in specs:
            if kind not in existing_kinds:
                schema, rows = loader(db, user_id)
                db.add(
                    DataSource(
                        user_id=user_id,
                        name=name,
                        kind=kind,
                        description=desc,
                        schema_json=schema,
                        row_count=len(rows),
                        last_synced_at=utcnow(),
                    )
                )
                created = True
        if created:
            db.commit()
    return list(
        db.scalars(
            select(DataSource)
            .where(DataSource.user_id == user_id)
            .order_by(DataSource.created_at.asc())
        ).all()
    )


def get_source(db: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> DataSource:
    source = db.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.user_id == user_id)
    )
    if source is None:
        raise AppError(404, "source_not_found", "Fonte de dados não encontrada.")
    return source


def load_source_data(
    db: Session, user_id: uuid.UUID, source: DataSource
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Retorna (schema, rows) de qualquer fonte (nativa viva ou snapshot salvo)."""
    req_res = NATIVE_SOURCE_RESOURCE.get(source.kind)
    if req_res is not None:
        owner = db.get(User, user_id)
        if owner is not None:
            admin_service.assert_resource_allowed(db, owner, req_res)

    if source.kind == "native_crm":
        return hub_bridge.native_crm_deals_dataset(db, user_id)
    if source.kind == "native_crm_contacts":
        return hub_bridge.native_crm_contacts_dataset(db, user_id)
    if source.kind == "native_messaging":
        return hub_bridge.native_messaging_dataset(db, user_id)
    if source.kind == "native_budget":
        return hub_bridge.native_budget_dataset(db, user_id)
    if source.kind == "native_catalog":
        return hub_bridge.native_catalog_dataset(db, user_id)

    snap = db.scalar(
        select(DataSnapshot)
        .where(DataSnapshot.source_id == source.id)
        .order_by(DataSnapshot.created_at.desc())
    )
    schema = list(source.schema_json or [])
    rows = list(snap.rows_json or []) if snap else []
    return schema, rows


def serialize_source(db: Session, user_id: uuid.UUID, source: DataSource) -> dict[str, Any]:
    row_count = source.row_count
    schema = list(source.schema_json or [])
    if source.kind in NATIVE_KINDS:
        schema, rows = load_source_data(db, user_id, source)
        row_count = len(rows)
    config = dict(source.config_json or {})
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "description": source.description,
        "config": config,
        "has_credentials": source.credentials_encrypted is not None,
        "schema": schema,
        "row_count": row_count,
        "last_synced_at": source.last_synced_at,
        "last_error": source.last_error,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def list_sources(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    sources = ensure_native_sources(db, user_id)
    owner = db.get(User, user_id)
    blocked = admin_service.effective_blocked_resources(db, owner) if owner is not None else set()
    visible = [s for s in sources if NATIVE_SOURCE_RESOURCE.get(s.kind) not in blocked]
    return [serialize_source(db, user_id, s) for s in visible]


def _normalize_schema_and_rows(
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if not columns:
        raise AppError(400, "empty_schema", "Informe pelo menos uma coluna para a fonte de dados.")
    clean_schema: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, col in enumerate(columns):
        key = slugify_column(col.get("name") or col.get("label") or f"col_{idx + 1}")
        if key in seen:
            key = f"{key}_{idx + 1}"
        seen.add(key)
        col_type = col.get("type") or "text"
        if col_type not in {"text", "number", "currency", "date", "phone", "email", "boolean"}:
            col_type = "text"
        clean_schema.append(
            {
                "name": key,
                "label": (col.get("label") or key)[:60],
                "type": col_type,
            }
        )

    clean_rows: list[dict[str, Any]] = []
    for raw in rows[:MAX_ROWS]:
        item: dict[str, Any] = {}
        for col in clean_schema:
            val = raw.get(col["name"])
            item[col["name"]] = coerce_cell(val, col["type"])
        clean_rows.append(item)
    return clean_schema, clean_rows


def _save_snapshot(db: Session, source: DataSource, rows: list[dict[str, Any]]) -> None:
    existing_ids = list(
        db.scalars(
            select(DataSnapshot.id)
            .where(DataSnapshot.source_id == source.id)
            .order_by(DataSnapshot.created_at.desc())
        ).all()
    )
    if len(existing_ids) >= 3:
        db.execute(delete(DataSnapshot).where(DataSnapshot.id.in_(existing_ids[2:])))

    now = utcnow()
    db.add(
        DataSnapshot(
            source_id=source.id,
            rows_json=rows,
            row_count=len(rows),
            checksum=_checksum(rows),
            created_at=now,
        )
    )
    source.row_count = len(rows)
    source.last_synced_at = now
    source.last_error = None
    source.updated_at = now


def save_tabular_source(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    kind: str,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    description: str | None = None,
    config: dict[str, Any] | None = None,
    source_id: uuid.UUID | None = None,
    mode: str = "replace",
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Cria ou atualiza uma DataSource a partir de PDF ou CSV já conferido na prévia."""
    if kind not in {"pdf", "csv"}:
        raise AppError(400, "invalid_kind", "Tipo de fonte tabular inválido.")
    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise AppError(400, "invalid_name", "Informe um nome para a fonte de dados.")

    schema, clean_rows = _normalize_schema_and_rows(columns, rows)

    if source_id is not None:
        source = get_source(db, user_id, source_id)
        if mode == "append":
            _, old_rows = load_source_data(db, user_id, source)
            merged = list(old_rows)
            if dedupe_key:
                seen_keys = {
                    str(r.get(dedupe_key)).strip().lower()
                    for r in old_rows
                    if r.get(dedupe_key) not in (None, "")
                }
                for r in clean_rows:
                    val = r.get(dedupe_key)
                    norm = str(val).strip().lower() if val not in (None, "") else ""
                    if norm and norm in seen_keys:
                        continue
                    if norm:
                        seen_keys.add(norm)
                    merged.append(r)
            else:
                merged.extend(clean_rows)
            clean_rows = merged[:MAX_ROWS]
        source.name = clean_name
        source.description = (description or "").strip()[:300] or source.description
        source.schema_json = schema
        if config:
            source.config_json = {**(source.config_json or {}), **config}
    else:
        source = DataSource(
            user_id=user_id,
            name=clean_name,
            kind=kind,
            description=(description or "").strip()[:300] or None,
            config_json=config or {},
            schema_json=schema,
        )
        db.add(source)
        db.flush()

    _check_snapshot_quota(db, user_id, clean_rows)
    _save_snapshot(db, source, clean_rows)
    db.commit()
    db.refresh(source)
    return serialize_source(db, user_id, source)


def create_api_source(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    url: str,
    method: str = "GET",
    data_path: str | None = None,
    auth_type: str = "none",
    auth_value: str | None = None,
    header_name: str | None = None,
    description: str | None = None,
    sync_now: bool = True,
) -> dict[str, Any]:
    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise AppError(400, "invalid_name", "Informe um nome para a conexão de API.")
    # Ao sincronizar agora, a busca já valida e fixa o destino antes de conectar.
    validated_url = url.strip() if sync_now else api_connector.validate_api_url(url)
    encrypted = api_connector.encrypt_credentials(auth_type, auth_value, header_name)

    config = {
        "url": validated_url,
        "method": method.upper(),
        "data_path": (data_path or "").strip() or None,
        "auth_type": auth_type,
        "header_name": (header_name or "X-API-Key").strip() if auth_type == "api_key" else None,
    }
    schema: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    if sync_now:
        fetched = api_connector.fetch_external_api(
            url=validated_url,
            method=method,
            data_path=data_path,
            credentials_encrypted=encrypted,
        )
        schema = fetched["columns"]
        rows = fetched["rows"]
        _check_snapshot_quota(db, user_id, rows)

    source = DataSource(
        user_id=user_id,
        name=clean_name,
        kind="api",
        description=(description or "").strip()[:300] or None,
        config_json=config,
        credentials_encrypted=encrypted,
        schema_json=schema,
    )
    db.add(source)
    db.flush()
    if sync_now:
        _save_snapshot(db, source, rows)
    db.commit()
    db.refresh(source)
    return serialize_source(db, user_id, source)


def sync_api_source(db: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> dict[str, Any]:
    source = get_source(db, user_id, source_id)
    if source.kind != "api":
        raise AppError(400, "not_api_source", "Esta fonte não é uma conexão de API externa.")
    cfg = source.config_json or {}
    try:
        fetched = api_connector.fetch_external_api(
            url=str(cfg.get("url") or ""),
            method=str(cfg.get("method") or "GET"),
            data_path=cfg.get("data_path"),
            credentials_encrypted=source.credentials_encrypted,
        )
    except AppError as exc:
        source.last_error = exc.message[:300]
        source.updated_at = utcnow()
        db.commit()
        raise

    _check_snapshot_quota(db, user_id, fetched["rows"])
    source.schema_json = fetched["columns"]
    _save_snapshot(db, source, fetched["rows"])
    db.commit()
    db.refresh(source)
    return serialize_source(db, user_id, source)


def delete_source(db: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> None:
    source = get_source(db, user_id, source_id)
    if source.kind.startswith("native_"):
        raise AppError(
            400, "cannot_delete_native", "Fontes nativas do Hub não podem ser excluídas."
        )
    db.execute(update(CrmWidget).where(CrmWidget.source_id == source.id).values(source_id=None))
    db.execute(delete(DataSnapshot).where(DataSnapshot.source_id == source.id))
    db.delete(source)
    db.commit()
