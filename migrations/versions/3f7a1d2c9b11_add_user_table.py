"""add user table

Revision ID: 3f7a1d2c9b11
Revises: b3ff89837011
Create Date: 2026-02-19 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3f7a1d2c9b11"
down_revision = "b3ff89837011"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user"):
        op.create_table(
            "user",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=80), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {idx["name"] for idx in inspector.get_indexes("user")}
    ix_name = op.f("ix_user_username")
    if ix_name not in index_names:
        op.create_index(ix_name, "user", ["username"], unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("user"):
        index_names = {idx["name"] for idx in inspector.get_indexes("user")}
        ix_name = op.f("ix_user_username")
        if ix_name in index_names:
            op.drop_index(ix_name, table_name="user")
        op.drop_table("user")
