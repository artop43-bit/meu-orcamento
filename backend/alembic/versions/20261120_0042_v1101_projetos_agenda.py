"""v1.10.1: Projetos & Tarefas (com apontamento de horas) e Agenda & Compromissos

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planning"),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "crm_deal_id",
            sa.Uuid(),
            sa.ForeignKey("crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("commercial_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "budget_project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("budget_value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_work_projects_user_id", "work_projects", ["user_id"])
    op.create_index("ix_work_projects_contact_id", "work_projects", ["contact_id"])
    op.create_index("ix_work_projects_crm_deal_id", "work_projects", ["crm_deal_id"])
    op.create_index("ix_work_projects_proposal_id", "work_projects", ["proposal_id"])
    op.create_index("ix_work_projects_budget_project_id", "work_projects", ["budget_project_id"])
    op.create_index("ix_work_projects_user_status", "work_projects", ["user_id", "status"])

    op.create_table(
        "project_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("work_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(length=12), nullable=False, server_default="medium"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("checklist_json", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "source_chat_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_chats.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_tasks_user_id", "project_tasks", ["user_id"])
    op.create_index("ix_project_tasks_project_id", "project_tasks", ["project_id"])
    op.create_index("ix_project_tasks_due_date", "project_tasks", ["due_date"])
    op.create_index("ix_project_tasks_source_chat_id", "project_tasks", ["source_chat_id"])
    op.create_index("ix_project_tasks_source_message_id", "project_tasks", ["source_message_id"])
    op.create_index("ix_project_tasks_project_status", "project_tasks", ["project_id", "status"])

    op.create_table(
        "project_time_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("work_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("project_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_time_entries_user_id", "project_time_entries", ["user_id"])
    op.create_index("ix_project_time_entries_project_id", "project_time_entries", ["project_id"])
    op.create_index("ix_project_time_entries_task_id", "project_time_entries", ["task_id"])

    op.create_table(
        "agenda_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="meeting"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("location", sa.String(length=180), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("crm_contacts.id", ondelete="SET NULL"),
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
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agenda_events_user_id", "agenda_events", ["user_id"])
    op.create_index("ix_agenda_events_start_at", "agenda_events", ["start_at"])
    op.create_index("ix_agenda_events_contact_id", "agenda_events", ["contact_id"])
    op.create_index("ix_agenda_events_project_id", "agenda_events", ["project_id"])
    op.create_index("ix_agenda_events_messaging_chat_id", "agenda_events", ["messaging_chat_id"])
    op.create_index("ix_agenda_events_user_start", "agenda_events", ["user_id", "start_at"])


def downgrade() -> None:
    op.drop_table("agenda_events")
    op.drop_table("project_time_entries")
    op.drop_table("project_tasks")
    op.drop_table("work_projects")
