"""add ci to cell2g/3g/5g

Revision ID: f2c4d6e8a1b3
Revises: e7a1b2c3d4e5
Create Date: 2026-02-26 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2c4d6e8a1b3"
down_revision = "e7a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cell_2g", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ci", sa.Integer(), nullable=True))

    with op.batch_alter_table("cell_3g", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ci", sa.Integer(), nullable=True))

    with op.batch_alter_table("cell_5g", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ci", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("cell_5g", schema=None) as batch_op:
        batch_op.drop_column("ci")

    with op.batch_alter_table("cell_3g", schema=None) as batch_op:
        batch_op.drop_column("ci")

    with op.batch_alter_table("cell_2g", schema=None) as batch_op:
        batch_op.drop_column("ci")
