"""add user scope tables

Revision ID: 8a2e9c4d1f55
Revises: 3f7a1d2c9b11
Create Date: 2026-02-20 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8a2e9c4d1f55"
down_revision = "3f7a1d2c9b11"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {col["name"] for col in inspector.get_columns("user")}
    if "is_admin" not in user_columns:
        op.add_column(
            "user",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if not inspector.has_table("user_wilaya"):
        op.create_table(
            "user_wilaya",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("wilaya_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["wilaya_id"], ["wilaya.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "wilaya_id"),
        )

    if not inspector.has_table("user_commune"):
        op.create_table(
            "user_commune",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("commune_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["commune_id"], ["commune.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "commune_id"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("user_commune"):
        op.drop_table("user_commune")
    if inspector.has_table("user_wilaya"):
        op.drop_table("user_wilaya")

    user_columns = {col["name"] for col in inspector.get_columns("user")}
    if "is_admin" in user_columns:
        op.drop_column("user", "is_admin")
