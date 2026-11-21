"""v1.10.1: Mensageria com mídias, fotos de perfil e prioridade de nome de contato

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Mídias recebidas e enviadas (fotos, áudios, vídeos, figurinhas e documentos; 7 dias).
    op.create_table(
        "messaging_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messaging_media_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messaging_media"),
    )
    op.create_index("ix_messaging_media_user_id", "messaging_media", ["user_id"], unique=False)
    op.create_index(
        "ix_messaging_media_user_created",
        "messaging_media",
        ["user_id", "created_at"],
        unique=False,
    )

    # Conversas: origem do nome (agenda > apelido > genérico) e foto de perfil do contato.
    with op.batch_alter_table("messaging_chats") as batch:
        batch.add_column(
            sa.Column(
                "name_source",
                sa.String(length=16),
                nullable=False,
                server_default="fallback",
            )
        )
        batch.add_column(sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("avatar_mime", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True))

    # Mensagens: vínculo opcional com o arquivo de mídia.
    with op.batch_alter_table("messaging_messages") as batch:
        batch.add_column(sa.Column("media_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_messaging_messages_media_id_messaging_media",
            "messaging_media",
            ["media_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_messaging_messages_media_id", "messaging_messages", ["media_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_messaging_messages_media_id", table_name="messaging_messages")
    with op.batch_alter_table("messaging_messages") as batch:
        batch.drop_constraint("fk_messaging_messages_media_id_messaging_media", type_="foreignkey")
        batch.drop_column("media_id")

    with op.batch_alter_table("messaging_chats") as batch:
        batch.drop_column("avatar_updated_at")
        batch.drop_column("avatar_mime")
        batch.drop_column("avatar_data")
        batch.drop_column("name_source")

    op.drop_index("ix_messaging_media_user_created", table_name="messaging_media")
    op.drop_index("ix_messaging_media_user_id", table_name="messaging_media")
    op.drop_table("messaging_media")
