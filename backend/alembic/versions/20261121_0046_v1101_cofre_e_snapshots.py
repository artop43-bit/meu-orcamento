"""v1.10.1: Índices únicos parciais no Cofre (duplo clique) e size_bytes em data_snapshots

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-21
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _delete_vault_duplicates(bind: sa.Connection, column: str) -> None:
    dup_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                f"""
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY user_id, {column}
                               ORDER BY created_at ASC, id ASC
                           ) AS rn
                    FROM vault_documents
                    WHERE {column} IS NOT NULL
                ) ranked
                WHERE rn > 1
                """
            )
        ).fetchall()
    ]
    for dup_id in dup_ids:
        bind.execute(
            sa.text("UPDATE notebook_notes SET vault_doc_id = NULL WHERE vault_doc_id = :doc_id"),
            {"doc_id": dup_id},
        )
        bind.execute(
            sa.text("DELETE FROM vault_documents WHERE id = :doc_id"),
            {"doc_id": dup_id},
        )


def upgrade() -> None:
    bind = op.get_bind()

    # R5: remove duplicatas antigas mantendo o registro mais antigo antes dos índices únicos.
    _delete_vault_duplicates(bind, "messaging_media_id")
    _delete_vault_duplicates(bind, "proposal_id")

    op.create_index(
        "uq_vault_documents_user_messaging_media",
        "vault_documents",
        ["user_id", "messaging_media_id"],
        unique=True,
        sqlite_where=sa.text("messaging_media_id IS NOT NULL"),
        postgresql_where=sa.text("messaging_media_id IS NOT NULL"),
    )
    op.create_index(
        "uq_vault_documents_user_proposal",
        "vault_documents",
        ["user_id", "proposal_id"],
        unique=True,
        sqlite_where=sa.text("proposal_id IS NOT NULL"),
        postgresql_where=sa.text("proposal_id IS NOT NULL"),
    )

    # R13: guarda o tamanho do snapshot em bytes para medir cota sem ler rows_json.
    op.add_column(
        "data_snapshots",
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    rows = bind.execute(sa.text("SELECT id, rows_json FROM data_snapshots")).fetchall()
    for snap_id, raw_rows in rows:
        if isinstance(raw_rows, str):
            parsed = json.loads(raw_rows) if raw_rows else []
        else:
            parsed = raw_rows or []
        size_bytes = len(json.dumps(parsed, ensure_ascii=False, default=str).encode("utf-8"))
        bind.execute(
            sa.text("UPDATE data_snapshots SET size_bytes = :size_bytes WHERE id = :id"),
            {"size_bytes": size_bytes, "id": snap_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("data_snapshots") as batch_op:
        batch_op.drop_column("size_bytes")

    op.drop_index("uq_vault_documents_user_proposal", table_name="vault_documents")
    op.drop_index("uq_vault_documents_user_messaging_media", table_name="vault_documents")
