"""expand cell technology specific fields

Revision ID: d4e5f6a7b8c9
Revises: c1d2f3a4b5c6
Create Date: 2026-02-21 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c1d2f3a4b5c6"
branch_labels = None
depends_on = None


def _ensure_column(table_name, column_name, column_type):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name not in cols:
        op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))


def upgrade():
    _ensure_column("cell_2g", "bsc", sa.String(length=80))
    _ensure_column("cell_2g", "lac", sa.String(length=50))
    _ensure_column("cell_2g", "rac", sa.String(length=50))

    _ensure_column("cell_3g", "lac", sa.String(length=50))
    _ensure_column("cell_3g", "rac", sa.String(length=50))
    _ensure_column("cell_3g", "dlarfcn", sa.String(length=50))

    _ensure_column("cell_4g", "enodeb", sa.String(length=80))
    _ensure_column("cell_4g", "tac", sa.String(length=50))
    _ensure_column("cell_4g", "rsi", sa.String(length=50))
    _ensure_column("cell_4g", "earfcn", sa.String(length=50))

    _ensure_column("cell_5g", "gnodeb", sa.String(length=80))
    _ensure_column("cell_5g", "lac", sa.String(length=50))
    _ensure_column("cell_5g", "rsi", sa.String(length=50))
    _ensure_column("cell_5g", "arfcn", sa.String(length=50))

    # Backward compatibility for existing 5G profile values created in previous schema.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols_5g = {c["name"] for c in inspector.get_columns("cell_5g")}
    if "nrarfcn" in cols_5g and "arfcn" in cols_5g:
        op.execute("UPDATE cell_5g SET arfcn = nrarfcn WHERE (arfcn IS NULL OR TRIM(arfcn) = '') AND nrarfcn IS NOT NULL")


def downgrade():
    # Keep downgrade conservative: removing columns may fail on some SQLite builds.
    pass
