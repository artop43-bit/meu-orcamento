"""Serviços do Caderno & Base de Conhecimento (`/caderno`): BM25 local, wikilinks e modelos."""

from __future__ import annotations

import math
import re
import unicodedata
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import NotebookNote, User
from app.services.common import get_owned
from app.services.memory.bridges import list_memory_bridges, validate_hub_links

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]")
TOKEN_RE = re.compile(r"[a-z0-9]+")

NOTE_TEMPLATES: dict[str, dict[str, str]] = {
    "blank": {
        "label": "Nota livre",
        "folder": "Geral",
        "title": "Nova anotação",
        "content": (
            "# Nova anotação\n\nEscreva aqui seus pontos principais.\n\n"
            "Use `[[Nome de outra nota]]` para conectar ideias.\n"
        ),
    },
    "meeting": {
        "label": "Ata de reunião",
        "folder": "Comercial",
        "title": "Ata · Alinhamento com cliente",
        "content": (
            "# Ata de reunião\n\n"
            "- **Participantes:** \n"
            "- **Objetivo:** \n\n"
            "## Decisões tomadas\n- \n\n"
            "## Próximos passos\n- [ ] Definir responsável e prazo\n"
        ),
    },
    "sales_script": {
        "label": "Roteiro WhatsApp",
        "folder": "Comercial",
        "title": "Roteiro · Primeiro contato e proposta",
        "content": (
            "# Roteiro de atendimento\n\n"
            "Olá! Tudo bem? Vi seu interesse e já preparei os detalhes principais:\n\n"
            "1. **Escopo:** ...\n"
            "2. **Prazo:** ...\n"
            "3. **Condição:** ...\n\n"
            "Se fizer sentido para você, posso te mandar a proposta completa em PDF agora.\n"
        ),
    },
    "sop": {
        "label": "Procedimento (POP)",
        "folder": "Operação",
        "title": "POP · Entrega padrão",
        "content": (
            "# Procedimento padrão (POP)\n\n"
            "## Quando usar\nSempre que iniciar um novo pedido ou entrega.\n\n"
            "## Passo a passo\n"
            "1. Conferir dados do cliente no [[Dashboard & CRM]].\n"
            "2. Validar itens, prazos e garantia no Cofre.\n"
            "3. Registrar conclusão e enviar resumo pelo WhatsApp.\n"
        ),
    },
    "planning": {
        "label": "Planejamento pessoal",
        "folder": "Pessoal",
        "title": "Plano do trimestre",
        "content": (
            "# Planejamento\n\n"
            "## Meta principal\n\n"
            "## Marcos do mês\n- [ ] Passo 1\n- [ ] Passo 2\n\n"
            "## Riscos e cuidados\n- \n"
        ),
    },
}


def fold_text(raw: str | None) -> str:
    """Remove acentos e normaliza espaços para busca BM25 e resolução de `[[links]]`."""
    nfkd = unicodedata.normalize("NFKD", (raw or "").strip())
    plain = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", plain.lower()).strip()


def tokenize(raw: str | None) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(fold_text(raw)) if len(tok) >= 2 or tok.isdigit()]


def extract_wikilinks(content: str | None) -> list[str]:
    seen: list[str] = []
    seen_keys: set[str] = set()
    for match in WIKILINK_RE.finditer(content or ""):
        label = re.sub(r"\s+", " ", match.group(1)).strip()[:160]
        key = fold_text(label)
        if label and key not in seen_keys:
            seen_keys.add(key)
            seen.append(label)
    return seen


