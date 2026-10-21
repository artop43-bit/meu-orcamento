"""Imagens enviadas pelos usuários: validação, limpeza e acesso.

- O tipo é conferido abrindo a imagem (Pillow), nunca pela extensão ou pelo cabeçalho do envio.
- Fotos estáticas são regravadas: some o EXIF (inclusive a localização GPS do celular) e a
  imagem é reduzida ao tamanho útil. GIF e WebP animados ficam como vieram (são verificados
  quadro a quadro e têm limite de tamanho).
- Só o dono, a administração e o autor da solicitação (no caso de anexos) conseguem abrir.
"""

import io
import uuid
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import StoredFile, SupportMessage, SupportThread, User
from app.services import documents

MB = 1024 * 1024
# Proteção contra "bombas" de descompressão (imagens pequenas em bytes e enormes em pixels).
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class Rule:
    max_bytes: int
    max_side: int  # lado maior depois de reduzir (imagens estáticas)
    formats: tuple[str, ...]
    animated: bool


RULES = {
    "attachment": Rule(5 * MB, 2560, ("PNG", "JPEG", "WEBP", "GIF"), animated=True),
    "avatar": Rule(5 * MB, 512, ("PNG", "JPEG", "WEBP", "GIF"), animated=True),
    "banner": Rule(8 * MB, 1600, ("PNG", "JPEG", "WEBP", "GIF"), animated=True),
    # Comprovante de despesa: foto do recibo, nota ou boleto (legível, sem animação).
    "receipt": Rule(5 * MB, 2560, ("PNG", "JPEG", "WEBP"), animated=False),
    # Imagem do objetivo de uma meta.
    "goal": Rule(8 * MB, 1600, ("PNG", "JPEG", "WEBP", "GIF"), animated=True),
}
# Comprovantes e imagens de metas são só do dono (nem a administração abre).
OWNER_ONLY = ("receipt", "goal")
CONTENT_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
LABELS = "PNG, JPG, WebP ou GIF"
STATIC_LABELS = "PNG, JPG ou WebP"
ATTACHMENT_HELP = (
    "Formato não aceito. Envie imagem (PNG, JPG, WebP ou GIF), PDF ou planilha "
    "(XLSX, XLS, CSV ou ODS)."
)


def _too_big(rule: Rule) -> AppError:
    return AppError(413, "file_too_large", f"A imagem passa de {rule.max_bytes // MB} MB.")


def prepare(raw: bytes, purpose: str) -> tuple[bytes, str, int, int]:
    """Confere e limpa a imagem. Devolve (bytes, content_type, largura, altura)."""
    rule = RULES[purpose]
    if not raw:
        raise AppError(400, "empty_file", "O arquivo está vazio.")
    if len(raw) > rule.max_bytes:
        raise _too_big(rule)
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format or ""
            probe.verify()  # estrutura do arquivo íntegra
        image = Image.open(io.BytesIO(raw))
        fmt = image.format or fmt
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise AppError(
            400, "invalid_image", f"Arquivo não é uma imagem válida ({LABELS})."
        ) from exc
    if fmt not in rule.formats:
        accepted = LABELS if "GIF" in rule.formats else STATIC_LABELS
        raise AppError(400, "invalid_image", f"Formato não aceito. Use {accepted}.")
    width, height = image.size
    if width * height > MAX_PIXELS or width < 1 or height < 1:
        raise AppError(400, "invalid_image", "Imagem com dimensões fora do permitido.")

    animated = bool(getattr(image, "is_animated", False)) and getattr(image, "n_frames", 1) > 1
    if animated:
        if not rule.animated:
            raise AppError(400, "invalid_image", "Imagens animadas não são aceitas aqui.")
        try:  # decodifica todos os quadros: arquivo corrompido não passa
            for frame in range(image.n_frames):
                image.seek(frame)
                image.load()
        except (OSError, EOFError) as exc:
            raise AppError(400, "invalid_image", "Animação corrompida.") from exc
        return raw, CONTENT_TYPES[fmt], width, height

    # Estática: aplica a rotação do EXIF, reduz e regrava sem metadados.
    image = ImageOps.exif_transpose(image)
    image.thumbnail((rule.max_side, rule.max_side))
    out = io.BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=86, optimize=True)
    elif fmt == "PNG":
        image.save(out, "PNG", optimize=True)
    elif fmt == "GIF":
        image.save(out, "GIF")
    else:
        image.save(out, "WEBP", quality=86)
    data = out.getvalue()
    if len(data) > rule.max_bytes:
        raise _too_big(rule)
    return data, CONTENT_TYPES[fmt], image.width, image.height


def store(
    db: Session,
    owner: User,
    raw: bytes,
    purpose: str,
    message_id: uuid.UUID | None = None,
    filename: str | None = None,
) -> StoredFile:
    name = None
    kind = documents.detect(raw) if purpose == "attachment" and raw else None
    if kind is not None:
        # v1.3.1: PDF e planilhas nas solicitações (guardados como vieram, só para baixar).
        if len(raw) > RULES[purpose].max_bytes:
            raise _too_big(RULES[purpose])
        data, content_type, width, height = raw, kind, 0, 0
        name = documents.safe_name(filename, kind)
    else:
        try:
            data, content_type, width, height = prepare(raw, purpose)
        except AppError as exc:
            if purpose == "attachment" and exc.code == "invalid_image":
                raise AppError(400, "invalid_file", ATTACHMENT_HELP) from exc
            raise
    item = StoredFile(
        owner_id=owner.id,
        purpose=purpose,
        message_id=message_id,
        filename=name,
        content_type=content_type,
        size=len(data),
        width=width,
        height=height,
        data=data,
    )
    db.add(item)
    db.flush()
    return item


def latest(db: Session, owner_id: uuid.UUID, purpose: str) -> StoredFile | None:
    return db.scalar(
        select(StoredFile)
        .where(StoredFile.owner_id == owner_id, StoredFile.purpose == purpose)
        .order_by(StoredFile.created_at.desc())
        .limit(1)
    )


def latest_ids(db: Session, owner_ids: list[uuid.UUID], purpose: str) -> dict[uuid.UUID, uuid.UUID]:
    """Foto (ou banner) atual de vários usuários de uma vez: {usuário: arquivo}."""
    if not owner_ids:
        return {}
    rows = db.execute(
        select(StoredFile.owner_id, StoredFile.id, StoredFile.created_at)
        .where(StoredFile.owner_id.in_(owner_ids), StoredFile.purpose == purpose)
        .order_by(StoredFile.created_at)
    )
    return {owner: file_id for owner, file_id, _ in rows}


def can_read(db: Session, user: User, item: StoredFile) -> bool:
    from app.services.auth import is_admin

    if item.owner_id == user.id:
        return True
    if item.purpose in OWNER_ONLY:
        return False
    if is_admin(user):
        return True
    if item.purpose == "attachment" and item.message_id is not None:
        thread_owner = db.scalar(
            select(SupportThread.user_id)
            .join(SupportMessage, SupportMessage.thread_id == SupportThread.id)
            .where(SupportMessage.id == item.message_id)
        )
        return thread_owner == user.id
    return False


def get_for(db: Session, user: User, file_id: uuid.UUID) -> StoredFile:
    item = db.get(StoredFile, file_id)
    # Mesmo erro para "não existe" e "não é seu": não revela quais arquivos existem.
    if item is None or not can_read(db, user, item):
        raise AppError(404, "not_found", "Imagem não encontrada.")
    return item
