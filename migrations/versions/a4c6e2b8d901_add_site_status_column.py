"""add site status column

Revision ID: a4c6e2b8d901
Revises: 9b7e2d4a6c10
Create Date: 2026-02-21 14:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4c6e2b8d901"
down_revision = "9b7e2d4a6c10"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    site_columns = {col["name"] for col in inspector.get_columns("site")}

    if "status" not in site_columns:
        op.add_column(
            "site",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="On air"),
        )

    op.execute("UPDATE site SET status = 'On air' WHERE status IS NULL OR TRIM(status) = ''")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    site_columns = {col["name"] for col in inspector.get_columns("site")}
    if "status" in site_columns:
        op.drop_column("site", "status")
