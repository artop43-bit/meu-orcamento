"""Serviços do Cofre de Documentos (`/cofre`): arquivo permanente, validade e OCR local."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from typing import Any

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.months import today_local
from app.db.types import utcnow
from app.models import (
    CommercialDocument,
    CrmContact,
    MessagingChat,
    MessagingMedia,
    MessagingMessage,
    User,
    VaultDocument,
)
from app.services import admin as admin_service
from app.services import files
from app.services import ocr as receipt_ocr
from app.services.commerce import proposals as proposals_service
from app.services.common import get_owned
from app.services.crm.pdf_reader import MAX_OCR_PAGES, MAX_PDF_PAGES, MIN_DIGITAL_CHARS, _ocr_page
from app.services.memory.bridges import list_memory_bridges, validate_hub_links
from app.services.memory.notebook import fold_text
from app.services.messaging.media import ascii_filename, clean_file_name

MAX_VAULT_BYTES = 15 * 1024 * 1024
VAULT_CATEGORIES = (
    "warranty",
    "contract",
    "fiscal",
    "receipt",
    "certificate",
    "identity",
    "other",
)
CATEGORY_LABELS: dict[str, str] = {
    "warranty": "Garantia",
    "contract": "Contrato",
    "fiscal": "Nota fiscal",
    "receipt": "Comprovante / Recibo",
    "certificate": "Certificado / Apólice",
    "identity": "Documento pessoal",
    "other": "Outro documento",
}
EXPIRY_FILTER_STATUSES = ("all", "valid", "expiring_soon", "expired", "no_expiry")


def _extract_pdf_text(raw: bytes, *, allow_ocr: bool) -> tuple[str | None, bool, str | None]:
    """Lê texto digital do PDF e roda OCR local limitado quando for escaneado."""
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise AppError(
            400, "invalid_pdf", "O arquivo PDF enviado está corrompido ou ilegível."
        ) from exc

    chunks: list[str] = []
    ocr_used = False
    ocr_pages = 0
    truncated = False
    try:
        total = len(doc)
        if total == 0:
            raise AppError(400, "empty_pdf", "O PDF enviado não possui páginas.")
        for idx in range(min(total, MAX_PDF_PAGES)):
            page = doc[idx]
            text = (page.get_text("text") or "").strip()
            if len(text) < MIN_DIGITAL_CHARS and allow_ocr and receipt_ocr.available():
                if ocr_pages >= MAX_OCR_PAGES:
                    truncated = True
                else:
                    try:
                        ocr_txt = (_ocr_page(page) or "").strip()
                    except AppError:
                        ocr_txt = ""
                    if ocr_txt:
                        text = ocr_txt
                        ocr_used = True
                        ocr_pages += 1
            if text:
                chunks.append(text)
    finally:
        doc.close()

    merged = "\n\n".join(chunks).strip()[:100_000] or None
    warning = f"Indexado por OCR até {MAX_OCR_PAGES} páginas digitalizadas." if truncated else None
    return merged, ocr_used, warning


def _prepare_vault_payload(
    raw: bytes,
    filename: str | None,
    *,
    allow_ocr: bool,
) -> tuple[bytes, str, str, str | None, bool, str | None]:
    """Valida PDF ou imagem por conteúdo real e extrai texto para busca."""
    if not raw:
        raise AppError(400, "empty_file", "O arquivo enviado está vazio.")
    if len(raw) > MAX_VAULT_BYTES:
        raise AppError(413, "file_too_large", "O documento ultrapassa o limite de 15 MB.")

    safe_name = clean_file_name(filename) or "documento"
    head = raw.lstrip()[:16]
    if head.startswith(b"%PDF"):
        extracted_text, ocr_used, warning = _extract_pdf_text(raw, allow_ocr=allow_ocr)
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{safe_name}.pdf"
        return raw, "application/pdf", safe_name[:160], extracted_text, ocr_used, warning

    # Para não aceitar SVG/HTML nem bombas de pixel, revalida imagens pelo Pillow.
    prepared, content_type, _, _ = files.prepare(raw, "receipt")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(content_type, "img")
    if "." not in safe_name:
        safe_name = f"{safe_name}.{ext}"

    extracted_text = None
    ocr_used = False
    if allow_ocr and receipt_ocr.available():
        try:
            res = receipt_ocr.extract(prepared)
            extracted_text = (res.texto_extraido or "").strip()[:100_000] or None
            ocr_used = bool(extracted_text)
        except AppError:
            extracted_text = None
    return prepared, content_type, safe_name[:160], extracted_text, ocr_used, None


def _expiry_state(doc: VaultDocument, ref: date) -> tuple[str, int | None]:
    if doc.expires_at is None:
        return "no_expiry", None
    days_left = (doc.expires_at - ref).days
    if days_left < 0:
        return "expired", days_left
    window = max(0, min(365, int(doc.notify_days_before or 30)))
    if days_left <= window:
        return "expiring_soon", days_left
    return "valid", days_left


def _serialize(doc: VaultDocument, ref: date) -> dict[str, Any]:
    expiry_status, days_left = _expiry_state(doc, ref)
    excerpt = (doc.extracted_text or "").strip().splitlines()
    preview_txt = " · ".join(line.strip() for line in excerpt if line.strip())[:240] or None
    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "category_label": CATEGORY_LABELS.get(doc.category, "Documento"),
        "issuer": doc.issuer,
        "document_number": doc.document_number,
        "issue_date": doc.issue_date.isoformat() if doc.issue_date else None,
        "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
        "notify_days_before": doc.notify_days_before,
        "expiry_status": expiry_status,
        "days_left": days_left,
        "notes": doc.notes,
        "file_name": doc.file_name,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "ocr_used": bool(doc.ocr_used),
        "has_extracted_text": bool(doc.extracted_text),
        "extracted_preview": preview_txt,
        "file_url": f"/api/cofre/documents/{doc.id}/file",
        "contact_id": doc.contact_id,
        "deal_id": doc.deal_id,
        "project_id": doc.project_id,
        "proposal_id": doc.proposal_id,
        "messaging_media_id": doc.messaging_media_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def list_documents(
    db: Session,
    user: User,
    *,
    category: str | None = None,
    expiry_status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    docs = list(
        db.scalars(
            select(VaultDocument)
            .where(VaultDocument.user_id == user.id)
            .order_by(VaultDocument.created_at.desc())
        ).all()
    )
    ref = today_local()
    needle = fold_text(q)

    items: list[dict[str, Any]] = []
    counts_expiry = {"valid": 0, "expiring_soon": 0, "expired": 0, "no_expiry": 0}
    total_bytes = 0
    ocr_indexed_count = 0

    for d in docs:
        total_bytes += int(d.size_bytes or 0)
        if d.extracted_text:
            ocr_indexed_count += 1
        st, _ = _expiry_state(d, ref)
        counts_expiry[st] = counts_expiry.get(st, 0) + 1
        if category and category != "all" and d.category != category:
            continue
        if expiry_status and expiry_status != "all" and st != expiry_status:
            continue
        if needle:
            hay = fold_text(
                " ".join(
                    part
                    for part in (
                        d.title,
                        d.issuer,
                        d.document_number,
                        d.notes,
                        d.file_name,
                        d.extracted_text,
                    )
                    if part
                )
            )
            if needle not in hay:
                continue
        items.append(_serialize(d, ref))

    used_bytes = admin_service.user_storage_bytes(db, user.id)
    quota_mb = int(getattr(user, "storage_quota_mb", admin_service.DEFAULT_STORAGE_QUOTA_MB) or 200)
    return {
        "documents": items,
        "summary": {
            "total_docs": len(docs),
            "valid_count": counts_expiry["valid"],
            "expiring_count": counts_expiry["expiring_soon"],
            "expired_count": counts_expiry["expired"],
            "no_expiry_count": counts_expiry["no_expiry"],
            "ocr_indexed_count": ocr_indexed_count,
            "vault_bytes": total_bytes,
            "account_used_bytes": used_bytes,
            "quota_mb": quota_mb,
        },
    }


def create_document(
    db: Session,
    user: User,
    *,
    raw: bytes,
    filename: str | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    validate_hub_links(db, user.id, meta)
    category = str(meta.get("category") or "other")
    if category not in VAULT_CATEGORIES:
        category = "other"

    blocked = admin_service.effective_blocked_resources(db, user)
    allow_ocr = "feature:pdf_ocr_upload" not in blocked
    prepared, content_type, safe_name, extracted_text, ocr_used, warning = _prepare_vault_payload(
        raw, filename, allow_ocr=allow_ocr
    )
    admin_service.assert_storage_quota(db, user, len(prepared))

    title = (str(meta.get("title") or "").strip() or safe_name.rsplit(".", 1)[0])[:160]
    now = utcnow()
    doc = VaultDocument(
        user_id=user.id,
        title=title,
        category=category,
        issuer=(str(meta.get("issuer") or "").strip()[:140] or None),
        document_number=(str(meta.get("document_number") or "").strip()[:80] or None),
        issue_date=meta.get("issue_date"),
        expires_at=meta.get("expires_at"),
        notify_days_before=max(0, min(365, int(meta.get("notify_days_before") or 30))),
        notes=(str(meta.get("notes") or "").strip()[:4000] or None),
        file_name=safe_name,
        mime_type=content_type,
        size_bytes=len(prepared),
        sha256=hashlib.sha256(prepared).hexdigest(),
        data=prepared,
        extracted_text=extracted_text,
        ocr_used=ocr_used,
        contact_id=meta.get("contact_id"),
        deal_id=meta.get("deal_id"),
        project_id=meta.get("project_id"),
        proposal_id=meta.get("proposal_id"),
        messaging_media_id=meta.get("messaging_media_id"),
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    out = _serialize(doc, today_local())
    if warning:
        out["warning"] = warning
    return out


def update_document(
    db: Session, user: User, doc_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    doc = get_owned(
        db,
        VaultDocument,
        user.id,
        doc_id,
        error_code="vault_doc_not_found",
        error_msg="Documento não encontrado.",
    )
    validate_hub_links(db, user.id, changes)
    if "title" in changes and changes["title"] is not None:
        clean = str(changes["title"]).strip()[:160]
        if clean:
            doc.title = clean
    if "category" in changes and changes["category"] in VAULT_CATEGORIES:
        doc.category = str(changes["category"])
    for str_field, limit in (("issuer", 140), ("document_number", 80), ("notes", 4000)):
        if str_field in changes:
            val = str(changes[str_field] or "").strip()[:limit]
            setattr(doc, str_field, val or None)
    for dt_field in ("issue_date", "expires_at"):
        if dt_field in changes:
            setattr(doc, dt_field, changes[dt_field])
    if "notify_days_before" in changes and changes["notify_days_before"] is not None:
        doc.notify_days_before = max(0, min(365, int(changes["notify_days_before"])))
    for fk in ("contact_id", "deal_id", "project_id", "proposal_id"):
        if fk in changes:
            setattr(doc, fk, changes[fk])
    doc.updated_at = utcnow()
    db.commit()
    db.refresh(doc)
    return _serialize(doc, today_local())


def delete_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    doc = get_owned(
        db,
        VaultDocument,
        user_id,
        doc_id,
        error_code="vault_doc_not_found",
        error_msg="Documento não encontrado.",
    )
    db.delete(doc)
    db.commit()


def get_document_file(
    db: Session, user_id: uuid.UUID, doc_id: uuid.UUID
) -> tuple[VaultDocument, str]:
    doc = get_owned(
        db,
        VaultDocument,
        user_id,
        doc_id,
        error_code="vault_doc_not_found",
        error_msg="Documento não encontrado.",
    )
    return doc, ascii_filename(doc.file_name, "documento")


def archive_from_messaging_media(
    db: Session,
    user: User,
    media_id: uuid.UUID,
    *,
    title: str | None = None,
    category: str = "other",
    expires_at: date | None = None,
) -> dict[str, Any]:
    """Copia foto/PDF da Mensageria para o Cofre antes da limpeza semanal de 7 dias."""
    admin_service.assert_resource_allowed(db, user, "mensageria")
    media = get_owned(
        db,
        MessagingMedia,
        user.id,
        media_id,
        error_code="media_not_found",
        error_msg="Mídia não encontrada.",
    )
    existing = db.scalar(
        select(VaultDocument).where(
            VaultDocument.user_id == user.id,
            VaultDocument.messaging_media_id == media.id,
        )
    )
    if existing is not None:
        return {"archived": False, "document": _serialize(existing, today_local())}

    contact_id: uuid.UUID | None = None
    msg = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.user_id == user.id, MessagingMessage.media_id == media.id
        )
    )
    chat_name: str | None = None
    if msg is not None:
        chat = db.scalar(
            select(MessagingChat).where(
                MessagingChat.id == msg.chat_id, MessagingChat.user_id == user.id
            )
        )
        if chat is not None:
            chat_name = chat.name
            contact = db.scalar(
                select(CrmContact).where(
                    CrmContact.user_id == user.id, CrmContact.messaging_chat_id == chat.id
                )
            )
            if contact is not None:
                contact_id = contact.id

    fallback_title = (
        title
        or media.file_name
        or (f"Arquivo WhatsApp · {chat_name}" if chat_name else "Mídia WhatsApp")
    )
    doc = create_document(
        db,
        user,
        raw=media.data,
        filename=media.file_name or ("arquivo.pdf" if "pdf" in media.mime_type else "imagem.png"),
        meta={
            "title": fallback_title[:160],
            "category": category,
            "issuer": chat_name,
            "expires_at": expires_at,
            "notes": "Arquivado a partir da Mensageria (protegido da limpeza semanal).",
            "contact_id": contact_id,
            "messaging_media_id": media.id,
        },
    )
    return {"archived": True, "document": doc}


def archive_from_proposal(
    db: Session,
    user: User,
    doc_id: uuid.UUID,
    *,
    category: str | None = None,
    expires_at: date | None = None,
) -> dict[str, Any]:
    """Gera o PDF A4 do documento comercial e arquiva no Cofre (idempotente)."""
    admin_service.assert_resource_allowed(db, user, "propostas")
    prop = get_owned(
        db,
        CommercialDocument,
        user.id,
        doc_id,
        error_code="document_not_found",
        error_msg="Documento comercial não encontrado.",
    )
    existing = db.scalar(
        select(VaultDocument).where(
            VaultDocument.user_id == user.id,
            VaultDocument.proposal_id == prop.id,
        )
    )
    if existing is not None:
        return {"archived": False, "document": _serialize(existing, today_local())}

    pdf_bytes, filename = proposals_service.render_document_pdf(db, user, prop.id)
    cat_by_type = {"contract": "contract", "receipt": "receipt"}
    default_cat = cat_by_type.get(prop.doc_type, "other")
    created = create_document(
        db,
        user,
        raw=pdf_bytes,
        filename=filename or f"{prop.doc_type}-{prop.number:04d}.pdf",
        meta={
            "title": f"#{prop.number:04d} · {prop.title}"[:160],
            "category": category or default_cat,
            "issuer": prop.customer_name,
            "document_number": f"#{prop.number:04d}",
            "issue_date": prop.created_at.date(),
            "expires_at": expires_at or prop.valid_until,
            "notes": f"Cópia arquivada de Propostas & PDFs ({prop.doc_type}).",
            "contact_id": prop.contact_id,
            "deal_id": prop.crm_deal_id,
            "proposal_id": prop.id,
        },
    )
    return {"archived": True, "document": created}


def list_hub_bridges(db: Session, user: User) -> dict[str, Any]:
    return list_memory_bridges(db, user, include_proposals=True)


def collect_agenda_expiries(
    db: Session, user: User, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    """Camada da Agenda 360° com validades e garantias próximas no Cofre."""
    docs = list(
        db.scalars(
            select(VaultDocument).where(
                VaultDocument.user_id == user.id,
                VaultDocument.expires_at.is_not(None),
                VaultDocument.expires_at >= start_date,
                VaultDocument.expires_at <= end_date,
            )
        ).all()
    )
    ref = today_local()
    out: list[dict[str, Any]] = []
    for d in docs:
        assert d.expires_at is not None
        status, _ = _expiry_state(d, ref)
        cat_label = CATEGORY_LABELS.get(d.category, "Documento")
        out.append(
            {
                "uid": f"cofre:{d.id}",
                "id": d.id,
                "layer": "cofre",
                "kind": "vault_expiry",
                "title": f"Validade ({cat_label}): {d.title}",
                "subtitle": d.issuer or d.file_name,
                "date": d.expires_at.isoformat(),
                "time": None,
                "status": "overdue" if status == "expired" else "open",
                "contact_id": d.contact_id,
                "project_id": d.project_id,
            }
        )
    return out
