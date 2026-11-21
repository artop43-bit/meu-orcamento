"""v1.10.1: Mensageria com o conector do WhatsApp (credenciais no banco, fila e sincronização)

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_sessions = sa.table("messaging_sessions", sa.column("status"))
_chats = sa.table(
    "messaging_chats", sa.column("remote_jid"), sa.column("phone"), sa.column("lid_jid")
)
_messages = sa.table("messaging_messages", sa.column("created_at"), sa.column("updated_at"))


def upgrade() -> None:
    # Sessão: sai a chave do conector antigo (whatsapp-web.js); entra o pedido de conexão.
    op.drop_index("ix_messaging_sessions_bridge_token_hash", table_name="messaging_sessions")
    with op.batch_alter_table("messaging_sessions") as batch:
        batch.drop_column("bridge_token_hash")
        batch.drop_column("bridge_token_prefix")
        batch.add_column(sa.Column("wanted", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("wa_jid", sa.String(length=64), nullable=True))
    op.execute(
        _sessions.update().where(_sessions.c.status == "authenticated").values(status="connecting")
    )

    # Conversas: o número pode ficar vazio (contato só com LID) e o LID ganha coluna própria.
    with op.batch_alter_table("messaging_chats") as batch:
        batch.alter_column("phone", existing_type=sa.String(length=32), nullable=True)
        batch.add_column(sa.Column("lid_jid", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_messaging_chats_user_lid", "messaging_chats", ["user_id", "lid_jid"], unique=False
    )
    op.execute(
        _chats.update()
        .where(_chats.c.remote_jid.like("%@c.us"))
        .values(remote_jid=sa.func.replace(_chats.c.remote_jid, "@c.us", "@s.whatsapp.net"))
    )
    # Antes, conversa com LID guardava os dígitos do LID como se fossem o número.
    op.execute(
        _chats.update()
        .where(_chats.c.remote_jid.like("%@lid"))
        .values(lid_jid=_chats.c.remote_jid, phone=None)
    )

    # Mensagens: data da última alteração (sincronização da tela), reserva da fila e
    # deduplicação garantida pelo banco.
    op.drop_index("ix_messaging_messages_user_external", table_name="messaging_messages")
    with op.batch_alter_table("messaging_messages") as batch:
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(_messages.update().values(updated_at=_messages.c.created_at))
    with op.batch_alter_table("messaging_messages") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_unique_constraint(
            "uq_messaging_messages_user_external", ["user_id", "external_id"]
        )
    op.create_index(
        "ix_messaging_messages_chat_updated",
        "messaging_messages",
        ["chat_id", "updated_at"],
        unique=False,
    )

    # Credenciais do WhatsApp de cada sessão (o conector lê e grava direto).
    op.create_table(
        "messaging_auth_keys",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["messaging_sessions.id"],
            name="fk_messaging_auth_keys_session_id_messaging_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", "category", "key_id", name="pk_messaging_auth_keys"),
    )

    # Valores soltos do conector (ex.: última versão do WhatsApp Web que funcionou).
    op.create_table(
        "messaging_connector_kv",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_messaging_connector_kv"),
    )


def downgrade() -> None:
    op.drop_table("messaging_connector_kv")
    op.drop_table("messaging_auth_keys")

    op.drop_index("ix_messaging_messages_chat_updated", table_name="messaging_messages")
    with op.batch_alter_table("messaging_messages") as batch:
        batch.drop_constraint("uq_messaging_messages_user_external", type_="unique")
        batch.drop_column("claimed_at")
        batch.drop_column("updated_at")
    op.create_index(
        "ix_messaging_messages_user_external",
        "messaging_messages",
        ["user_id", "external_id"],
        unique=False,
    )

    op.drop_index("ix_messaging_chats_user_lid", table_name="messaging_chats")
    op.execute(
        _chats.update()
        .where(_chats.c.remote_jid.like("%@s.whatsapp.net"))
        .values(remote_jid=sa.func.replace(_chats.c.remote_jid, "@s.whatsapp.net", "@c.us"))
    )
    op.execute(
        _chats.update()
        .where(_chats.c.phone.is_(None), _chats.c.remote_jid.like("%@lid"))
        .values(phone=sa.func.replace(_chats.c.remote_jid, "@lid", ""))
    )
    op.execute(_chats.update().where(_chats.c.phone.is_(None)).values(phone=""))
    with op.batch_alter_table("messaging_chats") as batch:
        batch.drop_column("lid_jid")
        batch.alter_column("phone", existing_type=sa.String(length=32), nullable=False)

    op.execute(
        _sessions.update().where(_sessions.c.status == "connecting").values(status="authenticated")
    )
    with op.batch_alter_table("messaging_sessions") as batch:
        batch.drop_column("wa_jid")
        batch.drop_column("wanted")
        batch.add_column(sa.Column("bridge_token_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("bridge_token_prefix", sa.String(length=12), nullable=True))
    op.create_index(
        "ix_messaging_sessions_bridge_token_hash",
        "messaging_sessions",
        ["bridge_token_hash"],
        unique=False,
    )
