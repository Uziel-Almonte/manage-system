import pytest
from sqlalchemy.exc import IntegrityError
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


def test_duplicate_sku_is_rejected(db_session):
    db_session.add(make_product(sku="ABC-123"))
    db_session.flush()  # envía el INSERT a Postgres sin hacer commit todavía

    db_session.add(make_product(sku="ABC-123", name="Otro producto"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_different_skus_are_allowed(db_session):
    db_session.add(make_product(sku="ABC-123"))
    db_session.add(make_product(sku="ABC-124"))
    db_session.flush()  # no debe lanzar error


def test_sku_is_case_sensitive_by_default(db_session):
    """
    Documenta el comportamiento ACTUAL del constraint: Postgres distingue
    mayúsculas/minúsculas, así que 'ABC-123' y 'abc-123' se consideran
    SKUs distintos. Si el negocio espera que sean el mismo SKU, este test
    debería fallar y es una señal de que falta un índice case-insensitive.
    """
    db_session.add(make_product(sku="ABC-123"))
    db_session.add(make_product(sku="abc-123"))
    db_session.flush()  # actualmente NO lanza error


def test_sku_cannot_be_null(db_session):
    product = Product(
        name="Producto sin SKU",
        sku=None,
        price="10.00",
        qty=5,
        min_stock=0,
        status="active",
    )
    db_session.add(product)

    with pytest.raises(IntegrityError):
        db_session.flush()