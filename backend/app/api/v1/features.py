from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Optional, Dict, Any
from uuid import UUID
import numpy as np
import logging
import json
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import (
    Feature, Epic, FeatureRequest, Customer, PriorityScore,
    TrendAnalysis, BusinessImpactAnalysis, MarketOpportunityAnalysis,
    GeographicAnalysis, FeatureAnalysisReport
)
from app.agents.agent_definitions import get_agent
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
        ).order_by(PriorityScore.created_at.desc()).limit(1)
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
    from app.services.agno_service import get_agno_service_v2
    agno_service = get_agno_service_v2()
    
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
    priority_query = select(PriorityScore).where(PriorityScore.feature_id == feature_id).order_by(PriorityScore.created_at.desc()).limit(1)
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
            "calculated_at": priority_score.created_at.isoformat()
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


# Cache for agent analysis results
_analysis_cache: Dict[str, Dict[str, Any]] = {}
CACHE_DURATION_HOURS = 24


@router.post("/{feature_id}/agent-analysis/{agent_type}")
async def run_individual_agent_analysis(
    feature_id: UUID,
    agent_type: str,
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False, description="Force refresh cached results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Run individual agent analysis for a specific feature.

    Supported agent types:
    - trend_analyst: Market trend analysis
    - competitive_analyst: Competitive analysis against ManageEngine, Freshservice, HaloITSM
    - market_opportunity_analyst: Market trends and future forecasting
    - business_impact_analyst: Business impact analysis
    - geographic_analyst: Geographic market analysis
    """

    # Validate agent type
    valid_agents = [
        "trend_analyst",
        "competitive_analyst",
        "market_opportunity_analyst",
        "business_impact_analyst",
        "geographic_analyst"
    ]

    if agent_type not in valid_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent type. Must be one of: {', '.join(valid_agents)}"
        )

    # Check if feature exists
    feature_query = select(Feature).where(Feature.id == feature_id)
    feature_result = await db.execute(feature_query)
    feature = feature_result.scalar_one_or_none()

    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )

    # Create cache key
    cache_key = f"{feature_id}_{agent_type}"

    # Check cache first (unless force refresh)
    if not force_refresh and cache_key in _analysis_cache:
        cached_result = _analysis_cache[cache_key]
        cache_time = datetime.fromisoformat(cached_result["cached_at"])

        # Check if cache is still valid (24 hours)
        if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
            return {
                "feature_id": str(feature_id),
                "agent_type": agent_type,
                "analysis": cached_result["analysis"],
                "cached": True,
                "cached_at": cached_result["cached_at"],
                "status": "completed"
            }

    try:
        # Get the agent
        agent = get_agent(agent_type)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent {agent_type} not available"
            )

        # Prepare feature context for the agent
        feature_context = {
            "feature_id": str(feature_id),
            "title": feature.title,
            "description": feature.description or "",
            "customer_request_count": feature.customer_request_count
        }

        # Create analysis prompt based on agent type
        analysis_prompt = _create_analysis_prompt(agent_type, feature_context)

        # Run the agent analysis
        response = agent.run(analysis_prompt)

        # Extract the analysis content
        analysis_content = response.content if hasattr(response, 'content') else str(response)

        # Cache the result
        cache_result = {
            "analysis": analysis_content,
            "cached_at": datetime.now().isoformat()
        }
        _analysis_cache[cache_key] = cache_result

        return {
            "feature_id": str(feature_id),
            "agent_type": agent_type,
            "analysis": analysis_content,
            "cached": False,
            "cached_at": cache_result["cached_at"],
            "status": "completed"
        }

    except Exception as e:
        logger.error(f"Error running {agent_type} analysis for feature {feature_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run {agent_type} analysis: {str(e)}"
        )


def _create_analysis_prompt(agent_type: str, feature_context: Dict[str, Any]) -> str:
    """Create analysis prompt based on agent type and feature context"""

    base_context = f"""
    Feature Analysis Request:
    - Feature: {feature_context['title']}
    - Description: {feature_context['description']}
    - Customer Requests: {feature_context['customer_request_count']}
    """

    if agent_type == "trend_analyst":
        return f"""{base_context}

        Please provide a comprehensive market trend analysis for this feature. Include:
        1. Current market trends relevant to this feature
        2. Technology trends and emerging patterns
        3. Industry adoption patterns
        4. Future outlook and predictions
        5. Trend alignment score and justification

        Format your response in markdown with clear sections and bullet points.
        """

    elif agent_type == "competitive_analyst":
        return f"""{base_context}

        Please provide a detailed competitive analysis focusing on:
        1. ManageEngine - their offering, strengths, and weaknesses
        2. Freshservice - their offering, strengths, and weaknesses
        3. HaloITSM - their offering, strengths, and weaknesses
        4. Market gaps and opportunities
        5. Competitive positioning recommendations

        Format your response in markdown with comparison tables where appropriate.
        """

    elif agent_type == "market_opportunity_analyst":
        return f"""{base_context}

        Please provide market trends and future forecasting analysis including:
        1. Market size and growth projections
        2. Geographic opportunities (US, UK, Germany, Japan, Australia)
        3. Industry vertical analysis
        4. Future market trends and forecasting
        5. Revenue opportunity assessment
        6. Risk factors and mitigation strategies

        Include detailed analysis with numbers, tables, and graphs where possible.
        Format your response in markdown.
        """

    elif agent_type == "business_impact_analyst":
        return f"""{base_context}

        Please provide business impact analysis including:
        1. Revenue impact potential
        2. User adoption forecast
        3. Strategic alignment assessment
        4. Implementation complexity analysis
        5. ROI projections
        6. Business justification

        Format your response in markdown with clear metrics and projections.
        """

    elif agent_type == "geographic_analyst":
        return f"""{base_context}

        Please provide geographic market analysis including:
        1. Regional market penetration opportunities
        2. Regulatory considerations by geography
        3. Cultural adoption factors
        4. Competitive landscape by region
        5. Market entry strategies
        6. Localization requirements

        Format your response in markdown with regional breakdowns.
        """

    else:
        return f"""{base_context}

        Please provide a comprehensive analysis of this feature.
        Format your response in markdown.
        """