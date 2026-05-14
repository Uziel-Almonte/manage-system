"""create products table

Revision ID: c1fba7c68b3b
Revises: 
Create Date: 2026-05-14 14:21:38.415076

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1fba7c68b3b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
    'products',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('sku', sa.String(length=50), nullable=False, unique=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('price', sa.Numeric(10, 2), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False, default=0),
    sa.Column('min_stock', sa.Integer(), nullable=False, default=0),
    sa.Column('status', sa.String(length=20), nullable=False, default='active')
    )


def downgrade():
    op.drop_table('products')
