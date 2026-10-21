
import pytest

from sqlalchemy.orm import Session

from app.database import engine

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture
def db_session():
    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            # Safety check: never use our application database
            database_name = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()

            if database_name != "savannah_clinic_test":
                raise RuntimeError(
                    "Tests must run against savannah_clinic_test"
                )

            # Allow service commits without committing
            # the outer test transaction
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint"
            ) as session:
                yield session

        finally:
            # Discard everything this test inserted or changed
            if transaction.is_active:
                transaction.rollback()




@pytest.fixture
def client(db_session):

    # Replace FastAPI's normal database dependency
    # with our isolated pytest database session.
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client

    finally:
        # Restore normal dependency behavior
        # after the test finishes.
        app.dependency_overrides.clear()
