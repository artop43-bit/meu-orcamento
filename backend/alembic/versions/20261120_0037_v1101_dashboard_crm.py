"""v1.10.1: Solução Dashboard & CRM (funis, contatos, negócios, fontes de dados e painéis)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_pipelines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_crm_pipelines_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_pipelines"),
    )
    op.create_index("ix_crm_pipelines_user_id", "crm_pipelines", ["user_id"], unique=False)

    op.create_table(
        "crm_stages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("is_won", sa.Boolean(), nullable=False),
        sa.Column("is_lost", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["crm_pipelines.id"],
            name="fk_crm_stages_pipeline_id_crm_pipelines",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_stages"),
    )
    op.create_index("ix_crm_stages_pipeline_id", "crm_stages", ["pipeline_id"], unique=False)
    op.create_index(
        "ix_crm_stages_pipeline_pos", "crm_stages", ["pipeline_id", "position"], unique=False
    )

    op.create_table(
        "crm_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("remote_jid", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("company", sa.String(length=120), nullable=True),
        sa.Column("origin", sa.String(length=60), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("messaging_chat_id", sa.Uuid(), nullable=True),
        sa.Column("budget_person", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_crm_contacts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["messaging_chat_id"],
            ["messaging_chats.id"],
            name="fk_crm_contacts_messaging_chat_id_messaging_chats",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_contacts"),
    )
    op.create_index("ix_crm_contacts_user_id", "crm_contacts", ["user_id"], unique=False)
    op.create_index("ix_crm_contacts_remote_jid", "crm_contacts", ["remote_jid"], unique=False)
    op.create_index(
        "ix_crm_contacts_messaging_chat_id", "crm_contacts", ["messaging_chat_id"], unique=False
    )
    op.create_index("ix_crm_contacts_user_name", "crm_contacts", ["user_id", "name"], unique=False)

    op.create_table(
        "crm_deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("budget_income_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_crm_deals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["crm_pipelines.id"],
            name="fk_crm_deals_pipeline_id_crm_pipelines",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["crm_stages.id"],
            name="fk_crm_deals_stage_id_crm_stages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["crm_contacts.id"],
            name="fk_crm_deals_contact_id_crm_contacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["budget_income_id"],
            ["incomes.id"],
            name="fk_crm_deals_budget_income_id_incomes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_deals"),
    )
    op.create_index("ix_crm_deals_user_id", "crm_deals", ["user_id"], unique=False)
    op.create_index("ix_crm_deals_pipeline_id", "crm_deals", ["pipeline_id"], unique=False)
    op.create_index("ix_crm_deals_stage_id", "crm_deals", ["stage_id"], unique=False)
    op.create_index("ix_crm_deals_contact_id", "crm_deals", ["contact_id"], unique=False)
    op.create_index(
        "ix_crm_deals_budget_income_id", "crm_deals", ["budget_income_id"], unique=False
    )
    op.create_index("ix_crm_deals_user_stage", "crm_deals", ["user_id", "stage_id"], unique=False)

    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_crm_activities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["crm_contacts.id"],
            name="fk_crm_activities_contact_id_crm_contacts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["crm_deals.id"],
            name="fk_crm_activities_deal_id_crm_deals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_activities"),
    )
    op.create_index("ix_crm_activities_user_id", "crm_activities", ["user_id"], unique=False)
    op.create_index("ix_crm_activities_contact_id", "crm_activities", ["contact_id"], unique=False)
    op.create_index("ix_crm_activities_deal_id", "crm_activities", ["deal_id"], unique=False)
    op.create_index(
        "ix_crm_activities_user_created",
        "crm_activities",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("refresh_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("sync_failures", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_data_sources_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_sources"),
    )
    op.create_index("ix_data_sources_user_id", "data_sources", ["user_id"], unique=False)
    op.create_index("ix_data_sources_user_kind", "data_sources", ["user_id", "kind"], unique=False)

    op.create_table(
        "data_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name="fk_data_snapshots_source_id_data_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_snapshots"),
    )
    op.create_index("ix_data_snapshots_source_id", "data_snapshots", ["source_id"], unique=False)
    op.create_index(
        "ix_data_snapshots_source_created",
        "data_snapshots",
        ["source_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "crm_dashboards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=240), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("default_range", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_crm_dashboards_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_dashboards"),
    )
    op.create_index("ix_crm_dashboards_user_id", "crm_dashboards", ["user_id"], unique=False)

    op.create_table(
        "crm_widgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dashboard_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("widget_type", sa.String(length=16), nullable=False),
        sa.Column("span", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("query_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dashboard_id"],
            ["crm_dashboards.id"],
            name="fk_crm_widgets_dashboard_id_crm_dashboards",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name="fk_crm_widgets_source_id_data_sources",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_widgets"),
    )
    op.create_index("ix_crm_widgets_dashboard_id", "crm_widgets", ["dashboard_id"], unique=False)
    op.create_index("ix_crm_widgets_source_id", "crm_widgets", ["source_id"], unique=False)
    op.create_index(
        "ix_crm_widgets_dashboard_pos",
        "crm_widgets",
        ["dashboard_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_widgets_dashboard_pos", table_name="crm_widgets")
    op.drop_index("ix_crm_widgets_source_id", table_name="crm_widgets")
    op.drop_index("ix_crm_widgets_dashboard_id", table_name="crm_widgets")
    op.drop_table("crm_widgets")

    op.drop_index("ix_crm_dashboards_user_id", table_name="crm_dashboards")
    op.drop_table("crm_dashboards")

    op.drop_index("ix_data_snapshots_source_created", table_name="data_snapshots")
    op.drop_index("ix_data_snapshots_source_id", table_name="data_snapshots")
    op.drop_table("data_snapshots")

    op.drop_index("ix_data_sources_user_kind", table_name="data_sources")
    op.drop_index("ix_data_sources_user_id", table_name="data_sources")
    op.drop_table("data_sources")

    op.drop_index("ix_crm_activities_user_created", table_name="crm_activities")
    op.drop_index("ix_crm_activities_deal_id", table_name="crm_activities")
    op.drop_index("ix_crm_activities_contact_id", table_name="crm_activities")
    op.drop_index("ix_crm_activities_user_id", table_name="crm_activities")
    op.drop_table("crm_activities")

    op.drop_index("ix_crm_deals_user_stage", table_name="crm_deals")
    op.drop_index("ix_crm_deals_budget_income_id", table_name="crm_deals")
    op.drop_index("ix_crm_deals_contact_id", table_name="crm_deals")
    op.drop_index("ix_crm_deals_stage_id", table_name="crm_deals")
    op.drop_index("ix_crm_deals_pipeline_id", table_name="crm_deals")
    op.drop_index("ix_crm_deals_user_id", table_name="crm_deals")
    op.drop_table("crm_deals")

    op.drop_index("ix_crm_contacts_user_name", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_messaging_chat_id", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_remote_jid", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_user_id", table_name="crm_contacts")
    op.drop_table("crm_contacts")

    op.drop_index("ix_crm_stages_pipeline_pos", table_name="crm_stages")
    op.drop_index("ix_crm_stages_pipeline_id", table_name="crm_stages")
    op.drop_table("crm_stages")

    op.drop_index("ix_crm_pipelines_user_id", table_name="crm_pipelines")
    op.drop_table("crm_pipelines")
