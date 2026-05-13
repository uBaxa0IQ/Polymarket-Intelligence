"""add bet source enum with copytrading

Revision ID: 0021_bet_source_copytrading
Revises: 0020
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_bet_source_copytrading"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bet_source = sa.Enum("pipeline", "copytrading", name="bet_source")
    bet_source.create(bind, checkfirst=True)
    op.add_column(
        "bets",
        sa.Column("source", bet_source, nullable=False, server_default="pipeline"),
    )
    op.execute("UPDATE bets SET source = 'pipeline' WHERE source IS NULL")
    op.alter_column("bets", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("bets", "source")
    bind = op.get_bind()
    sa.Enum("pipeline", "copytrading", name="bet_source").drop(bind, checkfirst=True)
