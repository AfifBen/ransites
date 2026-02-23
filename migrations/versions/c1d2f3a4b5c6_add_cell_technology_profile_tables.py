"""add cell technology profile tables

Revision ID: c1d2f3a4b5c6
Revises: a4c6e2b8d901
Create Date: 2026-02-21 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d2f3a4b5c6"
down_revision = "a4c6e2b8d901"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("cell_2g"):
        op.create_table(
            "cell_2g",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cell_id", sa.Integer(), nullable=False),
            sa.Column("bcch", sa.Integer(), nullable=True),
            sa.Column("bsic", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(["cell_id"], ["cell.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cell_id"),
        )
        op.create_index("ix_cell_2g_cell_id", "cell_2g", ["cell_id"], unique=False)

    if not inspector.has_table("cell_3g"):
        op.create_table(
            "cell_3g",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cell_id", sa.Integer(), nullable=False),
            sa.Column("psc", sa.Integer(), nullable=True),
            sa.Column("rnc", sa.String(length=80), nullable=True),
            sa.ForeignKeyConstraint(["cell_id"], ["cell.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cell_id"),
        )
        op.create_index("ix_cell_3g_cell_id", "cell_3g", ["cell_id"], unique=False)

    if not inspector.has_table("cell_4g"):
        op.create_table(
            "cell_4g",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cell_id", sa.Integer(), nullable=False),
            sa.Column("pci", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["cell_id"], ["cell.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cell_id"),
        )
        op.create_index("ix_cell_4g_cell_id", "cell_4g", ["cell_id"], unique=False)

    if not inspector.has_table("cell_5g"):
        op.create_table(
            "cell_5g",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cell_id", sa.Integer(), nullable=False),
            sa.Column("pci", sa.Integer(), nullable=True),
            sa.Column("nrarfcn", sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(["cell_id"], ["cell.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cell_id"),
        )
        op.create_index("ix_cell_5g_cell_id", "cell_5g", ["cell_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("cell_5g"):
        op.drop_index("ix_cell_5g_cell_id", table_name="cell_5g")
        op.drop_table("cell_5g")
    if inspector.has_table("cell_4g"):
        op.drop_index("ix_cell_4g_cell_id", table_name="cell_4g")
        op.drop_table("cell_4g")
    if inspector.has_table("cell_3g"):
        op.drop_index("ix_cell_3g_cell_id", table_name="cell_3g")
        op.drop_table("cell_3g")
    if inspector.has_table("cell_2g"):
        op.drop_index("ix_cell_2g_cell_id", table_name="cell_2g")
        op.drop_table("cell_2g")
