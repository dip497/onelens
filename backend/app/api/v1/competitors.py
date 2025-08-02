from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Competitor, CompetitorFeature
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorUpdate,
    CompetitorResponse,
    CompetitorFeatureResponse
)
from app.services.competitor_intelligence import CompetitorIntelligenceService

router = APIRouter()


@router.get("/", response_model=List[CompetitorResponse])
async def list_competitors(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all competitors"""
    result = await db.execute(
        select(Competitor)
        .options(selectinload(Competitor.features))
        .offset(skip)
        .limit(limit)
    )
    competitors = result.scalars().all()
    return competitors


@router.post("/", response_model=CompetitorResponse, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    competitor_data: CompetitorCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new competitor"""
    competitor = Competitor(**competitor_data.model_dump())
    db.add(competitor)
    await db.commit()
    await db.refresh(competitor)
    
    # Optionally trigger initial analysis
    if competitor.website:
        intelligence_service = CompetitorIntelligenceService()
        background_tasks.add_task(
            intelligence_service.analyze_competitor,
            competitor,
            db
        )
    
    return competitor


@router.get("/{competitor_id}", response_model=CompetitorResponse)
async def get_competitor(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific competitor by ID"""
    result = await db.execute(
        select(Competitor)
        .options(selectinload(Competitor.features))
        .where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    return competitor


@router.put("/{competitor_id}", response_model=CompetitorResponse)
async def update_competitor(
    competitor_id: UUID,
    competitor_update: CompetitorUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a competitor"""
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    update_data = competitor_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(competitor, field, value)
    
    await db.commit()
    await db.refresh(competitor)
    
    # Load features
    result = await db.execute(
        select(Competitor)
        .options(selectinload(Competitor.features))
        .where(Competitor.id == competitor_id)
    )
    return result.scalar_one()


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a competitor"""
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    await db.delete(competitor)
    await db.commit()


@router.get("/{competitor_id}/features", response_model=List[CompetitorFeatureResponse])
async def get_competitor_features(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all features for a competitor"""
    result = await db.execute(
        select(CompetitorFeature)
        .where(CompetitorFeature.competitor_id == competitor_id)
        .order_by(CompetitorFeature.feature_name)
    )
    features = result.scalars().all()
    return features


@router.post("/{competitor_id}/analyze", response_model=dict)
async def analyze_competitor(
    competitor_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Trigger AI analysis of a competitor"""
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    # Trigger background analysis
    intelligence_service = CompetitorIntelligenceService()
    background_tasks.add_task(
        intelligence_service.analyze_competitor,
        competitor,
        db
    )
    
    return {
        "message": "Competitor analysis started",
        "competitor_id": str(competitor_id),
        "status": "processing"
    }


@router.post("/{competitor_id}/compare", response_model=dict)
async def compare_with_our_product(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Compare competitor with our product"""
    # Get our product ID
    from app.models import Product
    result = await db.execute(select(Product))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company persona not initialized"
        )
    
    # Get competitor
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    # Perform comparison
    intelligence_service = CompetitorIntelligenceService()
    comparison = await intelligence_service.compare_with_our_product(
        competitor_id=competitor_id,
        product_id=product.id,
        db=db
    )
    
    return comparison