"""Mídias da Mensageria (fotos, áudios, vídeos, figurinhas e documentos) com limite de tamanho."""

import re
import unicodedata
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utcnow
from app.models import MessagingMedia, MessagingMessage, MessagingSession, User, VaultDocument
from app.services.common import get_owned

# Limite seguro para proteger memória e banco na VM ARM64.
MAX_MEDIA_BYTES = 8 * 1024 * 1024
# Teto das mídias guardadas por conta. Elas são temporárias (somem em 7 dias), não contam na
# cota de arquivos e nunca bloqueiam nada: passando do teto, as mais antigas saem antes.
MEDIA_CAP_BYTES = 300 * 1024 * 1024
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MEDIA_KINDS = ("image", "audio", "video", "document", "sticker")

# Tipos seguros para exibição direta no navegador (exclui HTML e SVG para evitar script).
INLINE_IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/avif"}
)
INLINE_AUDIO_MIMES = frozenset(
    {
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/webm",
        "audio/aac",
        "audio/wav",
        "audio/x-wav",
        "audio/x-m4a",
        "audio/opus",
    }
)
INLINE_VIDEO_MIMES = frozenset({"video/mp4", "video/webm", "video/3gpp", "video/quicktime"})

MEDIA_LABELS = {
    "image": "📷 Foto",
    "audio": "🎤 Áudio",
    "video": "🎬 Vídeo",
    "document": "📄 Documento",
    "sticker": "Figurinha",
}


def clean_mime_type(raw: str | None) -> str:
    base = (raw or "").split(";", 1)[0].strip().lower()
    if not base or "/" not in base or len(base) > 120:
        return "application/octet-stream"
    if not re.match(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$", base):
        return "application/octet-stream"
    return base


def clean_file_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f\"<>|*?]", "", name).strip()
    return name[:200] or None


def ascii_filename(raw: str | None, fallback: str = "arquivo") -> str:
    """Nome sem acentos nem aspas para o cabeçalho Content-Disposition."""
    cleaned = clean_file_name(raw) or fallback
    normalized = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", normalized).strip(" .")
    return safe[:160] or fallback


def infer_media_kind(mime_type: str, file_name: str | None = None) -> str:
    mime = clean_mime_type(mime_type)
    if mime in INLINE_IMAGE_MIMES:
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime in INLINE_VIDEO_MIMES or mime.startswith("video/"):
        return "video"
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if file_name and "." in file_name else ""
    if ext in {"jpg", "jpeg", "png", "webp", "gif", "heic", "heif", "avif"}:
        return "image"
    if ext in {"ogg", "opus", "mp3", "m4a", "wav", "aac"}:
        return "audio"
    if ext in {"mp4", "webm", "mov", "3gp"}:
        return "video"
    return "document"


def is_inline_safe(kind: str, mime_type: str) -> bool:
    mime = clean_mime_type(mime_type)
    if kind in {"image", "sticker"}:
        return mime in INLINE_IMAGE_MIMES
    if kind == "audio":
        return mime in INLINE_AUDIO_MIMES
    if kind == "video":
        return mime in INLINE_VIDEO_MIMES
    return False


def media_label(kind: str, file_name: str | None = None, caption: str | None = None) -> str:
    base = MEDIA_LABELS.get(kind, "📄 Documento")
    clean_caption = (caption or "").strip()
    if kind == "document":
        name = clean_file_name(file_name)
        if name and clean_caption:
            return f"{base} · {name} · {clean_caption}"
        if name:
            return f"{base} · {name}"
    return f"{base} · {clean_caption}" if clean_caption else base


def sniff_media_mime(data: bytes, declared_mime: str | None, kind: str | None = None) -> str:
    """Detecta o MIME real pelos primeiros bytes quando o navegador/celular manda tipo genérico."""
    head = data[:16]
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        cleaned = clean_mime_type(declared_mime)
        if kind == "video" or cleaned.startswith("video/"):
            return "video/webm"
        return "audio/webm"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}:
            return "image/heic"
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        cleaned = clean_mime_type(declared_mime)
        if brand == b"M4A " or kind == "audio" or cleaned.startswith("audio/"):
            return "audio/mp4"
        return "video/mp4"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return clean_mime_type(declared_mime)


