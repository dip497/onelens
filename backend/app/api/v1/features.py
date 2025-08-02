from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Optional
from uuid import UUID
import numpy as np
import logging

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
logger = logging.getLogger(__name__)

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
    # TODO: Re-enable when embedding service is active
    # embedding = await embedding_service.generate_embedding(normalized_text)
    
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
        # TODO: Re-enable when embedding service is active
        # embedding = await embedding_service.generate_embedding(normalized_text)
        
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
    
    # Integrate with Agno workflow
    from app.services.agno_service import agno_service_v2 as agno_service
    
    # Prepare analysis types - if not specified, run all analysis types
    analysis_types = analysis_request.analysis_types or [
        "trend_analysis",
        "business_impact",
        "competitive_analysis",
        "geographic_analysis",
        "priority_scoring"
    ]
    
    # Get feature requests data if business impact analysis is requested
    feature_data = {
        "id": str(feature_id),  # Keep as UUID string
        "title": feature.title,
        "description": feature.description or ""
    }
    
    if "business_impact" in analysis_types:
        # Get customer requests for this feature
        requests_query = select(FeatureRequest).where(FeatureRequest.feature_id == feature_id)
        requests_result = await db.execute(requests_query)
        feature_requests = requests_result.scalars().all()
        
        feature_data["customer_requests"] = [
            {
                "customer_id": str(req.customer_id),
                "urgency": req.urgency.value,
                "estimated_deal_impact": req.estimated_deal_impact
            }
            for req in feature_requests
        ]
    
    try:
        # Run the analysis workflow
        result = await agno_service.analyze_feature(
            feature_id=feature_data["id"],
            feature_data=feature_data,
            analysis_types=analysis_types,
            db_session=db
        )
        
        if result["status"] == "completed":
            return {
                "message": "Feature analysis completed successfully",
                "feature_id": feature_id,
                "analysis_types": analysis_types,
                "status": "completed",
                "results": result.get("results", {})
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Analysis failed: {result.get('error', 'Unknown error')}"
            )
            
    except Exception as e:
        # Log the error but don't expose internal details
        logger.error(f"Failed to run feature analysis workflow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis service temporarily unavailable"
        )

@router.get("/{feature_id}/analysis/results")
async def get_feature_analysis_results(
    feature_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get the analysis results for a feature"""
    # Verify feature exists
    query = select(Feature).where(Feature.id == feature_id)
    result = await db.execute(query)
    feature = result.scalar_one_or_none()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # Get all analysis results for this feature
    results = {}
    
    # Get trend analysis
    trend_query = select(TrendAnalysis).where(TrendAnalysis.feature_id == feature_id).order_by(TrendAnalysis.created_at.desc()).limit(1)
    trend_result = await db.execute(trend_query)
    trend_analysis = trend_result.scalar_one_or_none()
    if trend_analysis:
        results["trend_analysis"] = {
            "trend_keywords": trend_analysis.trend_keywords,
            "alignment_score": trend_analysis.alignment_score,
            "confidence_score": trend_analysis.confidence_score,
            "created_at": trend_analysis.created_at.isoformat()
        }
    
    # Get business impact analysis
    impact_query = select(BusinessImpactAnalysis).where(BusinessImpactAnalysis.feature_id == feature_id).order_by(BusinessImpactAnalysis.created_at.desc()).limit(1)
    impact_result = await db.execute(impact_query)
    impact_analysis = impact_result.scalar_one_or_none()
    if impact_analysis:
        results["business_impact"] = {
            "total_arr_impact": impact_analysis.total_arr_impact,
            "customer_count": impact_analysis.customer_count,
            "average_deal_size": impact_analysis.average_deal_size,
            "created_at": impact_analysis.created_at.isoformat()
        }
    
    # Get priority score
    priority_query = select(PriorityScore).where(PriorityScore.feature_id == feature_id).order_by(PriorityScore.calculated_at.desc()).limit(1)
    priority_result = await db.execute(priority_query)
    priority_score = priority_result.scalar_one_or_none()
    if priority_score:
        results["priority_score"] = {
            "final_score": priority_score.final_score,
            "customer_impact_score": priority_score.customer_impact_score,
            "trend_alignment_score": priority_score.trend_alignment_score,
            "business_impact_score": priority_score.business_impact_score,
            "market_opportunity_score": priority_score.market_opportunity_score,
            "segment_diversity_score": priority_score.segment_diversity_score,
            "calculated_at": priority_score.calculated_at.isoformat()
        }
    
    return {
        "feature_id": feature_id,
        "results": results,
        "has_results": len(results) > 0
    }

@router.post("/batch-update", response_model=dict)
async def batch_update_features(
    updates: List[dict],
    db: AsyncSession = Depends(get_db)
):
    """Batch update multiple features at once"""
    updated_count = 0
    
    for update in updates:
        feature_id = update.get("feature_id")
        module_id = update.get("module_id")
        is_key_differentiator = update.get("is_key_differentiator", False)
        
        if feature_id:
            result = await db.execute(
                select(Feature).where(Feature.id == feature_id)
            )
            feature = result.scalar_one_or_none()
            
            if feature:
                if module_id is not None:
                    feature.module_id = module_id if module_id else None
                feature.is_key_differentiator = is_key_differentiator
                updated_count += 1
    
    await db.commit()
    
    return {"updated": updated_count, "total": len(updates)}


@router.post("/search/similar", response_model=List[FeatureResponse])
async def search_similar_features(
    text: str = Query(..., description="Text to search for similar features"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Search for features similar to the given text using vector similarity"""
    # TODO: Re-enable when embedding service is active
    # Generate embedding for search text
    # search_embedding = await embedding_service.generate_embedding(text.lower())

    # TODO: Implement vector similarity search using pgvector
    # For now, return empty list as placeholder
    return []