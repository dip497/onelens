"""
Script to create product-related tables in the database
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models import Base
from app.core.config import settings

async def create_tables():
    # Convert sync postgres URL to async
    async_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(async_url, echo=True)
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print("Tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_tables())