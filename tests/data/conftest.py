import os

import pytest
from sqlalchemy import create_engine

POSTGRES_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:password@db:5432/inventory_db"),
)


@pytest.fixture(scope="session")
def postgres_engine():
    if "postgresql" not in POSTGRES_URL:
        pytest.skip("Postgres DATABASE_URL required for migration integration tests")
    engine = create_engine(POSTGRES_URL)
    yield engine
    engine.dispose()
