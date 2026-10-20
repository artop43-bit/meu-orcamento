"""v0.8: avisos por e-mail, metas com objetivo, importação em lotes e comprovantes

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-22

Contas que já existem não veem a configuração inicial guiada (onboarded_at preenchido) e metas
já alcançadas ficam marcadas como concluídas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("notify_due", sa.Boolean(), nullable=False, server_default="1"))
        batch.add_column(
            sa.Column("notify_due_days", sa.SmallInteger(), nullable=False, server_default="3")
        )
        batch.add_column(
            sa.Column("notify_hide_values", sa.Boolean(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("notify_monthly", sa.Boolean(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET onboarded_at = created_at")

    op.create_table(
        "known_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_known_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_known_devices")),
        sa.UniqueConstraint("user_id", "fingerprint", name=op.f("uq_known_devices_user_id")),
    )
    op.create_index(op.f("ix_known_devices_user_id"), "known_devices", ["user_id"])

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("ref", sa.String(length=40), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_log_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_log")),
        sa.UniqueConstraint("user_id", "kind", "ref", name=op.f("uq_notification_log_user_id")),
    )
    op.create_index(op.f("ix_notification_log_user_id"), "notification_log", ["user_id"])

    with op.batch_alter_table("goals") as batch:
        batch.add_column(
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="other")
        )
        batch.add_column(sa.Column("motivation", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("monthly_plan", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("is_main", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE goals SET completed_at = updated_at "
        "WHERE target_amount > 0 AND current_amount >= target_amount"
    )

    op.create_table(
        "goal_contributions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name=op.f("fk_goal_contributions_goal_id_goals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goal_contributions")),
    )
    op.create_index(op.f("ix_goal_contributions_goal_id"), "goal_contributions", ["goal_id"])

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=160), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_import_batches_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(op.f("ix_import_batches_user_id"), "import_batches", ["user_id"])

    op.create_table(
        "import_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("mapping", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_import_mappings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_mappings")),
        sa.UniqueConstraint("user_id", "signature", name=op.f("uq_import_mappings_user_id")),
    )
    op.create_index(op.f("ix_import_mappings_user_id"), "import_mappings", ["user_id"])

    for table in ("incomes", "expenses"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("import_batch_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                op.f(f"fk_{table}_import_batch_id_import_batches"),
                "import_batches",
                ["import_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index(op.f(f"ix_{table}_import_batch_id"), ["import_batch_id"])

    with op.batch_alter_table("stored_files") as batch:
        batch.add_column(sa.Column("expense_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("goal_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_stored_files_expense_id_expenses"),
            "expenses",
            ["expense_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            op.f("fk_stored_files_goal_id_goals"), "goals", ["goal_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index(op.f("ix_stored_files_expense_id"), ["expense_id"])
        batch.create_index(op.f("ix_stored_files_goal_id"), ["goal_id"])


def downgrade() -> None:
    op.execute("DELETE FROM stored_files WHERE purpose IN ('receipt', 'goal')")
    with op.batch_alter_table("stored_files") as batch:
        batch.drop_index(op.f("ix_stored_files_goal_id"))
        batch.drop_index(op.f("ix_stored_files_expense_id"))
        batch.drop_constraint(op.f("fk_stored_files_goal_id_goals"), type_="foreignkey")
        batch.drop_constraint(op.f("fk_stored_files_expense_id_expenses"), type_="foreignkey")
        batch.drop_column("goal_id")
        batch.drop_column("expense_id")
    for table in ("expenses", "incomes"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(op.f(f"ix_{table}_import_batch_id"))
            batch.drop_constraint(
                op.f(f"fk_{table}_import_batch_id_import_batches"), type_="foreignkey"
            )
            batch.drop_column("import_batch_id")
    op.drop_index(op.f("ix_import_mappings_user_id"), table_name="import_mappings")
    op.drop_table("import_mappings")
    op.drop_index(op.f("ix_import_batches_user_id"), table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_index(op.f("ix_goal_contributions_goal_id"), table_name="goal_contributions")
    op.drop_table("goal_contributions")
    with op.batch_alter_table("goals") as batch:
        batch.drop_column("completed_at")
        batch.drop_column("is_main")
        batch.drop_column("monthly_plan")
        batch.drop_column("motivation")
        batch.drop_column("kind")
    op.drop_index(op.f("ix_notification_log_user_id"), table_name="notification_log")
    op.drop_table("notification_log")
    op.drop_index(op.f("ix_known_devices_user_id"), table_name="known_devices")
    op.drop_table("known_devices")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("onboarded_at")
        batch.drop_column("notify_monthly")
        batch.drop_column("notify_hide_values")
        batch.drop_column("notify_due_days")
        batch.drop_column("notify_due")
