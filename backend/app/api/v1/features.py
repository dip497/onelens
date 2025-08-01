from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Optional
from uuid import UUID
import numpy as np

from app.core.database import get_db
from app.models import Feature, Epic, FeatureRequest, Customer, PriorityScore
from app.schemas.feature import (
    FeatureCreate,
    FeatureUpdate,
    FeatureResponse,
    FeatureWithAnalysis,
    FeatureListResponse,
    FeatureRequestCreate,
    FeatureRequestResponse,
    FeatureAnalysisRequest
)
from app.schemas.base import PaginationParams
from app.services.embedding import EmbeddingService

router = APIRouter()

# Initialize embedding service
embedding_service = EmbeddingService()

@router.post("/", response_model=FeatureResponse, status_code=status.HTTP_201_CREATED)
async def create_feature(
    feature_data: FeatureCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new feature within an epic"""
    # Verify epic exists
    epic_query = select(Epic).where(Epic.id == feature_data.epic_id)
    epic_result = await db.execute(epic_query)
    epic = epic_result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Create normalized text and embedding
    normalized_text = f"{feature_data.title} {feature_data.description}".lower()
    embedding = await embedding_service.generate_embedding(normalized_text)
    
    feature = Feature(
        **feature_data.model_dump(),
        normalized_text=normalized_text,
        # embedding=embedding  # TODO: Enable after creating pgvector extension
    )
    
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    
    return feature

@router.get("/", response_model=FeatureListResponse)
async def list_features(
    pagination: PaginationParams = Depends(),
    epic_id: Optional[UUID] = None,
    search: Optional[str] = None,
    has_priority_score: Optional[bool] = None,
    min_request_count: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List features with filtering and pagination"""
    query = select(Feature)
    
    # Apply filters
    if epic_id:
        query = query.where(Feature.epic_id == epic_id)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Feature.title.ilike(search_term),
                Feature.description.ilike(search_term)
            )
        )
    if min_request_count is not None:
        query = query.where(Feature.customer_request_count >= min_request_count)
    
    if has_priority_score is not None:
        if has_priority_score:
            # Features with priority scores
            subquery = select(PriorityScore.feature_id).distinct()
            query = query.where(Feature.id.in_(subquery))
        else:
            # Features without priority scores
            subquery = select(PriorityScore.feature_id).distinct()
            query = query.where(Feature.id.notin_(subquery))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)
    query = query.order_by(Feature.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    features = result.scalars().all()
    
    return FeatureListResponse(
        items=features,
        total=total,
        page=pagination.page,
        size=pagination.limit,
        pages=(total + pagination.limit - 1) // pagination.limit
    )

@router.get("/{feature_id}", response_model=FeatureWithAnalysis)
async def get_feature(
    feature_id: UUID,
    include_analysis: bool = Query(default=False),
    db: AsyncSession = Depends(get_db)
):
    """Get a feature by ID with optional analysis data"""
    query = select(Feature).where(Feature.id == feature_id)
    result = await db.execute(query)
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    response_data = {
        "id": feature.id,
        "epic_id": feature.epic_id,
        "title": feature.title,
        "description": feature.description,
        "customer_request_count": feature.customer_request_count,
        "created_at": feature.created_at
    }
    
    if include_analysis:
        # Get latest priority score
        priority_query = select(PriorityScore).where(
            PriorityScore.feature_id == feature_id
        ).order_by(PriorityScore.calculated_at.desc()).limit(1)
        priority_result = await db.execute(priority_query)
        priority_score = priority_result.scalar_one_or_none()
        
        if priority_score:
            response_data["priority_score"] = priority_score
        
        # Add more analysis data as needed
    
    return FeatureWithAnalysis(**response_data)

@router.put("/{feature_id}", response_model=FeatureResponse)
async def update_feature(
    feature_id: UUID,
    feature_update: FeatureUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a feature"""
    query = select(Feature).where(Feature.id == feature_id)
    result = await db.execute(query)
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # Update fields
    update_data = feature_update.model_dump(exclude_unset=True)
    
    # Regenerate embedding if title or description changed
    if "title" in update_data or "description" in update_data:
        title = update_data.get("title", feature.title)
        description = update_data.get("description", feature.description)
        normalized_text = f"{title} {description}".lower()
        embedding = await embedding_service.generate_embedding(normalized_text)
        
        update_data["normalized_text"] = normalized_text
        # update_data["embedding"] = embedding  # TODO: Enable after creating pgvector extension
    
    for field, value in update_data.items():
        setattr(feature, field, value)
    
    await db.commit()
    await db.refresh(feature)
    
    return feature

@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(
    feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a feature"""
    query = select(Feature).where(Feature.id == feature_id)
    result = await db.execute(query)
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    await db.delete(feature)
    await db.commit()

@router.post("/{feature_id}/requests", response_model=FeatureRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_feature_request(
    feature_id: UUID,
    request_data: FeatureRequestCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new feature request from a customer"""
    # Verify feature exists
    feature_query = select(Feature).where(Feature.id == feature_id)
    feature_result = await db.execute(feature_query)
    feature = feature_result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # Verify customer exists
    customer_query = select(Customer).where(Customer.id == request_data.customer_id)
    customer_result = await db.execute(customer_query)
    customer = customer_result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Create feature request
    feature_request = FeatureRequest(
        feature_id=feature_id,
        **request_data.model_dump()
    )
    
    db.add(feature_request)
    
    # Update feature request count
    feature.customer_request_count += 1
    
    await db.commit()
    await db.refresh(feature_request)
    
    return feature_request

@router.get("/{feature_id}/requests", response_model=List[FeatureRequestResponse])
async def get_feature_requests(
    feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all feature requests for a specific feature"""
    query = select(FeatureRequest).where(FeatureRequest.feature_id == feature_id)
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return requests

@router.post("/{feature_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
async def trigger_feature_analysis(
    feature_id: UUID,
    analysis_request: FeatureAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """Trigger analysis for a specific feature"""
    query = select(Feature).where(Feature.id == feature_id)
    result = await db.execute(query)
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # TODO: Integrate with Agno workflow
    # workflow_config = {
    #     "feature_id": feature_id,
    #     "analysis_types": analysis_request.analysis_types
    # }
    # await agno_service.trigger_workflow("feature_analysis", workflow_config)
    
    return {
        "message": "Feature analysis triggered successfully",
        "feature_id": feature_id,
        "analysis_types": analysis_request.analysis_types,
        "status": "pending"
    }

@router.post("/search/similar", response_model=List[FeatureResponse])
async def search_similar_features(
    text: str = Query(..., description="Text to search for similar features"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Search for features similar to the given text using vector similarity"""
    # Generate embedding for search text
    search_embedding = await embedding_service.generate_embedding(text.lower())
    
    # TODO: Implement vector similarity search using pgvector
    # For now, return empty list as placeholder
    return []