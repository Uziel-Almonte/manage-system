"""create stock_movement table

Revision ID: 176f84d707a0
Revises: c1fba7c68b3b
Create Date: 2026-05-14 14:25:46.283761

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '176f84d707a0'
down_revision = 'c1fba7c68b3b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stock_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('user', sa.String(length=100), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('prev_qty', sa.Integer(), nullable=False),
        sa.Column('new_qty', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('date', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('stock_movements')
