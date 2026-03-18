"""add road table

Revision ID: aed866d38d4a
Revises: a9d3c5e7f1b2
Create Date: 2026-03-17 13:45:18.426360

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aed866d38d4a'
down_revision = 'a9d3c5e7f1b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('road',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=True),
    sa.Column('name', sa.String(length=180), nullable=False),
    sa.Column('geometry_geojson', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('road', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_road_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_road_name'), ['name'], unique=False)


def downgrade():
    with op.batch_alter_table('road', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_road_name'))
        batch_op.drop_index(batch_op.f('ix_road_code'))

    op.drop_table('road')
