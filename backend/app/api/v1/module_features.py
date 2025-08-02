"""
API endpoints for Module Features (sales/marketing features)
Separate from Epic Features (development features)
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import ModuleFeature, ProductModule
from app.schemas.module_feature import (
    ModuleFeatureCreate,
    ModuleFeatureUpdate,
    ModuleFeatureResponse,
    ModuleFeatureListResponse
)

router = APIRouter(prefix="/module-features", tags=["module-features"])


@router.post("/", response_model=ModuleFeatureResponse, status_code=status.HTTP_201_CREATED)
async def create_module_feature(
    feature_data: ModuleFeatureCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new module feature (sales/marketing view)"""
    
    # Verify module exists
    result = await db.execute(
        select(ProductModule).where(ProductModule.id == feature_data.module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with id {feature_data.module_id} not found"
        )
    
    # Create the feature
    feature = ModuleFeature(**feature_data.dict())
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    
    return feature


@router.get("/", response_model=List[ModuleFeatureResponse])
async def list_module_features(
    module_id: Optional[UUID] = None,
    is_key_differentiator: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List module features with optional filtering"""
    
    query = select(ModuleFeature).options(selectinload(ModuleFeature.module))
    
    if module_id:
        query = query.where(ModuleFeature.module_id == module_id)
    
    if is_key_differentiator is not None:
        query = query.where(ModuleFeature.is_key_differentiator == is_key_differentiator)
    
    query = query.order_by(ModuleFeature.order_index)
    
    result = await db.execute(query)
    features = result.scalars().all()
    
    return features


@router.get("/{feature_id}", response_model=ModuleFeatureResponse)
async def get_module_feature(
    feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific module feature"""
    
    result = await db.execute(
        select(ModuleFeature)
        .options(selectinload(ModuleFeature.module))
        .where(ModuleFeature.id == feature_id)
    )
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module feature with id {feature_id} not found"
        )
    
    return feature


@router.put("/{feature_id}", response_model=ModuleFeatureResponse)
async def update_module_feature(
    feature_id: UUID,
    update_data: ModuleFeatureUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a module feature"""
    
    result = await db.execute(
        select(ModuleFeature).where(ModuleFeature.id == feature_id)
    )
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module feature with id {feature_id} not found"
        )
    
    # Update fields
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(feature, field, value)
    
    await db.commit()
    await db.refresh(feature)
    
    return feature


@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module_feature(
    feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a module feature"""
    
    result = await db.execute(
        select(ModuleFeature).where(ModuleFeature.id == feature_id)
    )
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module feature with id {feature_id} not found"
        )
    
    await db.delete(feature)
    await db.commit()


@router.post("/batch-create", response_model=List[ModuleFeatureResponse])
async def batch_create_module_features(
    features_data: List[ModuleFeatureCreate],
    db: AsyncSession = Depends(get_db)
):
    """Create multiple module features at once"""
    
    created_features = []
    
    for feature_data in features_data:
        # Verify module exists
        result = await db.execute(
            select(ProductModule).where(ProductModule.id == feature_data.module_id)
        )
        module = result.scalar_one_or_none()
        
        if module:
            feature = ModuleFeature(**feature_data.dict())
            db.add(feature)
            created_features.append(feature)
    
    await db.commit()
    
    # Refresh all features
    for feature in created_features:
        await db.refresh(feature)
    
    return created_features


@router.put("/modules/{module_id}/reorder", response_model=List[ModuleFeatureResponse])
async def reorder_module_features(
    module_id: UUID,
    feature_orders: List[dict],  # [{"id": "uuid", "order_index": 0}, ...]
    db: AsyncSession = Depends(get_db)
):
    """Reorder features within a module"""
    
    # Update order indices
    for order_data in feature_orders:
        await db.execute(
            select(ModuleFeature)
            .where(
                ModuleFeature.id == order_data["id"],
                ModuleFeature.module_id == module_id
            )
        )
        result = await db.execute(
            select(ModuleFeature).where(ModuleFeature.id == order_data["id"])
        )
        feature = result.scalar_one_or_none()
        
        if feature and feature.module_id == module_id:
            feature.order_index = order_data["order_index"]
    
    await db.commit()
    
    # Return updated list
    result = await db.execute(
        select(ModuleFeature)
        .where(ModuleFeature.module_id == module_id)
        .order_by(ModuleFeature.order_index)
    )
    features = result.scalars().all()
    
    return features


@router.get("/modules/{module_id}/key-differentiators", response_model=List[ModuleFeatureResponse])
async def get_key_differentiators(
    module_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get only the key differentiator features for a module"""
    
    result = await db.execute(
        select(ModuleFeature)
        .where(
            ModuleFeature.module_id == module_id,
            ModuleFeature.is_key_differentiator == True
        )
        .order_by(ModuleFeature.order_index)
    )
    features = result.scalars().all()
    
    return features


@router.post("/link-to-epic-feature", response_model=ModuleFeatureResponse)
async def link_to_epic_feature(
    module_feature_id: UUID,
    epic_feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Link a module feature to an epic feature (development)"""
    
    result = await db.execute(
        select(ModuleFeature).where(ModuleFeature.id == module_feature_id)
    )
    module_feature = result.scalar_one_or_none()
    
    if not module_feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module feature with id {module_feature_id} not found"
        )
    
    # Verify epic feature exists
    from app.models import Feature
    result = await db.execute(
        select(Feature).where(Feature.id == epic_feature_id)
    )
    epic_feature = result.scalar_one_or_none()
    
    if not epic_feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Epic feature with id {epic_feature_id} not found"
        )
    
    # Link them
    module_feature.epic_feature_id = epic_feature_id
    await db.commit()
    await db.refresh(module_feature)
    
    return module_feature