import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.core.database import get_db
from app.models import Base, Epic, Feature
from app.models.enums import EpicStatus


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session"""
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database session override"""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def test_epic(db_session: AsyncSession) -> Epic:
    """Create a test epic"""
    epic = Epic(
        title="Test Epic",
        description="Test epic description",
        status=EpicStatus.DRAFT
    )
    db_session.add(epic)
    await db_session.commit()
    await db_session.refresh(epic)
    return epic


@pytest.fixture
async def test_feature(db_session: AsyncSession, test_epic: Epic) -> Feature:
    """Create a test feature"""
    feature = Feature(
        title="Test Feature",
        description="Test feature description",
        epic_id=test_epic.id,
        normalized_text="test feature test feature description"
    )
    db_session.add(feature)
    await db_session.commit()
    await db_session.refresh(feature)
    return feature


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock application settings for testing"""
    monkeypatch.setenv("AGNO_SERVICE_URL", "http://test-agno:8080")
    monkeypatch.setenv("AGNO_API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)