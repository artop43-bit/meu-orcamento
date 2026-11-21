"""v1.10.1: Cofre de Documentos & Garantias (`/cofre`), Caderno (`/caderno`) e cota padrão 200 MB

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vault_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False, server_default="other"),
        sa.Column("issuer", sa.String(length=140), nullable=True),
        sa.Column("document_number", sa.String(length=80), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notify_days_before", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("file_name", sa.String(length=160), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("ocr_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "deal_id",
            sa.Uuid(),
            sa.ForeignKey("crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("work_projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("commercial_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "messaging_media_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vault_documents_user_id", "vault_documents", ["user_id"])
    op.create_index("ix_vault_documents_contact_id", "vault_documents", ["contact_id"])
    op.create_index("ix_vault_documents_deal_id", "vault_documents", ["deal_id"])
    op.create_index("ix_vault_documents_project_id", "vault_documents", ["project_id"])
    op.create_index("ix_vault_documents_proposal_id", "vault_documents", ["proposal_id"])
    op.create_index(
        "ix_vault_documents_messaging_media_id", "vault_documents", ["messaging_media_id"]
    )
    op.create_index("ix_vault_documents_user_expires", "vault_documents", ["user_id", "expires_at"])
    op.create_index("ix_vault_documents_user_category", "vault_documents", ["user_id", "category"])

    op.create_table(
        "notebook_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("folder", sa.String(length=60), nullable=False, server_default="Geral"),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("template_kind", sa.String(length=24), nullable=False, server_default="blank"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "deal_id",
            sa.Uuid(),
            sa.ForeignKey("crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("work_projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "messaging_chat_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_chats.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "goal_id",
            sa.Uuid(),
            sa.ForeignKey("goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "vault_doc_id",
            sa.Uuid(),
            sa.ForeignKey("vault_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notebook_notes_user_id", "notebook_notes", ["user_id"])
    op.create_index("ix_notebook_notes_contact_id", "notebook_notes", ["contact_id"])
    op.create_index("ix_notebook_notes_deal_id", "notebook_notes", ["deal_id"])
    op.create_index("ix_notebook_notes_project_id", "notebook_notes", ["project_id"])
    op.create_index("ix_notebook_notes_messaging_chat_id", "notebook_notes", ["messaging_chat_id"])
    op.create_index("ix_notebook_notes_goal_id", "notebook_notes", ["goal_id"])
    op.create_index("ix_notebook_notes_vault_doc_id", "notebook_notes", ["vault_doc_id"])
    op.create_index(
        "ix_notebook_notes_user_pinned_upd",
        "notebook_notes",
        ["user_id", "pinned", "updated_at"],
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "storage_quota_mb",
            existing_type=sa.SmallInteger(),
            server_default="200",
            existing_nullable=False,
        )
    op.execute("UPDATE users SET storage_quota_mb = 200 WHERE storage_quota_mb = 50")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "storage_quota_mb",
            existing_type=sa.SmallInteger(),
            server_default="50",
            existing_nullable=False,
        )
    op.drop_table("notebook_notes")
    op.drop_table("vault_documents")
