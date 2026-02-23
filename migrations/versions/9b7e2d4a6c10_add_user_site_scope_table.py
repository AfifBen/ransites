"""add user site scope table

Revision ID: 9b7e2d4a6c10
Revises: 8a2e9c4d1f55
Create Date: 2026-02-21 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b7e2d4a6c10"
down_revision = "8a2e9c4d1f55"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user_site"):
        op.create_table(
            "user_site",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "site_id"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_site"):
        op.drop_table("user_site")
