"""add user region scope table

Revision ID: a9d3c5e7f1b2
Revises: f2c4d6e8a1b3
Create Date: 2026-02-28 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9d3c5e7f1b2"
down_revision = "f2c4d6e8a1b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_region",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "region_id"),
    )


def downgrade():
    op.drop_table("user_region")

