"""add ci to cell4g

Revision ID: e7a1b2c3d4e5
Revises: d4e5f6a7b8c9
Create Date: 2026-02-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7a1b2c3d4e5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cell_4g", sa.Column("ci", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("cell_4g", "ci")
