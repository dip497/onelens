from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from app.core.config import settings
from app.core.database import engine
from app.models import Base

# Import routers
from app.api.v1 import epics, features, agent, debug

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up Epic Analysis System...")
    # Create database tables if they don't exist
    # Note: In production, use Alembic migrations instead
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Shutdown
    print("Shutting down...")
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(epics.router, prefix=f"{settings.API_PREFIX}/epics", tags=["epics"])
app.include_router(features.router, prefix=f"{settings.API_PREFIX}/features", tags=["features"])
app.include_router(agent.router, prefix=f"{settings.API_PREFIX}", tags=["agent"])
app.include_router(debug.router, prefix=f"{settings.API_PREFIX}/debug", tags=["debug"])
# app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])
# app.include_router(customers.router, prefix=f"{settings.API_PREFIX}/customers", tags=["customers"])
# app.include_router(competitors.router, prefix=f"{settings.API_PREFIX}/competitors", tags=["competitors"])
# app.include_router(analysis.router, prefix=f"{settings.API_PREFIX}/analysis", tags=["analysis"])

@app.get("/")
async def root():
    return {
        "message": "Epic Analysis System API",
        "version": settings.VERSION,
        "docs": f"{settings.API_PREFIX}/docs"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENV,
        "version": settings.VERSION
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