def bm25_rank(notes: list[NotebookNote], query: str) -> dict[uuid.UUID, float]:
    """Calcula pontuação BM25 local dando peso extra a título e etiquetas."""
    q_tokens = tokenize(query)
    if not q_tokens:
        return {n.id: 0.0 for n in notes}

    docs: list[tuple[uuid.UUID, list[str]]] = []
    df: Counter[str] = Counter()
    for note in notes:
        tags_txt = " ".join(note.tags or [])
        weighted_tokens = (
            tokenize(note.title) * 3
            + tokenize(f"{note.folder} {tags_txt}") * 2
            + tokenize(note.content)
        )
        docs.append((note.id, weighted_tokens))
        for tok in set(weighted_tokens):
            df[tok] += 1

    total_docs = len(docs)
    avgdl = max(sum(len(toks) for _, toks in docs) / max(total_docs, 1), 1.0)
    k1 = 1.5
    b = 0.75

    scores: dict[uuid.UUID, float] = {}
    q_fold = fold_text(query)
    for note, (nid, toks) in zip(notes, docs, strict=True):
        tf = Counter(toks)
        dl = len(toks)
        score = 0.0
        for term in q_tokens:
            freq = tf.get(term, 0)
            if freq == 0:
                continue
            doc_freq = df.get(term, 0)
            idf = math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denom = freq + k1 * (1.0 - b + b * (dl / avgdl))
            score += idf * ((freq * (k1 + 1.0)) / denom)
        # Bônus determinístico para substring exata no título ou conteúdo
        if q_fold and q_fold in fold_text(note.title):
            score += 4.0
        elif q_fold and q_fold in fold_text(note.content):
            score += 1.5
        scores[nid] = round(score, 4)
    return scores


def _clean_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in raw[:12]:
        tag = re.sub(r"\s+", " ", str(entry or "")).strip()[:30]
        key = fold_text(tag)
        if tag and key not in seen:
            seen.add(key)
            out.append(tag)
    return out


