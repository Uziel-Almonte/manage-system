import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:1234@db:5432/inventory_test_db"
)

@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL)
    yield eng
    eng.dispose()

@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()  # cada test aísla sus cambios, no ensucia la DB
    connection.close()