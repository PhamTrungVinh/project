import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from database import Base, get_db
import database
from main import app
from models.user import User
from schemas.user import UserCreate
from crud.users import create_user
from utils.security import create_access_token


# In-memory SQLite for testing with StaticPool so all connections share the same in-memory DB
TEST_DATABASE_URL = "sqlite:///:memory:"

engine_test = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def init_db_per_test():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session():
    """Provides a database session for unit tests."""
    session = TestingSessionLocal()

    # Patch SessionLocal in database module so tools using get_db_session() hit this DB
    orig_session_local = database.SessionLocal
    database.SessionLocal = TestingSessionLocal

    yield session

    database.SessionLocal = orig_session_local
    session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session) -> User:
    """Creates a standard test user."""
    user_data = UserCreate(
        email="testuser@example.com",
        password="TestPassword123!",
        full_name="Test User",
    )
    return create_user(db_session, user_data)


@pytest.fixture
def test_user_2(db_session) -> User:
    """Creates a second test user to test user isolation."""
    user_data = UserCreate(
        email="otheruser@example.com",
        password="OtherPassword123!",
        full_name="Other User",
    )
    return create_user(db_session, user_data)


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Returns Authorization header with Bearer token for test_user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_2(test_user_2: User) -> dict[str, str]:
    """Returns Authorization header with Bearer token for test_user_2."""
    token = create_access_token(data={"sub": str(test_user_2.id)})
    return {"Authorization": f"Bearer {token}"}
