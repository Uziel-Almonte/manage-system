"""add cascade delete on stock_movements product_id fk

Revision ID: a3f9c2d1e4b5
Revises: b76fc13a9c4a
Branch Labels: None
Depends On: None

"""
from alembic import op

revision = 'a3f9c2d1e4b5'
down_revision = 'b76fc13a9c4a'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('stock_movements_product_id_fkey', 'stock_movements', type_='foreignkey')
    op.create_foreign_key(
        'stock_movements_product_id_fkey',
        'stock_movements', 'products',
        ['product_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    op.drop_constraint('stock_movements_product_id_fkey', 'stock_movements', type_='foreignkey')
    op.create_foreign_key(
        'stock_movements_product_id_fkey',
        'stock_movements', 'products',
        ['product_id'], ['id']
    )
