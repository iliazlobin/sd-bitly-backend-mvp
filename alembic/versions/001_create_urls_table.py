"""create urls table

Revision ID: 001
Revises:
Create Date: 2026-06-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "urls",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("short_code", sa.String(20), unique=True, nullable=False),
        sa.Column("long_url", sa.Text, nullable=False),
        sa.Column("clicks", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_urls_short_code", "urls", ["short_code"])


def downgrade() -> None:
    op.drop_index("idx_urls_short_code", table_name="urls")
    op.drop_table("urls")
