import pytest
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.products.models import Product


def make_product(sku, name="Producto de prueba", price="10.00", qty=5):
    return Product(
        name=name,
        sku=sku,
        price=price,
        qty=qty,
        min_stock=0,
        status="active",
    )


def test_duplicate_sku_is_rejected(app):
    with app.app_context():
        db.session.add(make_product(sku="ABC-123"))
        db.session.flush()

        db.session.add(make_product(sku="ABC-123", name="Otro producto"))

        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_different_skus_are_allowed(app):
    with app.app_context():
        db.session.add(make_product(sku="ABC-123"))
        db.session.add(make_product(sku="ABC-124"))
        db.session.flush()
        db.session.rollback()


def test_sku_is_case_sensitive_by_default(app):
    """
    SQLite/Postgres distinguen mayúsculas en el SKU por defecto.
  """
    with app.app_context():
        db.session.add(make_product(sku="ABC-123"))
        db.session.add(make_product(sku="abc-123"))
        db.session.flush()
        db.session.rollback()


def test_sku_cannot_be_null(app):
    with app.app_context():
        product = Product(
            name="Producto sin SKU",
            sku=None,
            price="10.00",
            qty=5,
            min_stock=0,
            status="active",
        )
        db.session.add(product)

        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
