from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Product, ProductSegment, ProductModule, Feature
from app.schemas.product import (
    ProductUpdate,
    ProductResponse,
)

router = APIRouter(prefix="/persona", tags=["persona"])


@router.get("/", response_model=ProductResponse)
async def get_company_persona(
    db: AsyncSession = Depends(get_db)
):
    """Get the company's product persona (single product)"""
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company persona not initialized. Please run initialization script."
        )
    
    return product


@router.put("/", response_model=ProductResponse)
async def update_company_persona(
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update the company's product persona"""
    result = await db.execute(select(Product))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company persona not initialized. Please run initialization script."
        )
    
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    await db.commit()
    await db.refresh(product)
    
    # Load relationships
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
        .where(Product.id == product.id)
    )
    return result.scalar_one()


@router.get("/stats", response_model=dict)
async def get_persona_stats(
    db: AsyncSession = Depends(get_db)
):
    """Get statistics about the company persona"""
    result = await db.execute(select(Product))
    product = result.scalar_one_or_none()
    
    if not product:
        return {
            "initialized": False,
            "total_modules": 0,
            "total_features": 0,
            "total_segments": 0,
            "total_competitors": 0,
            "total_battle_cards": 0
        }
    
    # Get counts
    modules_count = await db.execute(
        select(func.count(ProductModule.id))
        .where(ProductModule.product_id == product.id)
    )
    
    features_count = await db.execute(
        select(func.count(Feature.id))
        .join(ProductModule, Feature.module_id == ProductModule.id)
        .where(ProductModule.product_id == product.id)
    )
    
    segments_count = await db.execute(
        select(func.count(ProductSegment.id))
        .where(ProductSegment.product_id == product.id)
    )
    
    # Get competitor count
    from app.models import Competitor, BattleCard
    competitors_count = await db.execute(
        select(func.count(Competitor.id))
    )
    
    battle_cards_count = await db.execute(
        select(func.count(BattleCard.id))
        .where(BattleCard.product_id == product.id)
    )
    
    return {
        "initialized": True,
        "product_name": product.name,
        "product_id": str(product.id),
        "total_modules": modules_count.scalar() or 0,
        "total_features": features_count.scalar() or 0,
        "total_segments": segments_count.scalar() or 0,
        "total_competitors": competitors_count.scalar() or 0,
        "total_battle_cards": battle_cards_count.scalar() or 0
    }