def store_media(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: str,
    mime_type: str,
    data: bytes,
    file_name: str | None = None,
) -> MessagingMedia:
    if not data:
        raise AppError(400, "empty_media", "Selecione um arquivo antes de enviar.")
    if len(data) > MAX_MEDIA_BYTES:
        raise AppError(
            413,
            "media_too_large",
            "O arquivo passa do limite de 8 MB permitido para envio.",
        )
    safe_mime = sniff_media_mime(data, mime_type, kind)
    safe_name = clean_file_name(file_name)
    safe_kind = kind if kind in MEDIA_KINDS else infer_media_kind(safe_mime, safe_name)
    if safe_mime in {"image/heic", "image/avif"}:
        safe_kind = "image"
    # SVG nunca entra como imagem exibida direto no navegador.
    if safe_mime == "image/svg+xml":
        safe_kind = "document"
    media = MessagingMedia(
        user_id=user_id,
        kind=safe_kind,
        mime_type=safe_mime,
        file_name=safe_name,
        size_bytes=len(data),
        data=data,
    )
    db.add(media)
    db.flush()
    trim_to_cap(db, user_id, keep_id=media.id)
    return media


def release_media(db: Session, media_ids: set[uuid.UUID]) -> int:
    """Apaga mídias soltando antes as mensagens e a cópia do Cofre que apontam para elas."""
    if not media_ids:
        return 0
    now = utcnow()
    db.execute(
        update(MessagingMessage)
        .where(MessagingMessage.media_id.in_(media_ids))
        .values(media_id=None, updated_at=now)
    )
    # Mantém a cópia permanente do Cofre intacta mesmo no SQLite sem FK cascata.
    db.execute(
        update(VaultDocument)
        .where(VaultDocument.messaging_media_id.in_(media_ids))
        .values(messaging_media_id=None, updated_at=now)
    )
    return db.execute(delete(MessagingMedia).where(MessagingMedia.id.in_(media_ids))).rowcount


def media_bytes(db: Session, user_id: uuid.UUID) -> int:
    """Espaço ocupado pelas mídias da Mensageria da conta."""
    total = db.scalar(
        select(func.coalesce(func.sum(MessagingMedia.size_bytes), 0)).where(
            MessagingMedia.user_id == user_id
        )
    )
    return int(total or 0)


def trim_to_cap(
    db: Session,
    user_id: uuid.UUID,
    *,
    keep_id: uuid.UUID | None = None,
    cap_bytes: int = MEDIA_CAP_BYTES,
) -> int:
    """Passando do teto, apaga as mídias mais antigas da conta (nunca a que acabou de chegar)."""
    excess = media_bytes(db, user_id) - cap_bytes
    if excess <= 0:
        return 0
    rows = db.execute(
        select(MessagingMedia.id, MessagingMedia.size_bytes)
        .where(MessagingMedia.user_id == user_id, MessagingMedia.id != keep_id)
        .order_by(MessagingMedia.created_at, MessagingMedia.id)
    ).all()
    to_delete: set[uuid.UUID] = set()
    for media_id, size in rows:
        if excess <= 0:
            break
        to_delete.add(media_id)
        excess -= int(size or 0)
    return release_media(db, to_delete)


def _active_session_user(db: Session, session_id: uuid.UUID) -> User:
    row = db.execute(
        select(MessagingSession, User)
        .join(User, User.id == MessagingSession.user_id)
        .where(MessagingSession.id == session_id)
    ).first()
    if row is None or row[1].access_status == "blocked":
        raise AppError(404, "session_not_found", "Sessão não encontrada.")
    return row[1]


def store_connector_media(
    db: Session,
    session_id: uuid.UUID,
    *,
    kind: str,
    mime_type: str,
    data: bytes,
    file_name: str | None = None,
) -> MessagingMedia:
    user = _active_session_user(db, session_id)
    media = store_media(
        db,
        user.id,
        kind=kind,
        mime_type=mime_type,
        data=data,
        file_name=file_name,
    )
    db.commit()
    db.refresh(media)
    return media


def get_media_for_user(db: Session, user: User, media_id: uuid.UUID) -> MessagingMedia:
    return get_owned(
        db,
        MessagingMedia,
        user.id,
        media_id,
        error_code="media_not_found",
        error_msg="Mídia não encontrada.",
    )


def get_media_for_connector(
    db: Session, session_id: uuid.UUID, media_id: uuid.UUID
) -> MessagingMedia:
    user = _active_session_user(db, session_id)
    return get_media_for_user(db, user, media_id)