def _serialize_note(
    note: NotebookNote,
    *,
    by_folded_title: dict[str, NotebookNote],
    backlinks_map: dict[uuid.UUID, list[dict[str, Any]]],
    score: float | None = None,
) -> dict[str, Any]:
    raw_links = extract_wikilinks(note.content)
    links: list[dict[str, Any]] = []
    for label in raw_links:
        target = by_folded_title.get(fold_text(label))
        links.append(
            {
                "label": label,
                "target_id": str(target.id) if target else None,
                "target_title": target.title if target else None,
            }
        )
    return {
        "id": note.id,
        "title": note.title,
        "folder": note.folder,
        "tags": list(note.tags or []),
        "pinned": bool(note.pinned),
        "template_kind": note.template_kind,
        "content": note.content,
        "links": links,
        "backlinks": backlinks_map.get(note.id, []),
        "score": score,
        "contact_id": note.contact_id,
        "deal_id": note.deal_id,
        "project_id": note.project_id,
        "messaging_chat_id": note.messaging_chat_id,
        "goal_id": note.goal_id,
        "vault_doc_id": note.vault_doc_id,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def _graph_maps(
    notes: list[NotebookNote],
) -> tuple[dict[str, NotebookNote], dict[uuid.UUID, list[dict[str, Any]]]]:
    by_folded_title: dict[str, NotebookNote] = {}
    for n in notes:
        key = fold_text(n.title)
        if key and key not in by_folded_title:
            by_folded_title[key] = n

    backlinks_map: dict[uuid.UUID, list[dict[str, Any]]] = {n.id: [] for n in notes}
    for source in notes:
        for label in extract_wikilinks(source.content):
            target = by_folded_title.get(fold_text(label))
            if target is not None and target.id != source.id:
                bucket = backlinks_map[target.id]
                if not any(b["id"] == source.id for b in bucket):
                    bucket.append({"id": source.id, "title": source.title})
    return by_folded_title, backlinks_map


def list_templates() -> list[dict[str, str]]:
    return [{"id": k, **v} for k, v in NOTE_TEMPLATES.items()]


def list_notes(
    db: Session,
    user_id: uuid.UUID,
    *,
    q: str | None = None,
    folder: str | None = None,
    pinned_only: bool = False,
) -> dict[str, Any]:
    all_notes = list(
        db.scalars(
            select(NotebookNote)
            .where(NotebookNote.user_id == user_id)
            .order_by(NotebookNote.pinned.desc(), NotebookNote.updated_at.desc())
        ).all()
    )
    by_folded_title, backlinks_map = _graph_maps(all_notes)

    scores = bm25_rank(all_notes, q) if q and q.strip() else None
    filtered: list[NotebookNote] = []
    for n in all_notes:
        if pinned_only and not n.pinned:
            continue
        if folder and folder != "all" and fold_text(n.folder) != fold_text(folder):
            continue
        if scores is not None and scores.get(n.id, 0.0) <= 0.0:
            continue
        filtered.append(n)

    if scores is not None:
        filtered.sort(
            key=lambda n: (n.pinned, scores.get(n.id, 0.0), n.updated_at),
            reverse=True,
        )

    folders = sorted({n.folder for n in all_notes if n.folder})
    total_links = sum(len(extract_wikilinks(n.content)) for n in all_notes)
    return {
        "notes": [
            _serialize_note(
                n,
                by_folded_title=by_folded_title,
                backlinks_map=backlinks_map,
                score=scores.get(n.id) if scores is not None else None,
            )
            for n in filtered
        ],
        "summary": {
            "total_notes": len(all_notes),
            "pinned_count": sum(1 for n in all_notes if n.pinned),
            "folders": folders,
            "total_links": total_links,
        },
    }


def create_note(db: Session, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
    validate_hub_links(db, user_id, data)
    tpl = str(data.get("template_kind") or "blank")
    if tpl not in NOTE_TEMPLATES:
        tpl = "blank"
    title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()[:160]
    if not title:
        title = NOTE_TEMPLATES[tpl]["title"]
    folder = re.sub(r"\s+", " ", str(data.get("folder") or "")).strip()[:60]
    if not folder:
        folder = NOTE_TEMPLATES[tpl]["folder"]
    raw_content = (
        data.get("content") if data.get("content") is not None else NOTE_TEMPLATES[tpl]["content"]
    )
    content = str(raw_content)[:60000]
    now = utcnow()
    note = NotebookNote(
        user_id=user_id,
        title=title,
        folder=folder,
        tags=_clean_tags(data.get("tags")),
        pinned=bool(data.get("pinned", False)),
        template_kind=tpl,
        content=content,
        contact_id=data.get("contact_id"),
        deal_id=data.get("deal_id"),
        project_id=data.get("project_id"),
        messaging_chat_id=data.get("messaging_chat_id"),
        goal_id=data.get("goal_id"),
        vault_doc_id=data.get("vault_doc_id"),
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    db.commit()
    all_notes = list(db.scalars(select(NotebookNote).where(NotebookNote.user_id == user_id)).all())
    by_folded_title, backlinks_map = _graph_maps(all_notes)
    refreshed = next(n for n in all_notes if n.id == note.id)
    return _serialize_note(refreshed, by_folded_title=by_folded_title, backlinks_map=backlinks_map)


def update_note(
    db: Session, user_id: uuid.UUID, note_id: uuid.UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    note = get_owned(
        db,
        NotebookNote,
        user_id,
        note_id,
        error_code="note_not_found",
        error_msg="Nota não encontrada.",
    )
    validate_hub_links(db, user_id, changes)
    if "title" in changes and changes["title"] is not None:
        title = re.sub(r"\s+", " ", str(changes["title"])).strip()[:160]
        if title:
            note.title = title
    if "folder" in changes and changes["folder"] is not None:
        folder = re.sub(r"\s+", " ", str(changes["folder"])).strip()[:60]
        if folder:
            note.folder = folder
    if "tags" in changes and changes["tags"] is not None:
        note.tags = _clean_tags(changes["tags"])
    if "pinned" in changes and changes["pinned"] is not None:
        note.pinned = bool(changes["pinned"])
    if "content" in changes and changes["content"] is not None:
        note.content = str(changes["content"])[:60000]
    for fk in (
        "contact_id",
        "deal_id",
        "project_id",
        "messaging_chat_id",
        "goal_id",
        "vault_doc_id",
    ):
        if fk in changes:
            setattr(note, fk, changes[fk])
    note.updated_at = utcnow()
    db.commit()
    all_notes = list(db.scalars(select(NotebookNote).where(NotebookNote.user_id == user_id)).all())
    by_folded_title, backlinks_map = _graph_maps(all_notes)
    refreshed = next(n for n in all_notes if n.id == note.id)
    return _serialize_note(refreshed, by_folded_title=by_folded_title, backlinks_map=backlinks_map)


def delete_note(db: Session, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
    note = get_owned(
        db,
        NotebookNote,
        user_id,
        note_id,
        error_code="note_not_found",
        error_msg="Nota não encontrada.",
    )
    db.delete(note)
    db.commit()


def list_hub_bridges(db: Session, user: User) -> dict[str, Any]:
    return list_memory_bridges(db, user, include_notebook_extras=True)
